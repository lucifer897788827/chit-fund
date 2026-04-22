from datetime import datetime

from pydantic import BaseModel


class JobRunResponse(BaseModel):
    id: int
    taskName: str
    taskId: str | None = None
    status: str
    attempts: int
    startedAt: datetime | None = None
    completedAt: datetime | None = None
    failedAt: datetime | None = None
    summary: dict | None = None
    createdAt: datetime
    updatedAt: datetime


class JobCleanupResponse(BaseModel):
    deletedCount: int
    cutoffDays: int

