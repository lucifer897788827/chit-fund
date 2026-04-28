from datetime import date, datetime
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


class AdminGroupSummaryResponse(BaseModel):
    id: int
    name: str
    status: str
    owner: str
    membersCount: int
    monthlyAmount: int


class AdminGroupDetailSummaryResponse(BaseModel):
    id: int
    name: str
    status: str
    owner: str
    ownerPhone: str
    membersCount: int
    monthlyAmount: int
    chitValue: int
    currentCycleNo: int
    startDate: date
    firstAuctionDate: date


class AdminGroupDetailMemberResponse(BaseModel):
    membershipId: int
    userId: int
    name: str
    phone: str
    membershipStatus: str
    prizedStatus: str
    totalPaid: int
    totalReceived: int
    netPosition: int
    paymentScore: int
    pendingPaymentsCount: int
    pendingAmount: int


class AdminGroupDetailFinancialSummaryResponse(BaseModel):
    totalCollected: int
    totalPaid: int
    pendingAmount: int


class AdminGroupDetailAuctionResponse(BaseModel):
    id: int
    cycleNo: int
    month: str
    winner: str | None = None
    bidAmount: int | None = None
    status: str
    scheduledAt: datetime | None = None


class AdminGroupDetailRiskMemberResponse(BaseModel):
    userId: int
    name: str
    phone: str
    pendingPaymentsCount: int
    pendingAmount: int
    paymentScore: int
    netPosition: int


class AdminGroupDetailResponse(BaseModel):
    group: AdminGroupDetailSummaryResponse
    members: list[AdminGroupDetailMemberResponse]
    financialSummary: AdminGroupDetailFinancialSummaryResponse
    auctions: list[AdminGroupDetailAuctionResponse]
    defaulters: list[AdminGroupDetailRiskMemberResponse]


class AdminAuctionSummaryResponse(BaseModel):
    id: int
    group: str
    winner: str | None = None
    bidAmount: int | None = None
    status: str
    scheduledAt: datetime | None = None


class AdminPaymentSummaryResponse(BaseModel):
    id: int
    user: str
    group: str | None = None
    groupId: int | None = None
    amount: int
    status: str


class AdminDefaulterInsightResponse(BaseModel):
    userId: int
    name: str | None = None
    phone: str
    pendingPaymentsCount: int
    pendingAmount: int


class AdminInsightsSummaryResponse(BaseModel):
    totalUsers: int
    activeGroups: int
    pendingPayments: int
    defaulters: int


class AdminUserSummaryResponse(BaseModel):
    id: int
    role: str
    name: str | None = None
    phone: str
    isActive: bool
    createdAt: datetime
    totalChits: int
    paymentScore: int


class AdminUserFinancialSummaryResponse(BaseModel):
    paymentCount: int
    totalPaid: int
    payoutCount: int
    totalReceived: int
    netCashflow: int
    netPosition: int
    paymentScore: int


class AdminUserParticipationStatsResponse(BaseModel):
    totalChits: int
    ownedChits: int
    joinedChits: int
    externalChits: int
    membershipCount: int
    activeMemberships: int
    prizedMemberships: int


class AdminUserChitItemResponse(BaseModel):
    id: int
    kind: Literal["owned", "joined"]
    groupCode: str
    title: str
    status: str
    currentCycleNo: int


class AdminUserPaymentItemResponse(BaseModel):
    id: int
    amount: int
    paymentDate: date | None = None
    status: str
    paymentType: str
    paymentMethod: str
    groupId: int | None = None
    membershipId: int | None = None


class AdminUserExternalChitItemResponse(BaseModel):
    id: int
    title: str
    organizerName: str
    chitValue: int
    installmentAmount: int
    startDate: date | None = None
    status: str


class AdminUserDetailResponse(BaseModel):
    id: int
    phone: str
    email: str | None = None
    role: str
    createdAt: datetime
    isActive: bool
    ownerId: int | None = None
    subscriberId: int | None = None
    financialSummary: AdminUserFinancialSummaryResponse
    participationStats: AdminUserParticipationStatsResponse
    chits: list[AdminUserChitItemResponse]
    payments: list[AdminUserPaymentItemResponse]
    externalChitsData: list[AdminUserExternalChitItemResponse]


class AdminUserDeactivateResponse(BaseModel):
    id: int
    isActive: bool


class AdminUserActivateResponse(BaseModel):
    id: int
    isActive: bool


class AdminBulkDeactivateRequest(BaseModel):
    userIds: list[int] = Field(min_length=1)


class AdminBulkDeactivateResponse(BaseModel):
    deactivatedUserIds: list[int]
    count: int
