from datetime import datetime

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: int
    userId: int
    ownerId: int | None = None
    channel: str
    title: str
    message: str
    status: str
    createdAt: datetime
    sentAt: datetime | None = None
    readAt: datetime | None = None


__all__ = ["NotificationResponse"]
