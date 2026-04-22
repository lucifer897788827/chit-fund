from datetime import datetime
from typing import Any

from pydantic import BaseModel


class JobRunResponse(BaseModel):
    id: int
    ownerId: int | None = None
    jobType: str
    taskId: str | None = None
    status: str
    attempts: int
    startedAt: datetime | None = None
    completedAt: datetime | None = None
    failedAt: datetime | None = None
    summary: dict[str, Any] | None = None
    createdAt: datetime
    updatedAt: datetime


__all__ = ["JobRunResponse"]
