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


class AdminAuctionSummaryResponse(BaseModel):
    id: int
    group: str
    winner: str | None = None
    bidAmount: int | None = None
    status: str


class AdminPaymentSummaryResponse(BaseModel):
    id: int
    user: str
    group: str | None = None
    amount: int
    status: str


class AdminUserSummaryResponse(BaseModel):
    id: int
    role: str
    phone: str
    createdAt: datetime
    totalChits: int
    paymentScore: int


class AdminUserFinancialSummaryResponse(BaseModel):
    paymentCount: int
    totalPaid: int
    payoutCount: int
    totalReceived: int
    netCashflow: int
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
