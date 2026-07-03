import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.organizations import _get_owned_org
from app.core.database import get_db
from app.models.project import Project
from app.models.queue import Queue
from app.models.retry_policy import RetryPolicy
from app.models.user import User
from app.schemas.queue import QueueCreate, QueueOut, QueueUpdate, QueueStatus

router = APIRouter(prefix="/api/v1", tags=["queues"])


def _get_owned_project(db: Session, project_id: uuid.UUID, user: User) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    _get_owned_org(db, project.organization_id, user)
    return project


@router.post("/projects/{project_id}/queues", response_model=QueueOut, status_code=status.HTTP_201_CREATED)
def create_queue(
    project_id: uuid.UUID,
    payload: QueueCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_project(db, project_id, current_user)

    existing = db.query(Queue).filter(Queue.project_id == project_id, Queue.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Queue name already exists in this project")

    retry_policy_id = None
    if payload.retry_policy:
        rp = RetryPolicy(**payload.retry_policy.model_dump())
        db.add(rp)
        db.flush()
        retry_policy_id = rp.id

    queue = Queue(
        project_id=project_id,
        name=payload.name,
        priority=payload.priority,
        concurrency_limit=payload.concurrency_limit,
        default_retry_policy_id=retry_policy_id,
    )
    db.add(queue)
    db.commit()
    db.refresh(queue)
    return queue


@router.get("/projects/{project_id}/queues", response_model=list[QueueOut])
def list_queues(
    project_id: uuid.UUID,
    status_filter: QueueStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_project(db, project_id, current_user)
    q = db.query(Queue).filter(Queue.project_id == project_id)
    if status_filter:
        q = q.filter(Queue.status == status_filter.value)
    return q.offset((page - 1) * page_size).limit(page_size).all()


def _get_owned_queue(db: Session, queue_id: uuid.UUID, user: User) -> Queue:
    queue = db.get(Queue, queue_id)
    if queue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue not found")
    _get_owned_project(db, queue.project_id, user)
    return queue


@router.get("/queues/{queue_id}", response_model=QueueOut)
def get_queue(queue_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _get_owned_queue(db, queue_id, current_user)


@router.patch("/queues/{queue_id}", response_model=QueueOut)
def update_queue(
    queue_id: uuid.UUID,
    payload: QueueUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    queue = _get_owned_queue(db, queue_id, current_user)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(queue, field, value.value if isinstance(value, QueueStatus) else value)
    db.commit()
    db.refresh(queue)
    return queue


@router.post("/queues/{queue_id}/pause", response_model=QueueOut)
def pause_queue(queue_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    queue = _get_owned_queue(db, queue_id, current_user)
    queue.status = "paused"
    db.commit()
    db.refresh(queue)
    return queue


@router.post("/queues/{queue_id}/resume", response_model=QueueOut)
def resume_queue(queue_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    queue = _get_owned_queue(db, queue_id, current_user)
    queue.status = "active"
    db.commit()
    db.refresh(queue)
    return queue
