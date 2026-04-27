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
