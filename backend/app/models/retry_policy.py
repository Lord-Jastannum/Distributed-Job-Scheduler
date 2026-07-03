import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RetryPolicy(Base):
    __tablename__ = "retry_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy: Mapped[str] = mapped_column(String(20), nullable=False, default="fixed")  # fixed|linear|exponential
    base_delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    max_delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
