import uuid

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.organizations import _get_owned_org
from app.core.database import get_db
from app.models.project import Project
from app.models.worker import Worker
from app.models.worker_heartbeat import WorkerHeartbeat
from app.models.job_execution import JobExecution
from app.models.user import User
from app.schemas.worker import WorkerOut, WorkerHeartbeatOut, JobExecutionOut

router = APIRouter(prefix="/api/v1", tags=["workers"])


def _get_owned_project_for_workers(db: Session, project_id: uuid.UUID, user: User) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    _get_owned_org(db, project.organization_id, user)
    return project


@router.get("/projects/{project_id}/workers", response_model=list[WorkerOut])
def list_workers(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_project_for_workers(db, project_id, current_user)
    return db.query(Worker).filter(Worker.project_id == project_id).order_by(Worker.registered_at.desc()).all()


@router.get("/workers/{worker_id}/heartbeats", response_model=list[WorkerHeartbeatOut])
def list_worker_heartbeats(
    worker_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    worker = db.get(Worker, worker_id)
    if worker is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found")
    _get_owned_project_for_workers(db, worker.project_id, current_user)
    return (
        db.query(WorkerHeartbeat)
        .filter(WorkerHeartbeat.worker_id == worker_id)
        .order_by(WorkerHeartbeat.sent_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/jobs/{job_id}/executions", response_model=list[JobExecutionOut])
def list_job_executions(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.api.v1.queues import _get_owned_queue
    from app.models.job import Job

    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    _get_owned_queue(db, job.queue_id, current_user)
    return (
        db.query(JobExecution)
        .filter(JobExecution.job_id == job_id)
        .order_by(JobExecution.attempt_number.asc())
        .all()
    )
