from datetime import date, datetime

from pydantic import BaseModel

from app.modules.payments.schemas import MemberBalanceResponse


class OwnerGroupSummary(BaseModel):
    groupId: int
    groupCode: str
    title: str
    status: str
    currentCycleNo: int
    memberCount: int
    activeMemberCount: int
    totalDue: int
    totalPaid: int
    outstandingAmount: int
    totalPenaltyAmount: int | None = None
    penaltyEnabled: bool = False
    penaltyType: str | None = None
    penaltyValue: float | int | None = None
    gracePeriodDays: int = 0
    auctionCount: int
    openAuctionCount: int
    latestPaymentAt: datetime | None = None


class OwnerAuctionSummary(BaseModel):
    sessionId: int
    groupId: int
    groupCode: str
    groupTitle: str
    cycleNo: int
    auctionMode: str
    commissionMode: str
    commissionValue: int | None = None
    minBidValue: int | None = None
    maxBidValue: int | None = None
    minIncrement: int | None = None
    status: str
    scheduledStartAt: datetime
    actualStartAt: datetime | None = None
    actualEndAt: datetime | None = None
    highestBidAmount: int | None = None
    highestBidMembershipNo: int | None = None
    highestBidderName: str | None = None
    winnerMembershipId: int | None = None
    winnerMembershipNo: int | None = None
    winnerName: str | None = None
    winningBidAmount: int | None = None
    finalizedAt: datetime | None = None
    createdAt: datetime


class OwnerPaymentSummary(BaseModel):
    paymentId: int
    groupId: int | None = None
    groupCode: str | None = None
    subscriberId: int
    subscriberName: str
    amount: int
    paymentDate: date
    paymentMethod: str
    status: str
    paymentStatus: str | None = None
    penaltyAmount: int | None = None
    arrearsAmount: int | None = None
    nextDueAmount: int | None = None
    nextDueDate: date | None = None
    outstandingAmount: int | None = None
    createdAt: datetime


class OwnerPayoutSummary(BaseModel):
    id: int
    ownerId: int
    auctionResultId: int
    groupId: int
    groupCode: str
    groupTitle: str
    subscriberId: int
    subscriberName: str
    membershipId: int
    memberNo: int
    cycleNo: int
    grossAmount: int
    deductionsAmount: int
    netAmount: int
    payoutMethod: str
    payoutDate: date | None = None
    referenceNo: str | None = None
    status: str
    paymentStatus: str | None = None
    penaltyAmount: int | None = None
    arrearsAmount: int | None = None
    nextDueAmount: int | None = None
    nextDueDate: date | None = None
    outstandingAmount: int | None = None
    createdAt: datetime


class OwnerActivityItem(BaseModel):
    kind: str
    occurredAt: datetime
    groupId: int | None = None
    groupCode: str | None = None
    title: str
    detail: str
    refId: int


class OwnerAuditLogItem(BaseModel):
    id: int
    occurredAt: datetime
    action: str
    actionLabel: str
    entityType: str
    entityId: str
    actorId: int | None = None
    actorName: str | None = None
    actorRole: str | None = None
    ownerId: int | None = None
    metadata: dict | list | str | int | float | bool | None = None
    before: dict | list | str | int | float | bool | None = None
    after: dict | list | str | int | float | bool | None = None


class OwnerDashboardResponse(BaseModel):
    ownerId: int
    groupCount: int
    auctionCount: int
    paymentCount: int
    payoutCount: int
    totalDueAmount: int
    totalPaidAmount: int
    totalOutstandingAmount: int
    totalPayoutAmount: int
    groups: list[OwnerGroupSummary]
    recentAuctions: list[OwnerAuctionSummary]
    recentPayments: list[OwnerPaymentSummary]
    recentPayouts: list[OwnerPayoutSummary]
    balances: list[MemberBalanceResponse]
    recentActivity: list[OwnerActivityItem]
    recentAuditLogs: list[OwnerAuditLogItem]
