from datetime import date, datetime
import math
from typing import Any

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

from app.core.money import parse_whole_amount
from app.models.chit import CurrentMonthStatus


class GroupCreate(BaseModel):
    ownerId: int
    groupCode: str
    title: str
    chitValue: int
    installmentAmount: int
    memberCount: int
    cycleCount: int | None = None
    autoCycleCalculation: bool = False
    cycleFrequency: str
    commissionType: str = "NONE"
    auctionType: str = "LIVE"
    groupType: str = "STANDARD"
    startDate: date
    firstAuctionDate: date
    penaltyEnabled: bool = False
    penaltyType: str | None = None
    penaltyValue: float | int | None = None
    gracePeriodDays: int = 0
    visibility: str = "private"

    @field_validator("chitValue", "installmentAmount", mode="before")
    @classmethod
    def _validate_money_fields(cls, value):
        return parse_whole_amount(value, allow_none=True)

    @model_validator(mode="after")
    def _validate_penalty_value(self):
        if not self.penaltyEnabled or self.penaltyValue is None:
            return self

        normalized_penalty_type = (self.penaltyType or "").strip().upper()
        if normalized_penalty_type == "PERCENTAGE":
            self.penaltyValue = _parse_percentage_value(self.penaltyValue)
            return self

        self.penaltyValue = parse_whole_amount(self.penaltyValue, allow_none=True)
        return self


def _parse_percentage_value(value: Any) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Value must be numeric")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Value must be numeric")
        return value

    text = str(value).strip()
    if not text:
        return None
    try:
        normalized = float(text)
    except ValueError as exc:
        raise ValueError("Value must be numeric") from exc
    if not math.isfinite(normalized):
        raise ValueError("Value must be numeric")
    return normalized


class GroupResponse(GroupCreate):
    id: int
    cycleCount: int
    slotsRemaining: int
    currentCycleNo: int
    biddingEnabled: bool
    collectionClosed: bool = False
    currentMonthStatus: CurrentMonthStatus = CurrentMonthStatus.OPEN
    status: str


class GroupSettingsUpdate(BaseModel):
    commissionType: str
    auctionType: str


class GroupStatusResponse(BaseModel):
    collection_closed: bool
    status: CurrentMonthStatus
    paid_members: int
    total_members: int


class GroupMemberSummaryResponse(BaseModel):
    membershipId: int
    subscriberId: int
    memberNo: int
    memberName: str | None = None
    membershipStatus: str = "active"
    prizedStatus: str = "unprized"
    lastPaymentDate: date | None = None
    canBid: bool = True
    slotCount: int = 1
    wonSlotCount: int = 0
    remainingSlotCount: int = 1
    removeEligible: bool = False
    removeBlockedReason: str | None = None
    paid: int
    received: int
    dividend: int
    net: int


class MembershipCreate(BaseModel):
    subscriberId: int
    memberNo: int
    slotCount: int = 1


class MembershipResponse(MembershipCreate):
    id: int
    groupId: int
    membershipStatus: str
    prizedStatus: str
    canBid: bool
    slotCount: int = 1
    wonSlotCount: int = 0
    remainingSlotCount: int = 1


class JoinRequestCreate(BaseModel):
    slotCount: int = 1


class JoinRequestResponse(BaseModel):
    id: int
    groupId: int
    subscriberId: int
    subscriberName: str | None = None
    requestedSlotCount: int
    paymentScore: int | None = None
    status: str
    createdAt: datetime
    reviewedAt: datetime | None = None
    approvedMembershipId: int | None = None


class JoinRequestApprovalRequest(BaseModel):
    joinRequestId: int


class GroupInviteCandidateResponse(BaseModel):
    subscriberId: int
    userId: int
    fullName: str
    phone: str
    subscriberStatus: str
    membershipStatus: str | None = None
    inviteStatus: str | None = None
    inviteExpiresAt: datetime | None = None
    memberNo: int | None = None
    inviteEligible: bool
    note: str | None = None


class GroupInviteCreate(BaseModel):
    subscriberId: int


class GroupInviteResponse(BaseModel):
    inviteId: int
    membershipId: int
    groupId: int
    subscriberId: int
    subscriberName: str | None = None
    memberNo: int | None = None
    membershipStatus: str | None = None
    inviteStatus: str | None = None
    inviteExpiresAt: datetime | None = None
    requestedAt: datetime


class GroupInviteAuditResponse(BaseModel):
    inviteId: int
    groupId: int
    subscriberId: int
    subscriberName: str | None = None
    membershipId: int | None = None
    memberNo: int | None = None
    membershipStatus: str | None = None
    status: str
    issuedAt: datetime
    expiresAt: datetime | None = None
    acceptedAt: datetime | None = None
    revokedAt: datetime | None = None
    invitedByUserId: int
    revokedByUserId: int | None = None


class GroupMemberRemovalResponse(BaseModel):
    membershipId: int
    groupId: int
    subscriberId: int
    membershipStatus: str
    slotsReleased: int
    removedAt: datetime


class AuctionSessionCreate(BaseModel):
    cycleNo: int
    auctionMode: str = "LIVE"
    commissionMode: str = "NONE"
    commissionValue: int | None = None
    minBidValue: int | None = None
    maxBidValue: int | None = None
    minIncrement: int | None = None
    biddingWindowSeconds: int = 180
    startTime: datetime | None = None
    endTime: datetime | None = None
    allowWithPending: bool = Field(default=False, validation_alias=AliasChoices("allowWithPending", "allow_with_pending"))

    @field_validator("commissionValue", mode="before")
    @classmethod
    def _validate_commission_value(cls, value):
        return parse_whole_amount(value, allow_none=True)


class AuctionSessionResponse(BaseModel):
    id: int
    groupId: int
    cycleNo: int
    auctionMode: str
    commissionMode: str
    commissionValue: int | None = None
    minBidValue: int
    maxBidValue: int
    minIncrement: int
    status: str
    biddingWindowSeconds: int
    startTime: datetime | None = None
    endTime: datetime | None = None
