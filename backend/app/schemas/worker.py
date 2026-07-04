import uuid
from datetime import datetime

from pydantic import BaseModel


class WorkerOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    hostname: str
    status: str
    registered_at: datetime
    last_seen_at: datetime | None

    class Config:
        from_attributes = True


class WorkerHeartbeatOut(BaseModel):
    id: int
    worker_id: uuid.UUID
    sent_at: datetime
    active_jobs: int
    cpu_percent: float | None
    mem_percent: float | None

    class Config:
        from_attributes = True


class JobExecutionOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    worker_id: uuid.UUID | None
    attempt_number: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    error_message: str | None

    class Config:
        from_attributes = True
