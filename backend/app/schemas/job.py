import uuid
from datetime import datetime, timezone
from enum import Enum

from croniter import croniter
from pydantic import BaseModel, Field, field_validator, model_validator


class JobStatus(str, Enum):
    queued = "queued"
    scheduled = "scheduled"
    claimed = "claimed"
    running = "running"
    completed = "completed"
    failed = "failed"
    dead_letter = "dead_letter"


class JobCreate(BaseModel):
    type: str = Field(min_length=1, max_length=100)
    payload: dict = Field(default_factory=dict)
    run_at: datetime | None = Field(
        default=None, description="Omit for immediate execution; set a future time to delay."
    )
    priority: int | None = Field(default=None, ge=-32768, le=32767, description="Overrides queue default if set")
    idempotency_key: str | None = Field(default=None, max_length=255)


class JobOut(BaseModel):
    id: uuid.UUID
    queue_id: uuid.UUID
    type: str
    payload: dict
    status: str
    priority: int
    run_at: datetime
    attempt_count: int
    idempotency_key: str | None
    worker_id: uuid.UUID | None
    claimed_at: datetime | None
    batch_id: uuid.UUID | None
    scheduled_job_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BatchJobCreate(BaseModel):
    jobs: list[JobCreate] = Field(min_length=1, max_length=500)


class ScheduledJobCreate(BaseModel):
    type: str = Field(min_length=1, max_length=100)
    payload_template: dict = Field(default_factory=dict)
    cron_expression: str | None = Field(default=None, description="Set this OR run_once_at, not both")
    run_once_at: datetime | None = Field(default=None, description="Set this OR cron_expression, not both")

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not croniter.is_valid(v):
            raise ValueError(f"Invalid cron expression: {v!r}")
        return v

    @model_validator(mode="after")
    def validate_xor(self):
        has_cron = self.cron_expression is not None
        has_once = self.run_once_at is not None
        if has_cron == has_once:  # both set or neither set
            raise ValueError("Exactly one of cron_expression or run_once_at must be provided")
        if has_once and self.run_once_at <= datetime.now(timezone.utc):
            raise ValueError("run_once_at must be in the future")
        return self


class ScheduledJobOut(BaseModel):
    id: uuid.UUID
    queue_id: uuid.UUID
    type: str
    payload_template: dict
    cron_expression: str | None
    run_once_at: datetime | None
    next_run_at: datetime
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
