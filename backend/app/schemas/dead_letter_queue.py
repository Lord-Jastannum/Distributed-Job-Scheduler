import uuid
from datetime import datetime

from pydantic import BaseModel


class DeadLetterQueueOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    final_error: str
    attempt_count: int
    moved_at: datetime
    resolved: bool

    class Config:
        from_attributes = True
