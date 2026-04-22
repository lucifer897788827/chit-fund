from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import utcnow


class JobRun(Base):
    __tablename__ = "job_runs"
    __table_args__ = (
        Index("ix_job_runs_status_started_at_id", "status", "started_at", "id"),
        Index("ix_job_runs_task_name_status_started_at_id", "task_name", "status", "started_at", "id"),
        Index("ix_job_runs_status_updated_at_id", "status", "updated_at", "id"),
        Index("ix_job_runs_owner_id_started_at_id", "owner_id", "started_at", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("owners.id"), index=True, nullable=True)
    task_name: Mapped[str] = mapped_column(String(255), index=True)
    task_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(30), index=True, default="running")
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
