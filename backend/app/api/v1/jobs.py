import uuid
from datetime import datetime, timezone

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.queues import _get_owned_queue
from app.core.database import get_db
from app.models.job import Job
from app.models.scheduled_job import ScheduledJob
from app.models.queue import Queue
from app.models.dead_letter_queue import DeadLetterQueue
from app.models.user import User
from app.schemas.job import (
    JobCreate,
    JobOut,
    BatchJobCreate,
    ScheduledJobCreate,
    ScheduledJobOut,
    JobStatus,
)
from app.schemas.dead_letter_queue import DeadLetterQueueOut

router = APIRouter(prefix="/api/v1", tags=["jobs"])


def _build_job(queue: Queue, payload: JobCreate, batch_id: uuid.UUID | None = None) -> Job:
    now = datetime.now(timezone.utc)
    run_at = payload.run_at or now
    initial_status = "queued" if run_at <= now else "scheduled"

    return Job(
        queue_id=queue.id,
        type=payload.type,
        payload=payload.payload,
        status=initial_status,
        priority=payload.priority if payload.priority is not None else queue.priority,
        run_at=run_at,
        retry_policy_id=queue.default_retry_policy_id,
        idempotency_key=payload.idempotency_key,
        batch_id=batch_id,
    )


def _assert_queue_accepts_jobs(queue: Queue):
    if queue.status != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Queue is '{queue.status}' and is not accepting new jobs. Resume it first.",
        )


@router.post("/queues/{queue_id}/jobs", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    queue_id: uuid.UUID,
    payload: JobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    queue = _get_owned_queue(db, queue_id, current_user)
    _assert_queue_accepts_jobs(queue)

    if payload.idempotency_key:
        existing = (
            db.query(Job)
            .filter(Job.queue_id == queue_id, Job.idempotency_key == payload.idempotency_key)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A job with this idempotency_key already exists in this queue",
            )

    job = _build_job(queue, payload)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.post("/queues/{queue_id}/jobs/batch", response_model=list[JobOut], status_code=status.HTTP_201_CREATED)
def create_batch_jobs(
    queue_id: uuid.UUID,
    payload: BatchJobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    queue = _get_owned_queue(db, queue_id, current_user)
    _assert_queue_accepts_jobs(queue)

    batch_id = uuid.uuid4()
    jobs = [_build_job(queue, job_payload, batch_id=batch_id) for job_payload in payload.jobs]
    db.add_all(jobs)
    db.commit()
    for job in jobs:
        db.refresh(job)
    return jobs


@router.get("/queues/{queue_id}/jobs", response_model=list[JobOut])
def list_jobs(
    queue_id: uuid.UUID,
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    type_filter: str | None = Query(default=None, alias="type"),
    batch_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_queue(db, queue_id, current_user)
    q = db.query(Job).filter(Job.queue_id == queue_id)
    if status_filter:
        q = q.filter(Job.status == status_filter.value)
    if type_filter:
        q = q.filter(Job.type == type_filter)
    if batch_id:
        q = q.filter(Job.batch_id == batch_id)
    return q.order_by(Job.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    _get_owned_queue(db, job.queue_id, current_user)
    return job


# ---- Recurring / scheduled job templates ----


def _compute_next_run_at(payload: ScheduledJobCreate) -> datetime:
    if payload.run_once_at:
        return payload.run_once_at
    now = datetime.now(timezone.utc)
    return croniter(payload.cron_expression, now).get_next(datetime)


@router.post(
    "/queues/{queue_id}/scheduled-jobs", response_model=ScheduledJobOut, status_code=status.HTTP_201_CREATED
)
def create_scheduled_job(
    queue_id: uuid.UUID,
    payload: ScheduledJobCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    queue = _get_owned_queue(db, queue_id, current_user)
    _assert_queue_accepts_jobs(queue)

    scheduled_job = ScheduledJob(
        queue_id=queue.id,
        type=payload.type,
        payload_template=payload.payload_template,
        cron_expression=payload.cron_expression,
        run_once_at=payload.run_once_at,
        next_run_at=_compute_next_run_at(payload),
    )
    db.add(scheduled_job)
    db.commit()
    db.refresh(scheduled_job)
    return scheduled_job


@router.get("/queues/{queue_id}/scheduled-jobs", response_model=list[ScheduledJobOut])
def list_scheduled_jobs(
    queue_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_queue(db, queue_id, current_user)
    return (
        db.query(ScheduledJob)
        .filter(ScheduledJob.queue_id == queue_id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )


@router.post("/scheduled-jobs/{scheduled_job_id}/deactivate", response_model=ScheduledJobOut)
def deactivate_scheduled_job(
    scheduled_job_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    scheduled_job = db.get(ScheduledJob, scheduled_job_id)
    if scheduled_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduled job not found")
    _get_owned_queue(db, scheduled_job.queue_id, current_user)
    scheduled_job.is_active = False
    db.commit()
    db.refresh(scheduled_job)
    return scheduled_job


# ---- Dead Letter Queue ----


@router.get("/queues/{queue_id}/dead-letter-queue", response_model=list[DeadLetterQueueOut])
def list_dead_letter_entries(
    queue_id: uuid.UUID,
    include_resolved: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_queue(db, queue_id, current_user)
    q = db.query(DeadLetterQueue).join(Job, Job.id == DeadLetterQueue.job_id).filter(Job.queue_id == queue_id)
    if not include_resolved:
        q = q.filter(DeadLetterQueue.resolved.is_(False))
    return q.order_by(DeadLetterQueue.moved_at.desc()).offset((page - 1) * page_size).limit(page_size).all()


@router.post("/dead-letter-queue/{dlq_id}/replay", response_model=JobOut)
def replay_dead_letter_job(
    dlq_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Resets the job's attempt count and puts it back in the queue for a fresh run."""
    dlq_entry = db.get(DeadLetterQueue, dlq_id)
    if dlq_entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dead letter entry not found")

    job = db.get(Job, dlq_entry.job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Underlying job not found")
    _get_owned_queue(db, job.queue_id, current_user)

    job.status = "queued"
    job.attempt_count = 0
    job.run_at = datetime.now(timezone.utc)
    job.worker_id = None
    job.claimed_at = None
    dlq_entry.resolved = True
    db.commit()
    db.refresh(job)
    return job


@router.post("/dead-letter-queue/{dlq_id}/dismiss", response_model=DeadLetterQueueOut)
def dismiss_dead_letter_job(
    dlq_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Marks a DLQ entry as resolved without replaying the job (e.g. it was bad data, not worth retrying)."""
    dlq_entry = db.get(DeadLetterQueue, dlq_id)
    if dlq_entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dead letter entry not found")
    job = db.get(Job, dlq_entry.job_id)
    _get_owned_queue(db, job.queue_id, current_user)
    dlq_entry.resolved = True
    db.commit()
    db.refresh(dlq_entry)
    return dlq_entry
