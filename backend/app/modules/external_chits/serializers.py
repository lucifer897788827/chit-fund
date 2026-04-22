from collections.abc import Iterable
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.external import ExternalChit, ExternalChitEntry


class _CamelCaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ExternalChitEntryResponse(_CamelCaseModel):
    id: int
    external_chit_id: int = Field(alias="externalChitId")
    month_number: int | None = Field(default=None, alias="monthNumber")
    bid_amount: int | None = Field(default=None, alias="bidAmount")
    winner_type: str | None = Field(default=None, alias="winnerType")
    winner_name: str | None = Field(default=None, alias="winnerName")
    share_per_slot: int | None = Field(default=None, alias="sharePerSlot")
    my_share: int | None = Field(default=None, alias="myShare")
    my_payable: int | None = Field(default=None, alias="myPayable")
    my_payout: int | None = Field(default=None, alias="myPayout")
    is_bid_overridden: bool = Field(default=False, alias="isBidOverridden")
    is_share_overridden: bool = Field(default=False, alias="isShareOverridden")
    is_payable_overridden: bool = Field(default=False, alias="isPayableOverridden")
    is_payout_overridden: bool = Field(default=False, alias="isPayoutOverridden")
    entry_type: str = Field(alias="entryType")
    entry_date: date = Field(alias="entryDate")
    amount: int | None = None
    description: str
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")


class ExternalChitResponse(_CamelCaseModel):
    id: int
    subscriber_id: int = Field(alias="subscriberId")
    user_id: int | None = Field(default=None, alias="userId")
    title: str
    name: str | None = None
    organizer_name: str = Field(alias="organizerName")
    chit_value: int = Field(alias="chitValue")
    installment_amount: int = Field(alias="installmentAmount")
    monthly_installment: int | None = Field(default=None, alias="monthlyInstallment")
    total_members: int | None = Field(default=None, alias="totalMembers")
    total_months: int | None = Field(default=None, alias="totalMonths")
    user_slots: int | None = Field(default=None, alias="userSlots")
    first_month_organizer: bool = Field(default=False, alias="firstMonthOrganizer")
    cycle_frequency: str = Field(alias="cycleFrequency")
    start_date: date = Field(alias="startDate")
    end_date: date | None = Field(default=None, alias="endDate")
    status: str
    notes: str | None = None


class ExternalChitDetailResponse(ExternalChitResponse):
    entry_history: list[ExternalChitEntryResponse] = Field(default_factory=list, alias="entryHistory")


class ExternalChitSummaryResponse(_CamelCaseModel):
    total_paid: int = Field(alias="totalPaid")
    total_received: int = Field(alias="totalReceived")
    profit: int
    winning_month: int | None = Field(default=None, alias="winningMonth")


def serialize_external_chit(chit: ExternalChit) -> dict:
    payload = {
        "id": chit.id,
        "subscriberId": chit.subscriber_id,
        "userId": chit.user_id,
        "title": chit.title,
        "name": chit.name,
        "organizerName": chit.organizer_name,
        "chitValue": chit.chit_value,
        "installmentAmount": chit.installment_amount,
        "monthlyInstallment": chit.monthly_installment,
        "totalMembers": chit.total_members,
        "totalMonths": chit.total_months,
        "userSlots": chit.user_slots,
        "firstMonthOrganizer": bool(chit.first_month_organizer),
        "cycleFrequency": chit.cycle_frequency,
        "startDate": chit.start_date,
        "endDate": chit.end_date,
        "status": chit.status,
        "notes": chit.notes,
    }
    return ExternalChitResponse.model_validate(payload).model_dump(by_alias=True)


def serialize_external_chit_entry(entry: ExternalChitEntry) -> dict:
    payload = {
        "id": entry.id,
        "externalChitId": entry.external_chit_id,
        "monthNumber": entry.month_number,
        "bidAmount": entry.bid_amount,
        "winnerType": entry.winner_type,
        "winnerName": entry.winner_name,
        "sharePerSlot": entry.share_per_slot,
        "myShare": entry.my_share,
        "myPayable": entry.my_payable,
        "myPayout": entry.my_payout,
        "isBidOverridden": bool(entry.is_bid_overridden),
        "isShareOverridden": bool(entry.is_share_overridden),
        "isPayableOverridden": bool(entry.is_payable_overridden),
        "isPayoutOverridden": bool(entry.is_payout_overridden),
        "entryType": entry.entry_type,
        "entryDate": entry.entry_date,
        "amount": entry.amount,
        "description": entry.description,
        "createdAt": entry.created_at,
        "updatedAt": entry.updated_at,
    }
    return ExternalChitEntryResponse.model_validate(payload).model_dump(by_alias=True)


def serialize_external_chit_entry_history(entries: Iterable[ExternalChitEntry]) -> list[dict]:
    return [serialize_external_chit_entry(entry) for entry in entries]


def serialize_external_chit_with_history(chit: ExternalChit, entries: Iterable[ExternalChitEntry]) -> dict:
    payload = ExternalChitDetailResponse.model_validate(
        {
            **serialize_external_chit(chit),
            "entryHistory": [serialize_external_chit_entry(entry) for entry in entries],
        }
    )
    return payload.model_dump(by_alias=True)


def serialize_external_chit_summary(
    *,
    total_paid: int,
    total_received: int,
    profit: int,
    winning_month: int | None,
) -> dict:
    payload = ExternalChitSummaryResponse.model_validate(
        {
            "totalPaid": total_paid,
            "totalReceived": total_received,
            "profit": profit,
            "winningMonth": winning_month,
        }
    )
    return payload.model_dump(by_alias=True)
