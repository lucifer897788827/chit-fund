from datetime import datetime

from pydantic import BaseModel


class AuctionRoomResponse(BaseModel):
    sessionId: int
    groupId: int
    status: str
    cycleNo: int
    serverTime: datetime
    endsAt: datetime
    canBid: bool
    myMembershipId: int
    myLastBid: int | None


class BidCreate(BaseModel):
    membershipId: int
    bidAmount: int
    idempotencyKey: str


class BidResponse(BaseModel):
    accepted: bool
    bidId: int
    placedAt: datetime
    sessionStatus: str
