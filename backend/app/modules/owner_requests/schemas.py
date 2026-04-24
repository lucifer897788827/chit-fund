from datetime import datetime

from pydantic import BaseModel


class OwnerRequestCreate(BaseModel):
    pass


class OwnerRequestResponse(BaseModel):
    id: int
    userId: int
    status: str
    createdAt: datetime
    requesterName: str | None = None
    phone: str | None = None
    email: str | None = None
    ownerId: int | None = None


class OwnerRequestDecisionResponse(OwnerRequestResponse):
    ownerCreated: bool = False
