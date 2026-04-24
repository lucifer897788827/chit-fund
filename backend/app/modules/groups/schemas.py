from datetime import date, datetime
import math
from typing import Any

from pydantic import BaseModel, field_validator, model_validator

from app.core.money import parse_whole_amount


class GroupCreate(BaseModel):
    ownerId: int
    groupCode: str
    title: str
    chitValue: int
    installmentAmount: int
    memberCount: int
    cycleCount: int
    cycleFrequency: str
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
    currentCycleNo: int
    biddingEnabled: bool
    status: str


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
