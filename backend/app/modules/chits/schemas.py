from datetime import datetime

from pydantic import BaseModel


class MembershipInviteRequest(BaseModel):
    phone: str


class MembershipRequestResponse(BaseModel):
    membershipId: int
    groupId: int
    subscriberId: int
    memberNo: int
    membershipStatus: str
    requestedAt: datetime | None = None


class MembershipDecisionRequest(BaseModel):
    membershipId: int
