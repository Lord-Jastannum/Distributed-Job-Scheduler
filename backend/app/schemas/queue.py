import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class RetryStrategy(str, Enum):
    fixed = "fixed"
    linear = "linear"
    exponential = "exponential"


class QueueStatus(str, Enum):
    active = "active"
    paused = "paused"


class RetryPolicyCreate(BaseModel):
    strategy: RetryStrategy = RetryStrategy.fixed
    base_delay_seconds: int = Field(default=5, ge=0)
    max_retries: int = Field(default=3, ge=0, le=50)
    max_delay_seconds: int = Field(default=3600, ge=0)


class RetryPolicyOut(RetryPolicyCreate):
    id: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True


class QueueCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    priority: int = Field(default=0, ge=-32768, le=32767)
    concurrency_limit: int = Field(default=5, ge=1)
    retry_policy: RetryPolicyCreate | None = None


class QueueUpdate(BaseModel):
    priority: int | None = None
    concurrency_limit: int | None = Field(default=None, ge=1)
    status: QueueStatus | None = None


class QueueOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    priority: int
    concurrency_limit: int
    status: str
    default_retry_policy_id: uuid.UUID | None
    created_at: datetime

    class Config:
        from_attributes = True


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
