from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


AdminMessageType = Literal["info", "warning", "critical"]


class AdminMessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    type: AdminMessageType = "info"
    active: bool = True


class AdminMessageResponse(BaseModel):
    id: int
    message: str
    type: AdminMessageType
    active: bool
    createdByUserId: int
    createdAt: datetime
    updatedAt: datetime


class AdminUserSummaryResponse(BaseModel):
    id: int
    phone: str
    email: str | None = None
    role: str
    isActive: bool
    ownerId: int | None = None
    subscriberId: int | None = None
    paymentBehavior: dict
    stats: dict
