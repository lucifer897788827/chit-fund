from datetime import date, datetime

from pydantic import BaseModel, Field


class SubscriberCreate(BaseModel):
    ownerId: int | None = None
    fullName: str
    phone: str
    email: str | None = None
    password: str = Field(min_length=1)


class SubscriberUpdate(BaseModel):
    ownerId: int | None = None
    fullName: str | None = None
    phone: str | None = None
    email: str | None = None


class SubscriberResponse(BaseModel):
    id: int
    ownerId: int | None
    fullName: str
    phone: str
    email: str | None = None
    status: str


class SubscriberDashboardMembership(BaseModel):
    membershipId: int
    groupId: int
    groupCode: str
    groupTitle: str
    memberNo: int
    membershipStatus: str
    inviteStatus: str | None = None
    inviteExpiresAt: datetime | None = None
    prizedStatus: str
    canBid: bool
    currentCycleNo: int
    installmentAmount: int
    totalDue: int
    totalPaid: int
    outstandingAmount: int
    penaltyAmount: int | None = None
    paymentStatus: str
    arrearsAmount: int
    nextDueAmount: int
    nextDueDate: date | None = None
    auctionStatus: str | None = None
    slotCount: int = 1
    wonSlotCount: int = 0
    remainingSlotCount: int = 1


class SubscriberDashboardAuction(BaseModel):
    sessionId: int
    groupId: int
    groupCode: str
    groupTitle: str
    cycleNo: int
    status: str
    membershipId: int
    canBid: bool
    slotCount: int = 1
    wonSlotCount: int = 0
    remainingSlotCount: int = 1


class SubscriberDashboardAuctionOutcome(BaseModel):
    sessionId: int
    groupId: int
    groupCode: str
    groupTitle: str
    cycleNo: int
    status: str
    membershipId: int | None = None
    winnerMembershipId: int
    winnerMemberNo: int | None = None
    winnerName: str | None = None
    winningBidAmount: int
    finalizedAt: datetime | None = None


class SubscriberDashboardResponse(BaseModel):
    subscriberId: int
    memberships: list[SubscriberDashboardMembership]
    activeAuctions: list[SubscriberDashboardAuction]
    recentAuctionOutcomes: list[SubscriberDashboardAuctionOutcome] = []
