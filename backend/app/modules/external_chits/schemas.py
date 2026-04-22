from datetime import date

from pydantic import BaseModel, field_validator

from app.core.money import parse_whole_amount

from app.modules.external_chits.serializers import (
    ExternalChitDetailResponse,
    ExternalChitEntryResponse,
    ExternalChitResponse,
    ExternalChitSummaryResponse,
)


class ExternalChitCreate(BaseModel):
    subscriberId: int | None = None
    title: str
    name: str | None = None
    organizerName: str
    chitValue: int
    installmentAmount: int
    monthlyInstallment: int | None = None
    totalMembers: int | None = None
    totalMonths: int | None = None
    userSlots: int | None = None
    firstMonthOrganizer: bool | None = None
    cycleFrequency: str
    startDate: date
    endDate: date | None = None
    notes: str | None = None
    status: str | None = None

    @field_validator("chitValue", "installmentAmount", mode="before")
    @classmethod
    def _validate_amounts(cls, value):
        return parse_whole_amount(value)


class ExternalChitUpdate(BaseModel):
    subscriberId: int | None = None
    title: str | None = None
    name: str | None = None
    organizerName: str | None = None
    chitValue: int | None = None
    installmentAmount: int | None = None
    monthlyInstallment: int | None = None
    totalMembers: int | None = None
    totalMonths: int | None = None
    userSlots: int | None = None
    firstMonthOrganizer: bool | None = None
    cycleFrequency: str | None = None
    startDate: date | None = None
    endDate: date | None = None
    notes: str | None = None
    status: str | None = None

    @field_validator("chitValue", "installmentAmount", mode="before")
    @classmethod
    def _validate_amounts(cls, value):
        return parse_whole_amount(value, allow_none=True)


class ExternalChitEntryCreate(BaseModel):
    entryType: str
    entryDate: date
    amount: int | None = None
    description: str
    monthNumber: int | None = None
    bidAmount: int | None = None
    winnerType: str | None = None
    winnerName: str | None = None
    sharePerSlot: int | None = None
    myShare: int | None = None
    myPayable: int | None = None
    myPayout: int | None = None
    isBidOverridden: bool | None = None
    isShareOverridden: bool | None = None
    isPayableOverridden: bool | None = None
    isPayoutOverridden: bool | None = None

    @field_validator("amount", "bidAmount", "sharePerSlot", "myShare", "myPayable", "myPayout", mode="before")
    @classmethod
    def _validate_money_fields(cls, value):
        return parse_whole_amount(value, allow_none=True)


class ExternalChitEntryUpdate(ExternalChitEntryCreate):
    entryType: str | None = None
    entryDate: date | None = None
    amount: int | None = None
    description: str | None = None


__all__ = [
    "ExternalChitCreate",
    "ExternalChitDetailResponse",
    "ExternalChitEntryCreate",
    "ExternalChitEntryUpdate",
    "ExternalChitResponse",
    "ExternalChitEntryResponse",
    "ExternalChitSummaryResponse",
    "ExternalChitUpdate",
]
