from datetime import date

from pydantic import BaseModel


class GroupCreate(BaseModel):
    ownerId: int
    groupCode: str
    title: str
    chitValue: float
    installmentAmount: float
    memberCount: int
    cycleCount: int
    cycleFrequency: str
    startDate: date
    firstAuctionDate: date


class GroupResponse(GroupCreate):
    id: int
    currentCycleNo: int
    biddingEnabled: bool
    status: str


class MembershipCreate(BaseModel):
    subscriberId: int
    memberNo: int


class MembershipResponse(MembershipCreate):
    id: int
    groupId: int
    membershipStatus: str
    prizedStatus: str
    canBid: bool


class AuctionSessionCreate(BaseModel):
    cycleNo: int
    biddingWindowSeconds: int = 180


class AuctionSessionResponse(BaseModel):
    id: int
    groupId: int
    cycleNo: int
    status: str
    biddingWindowSeconds: int
