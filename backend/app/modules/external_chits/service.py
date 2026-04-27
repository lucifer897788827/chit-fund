from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.money import money_int, money_int_or_none
from app.core.security import CurrentUser
from app.models.external import ExternalChit, ExternalChitEntry
from app.modules.external_chits.access_control import require_external_chit_participant
from app.modules.external_chits.crud_service import (
    create_external_chit as create_external_chit_record,
    delete_external_chit as delete_external_chit_record,
    list_external_chits as list_external_chit_records,
    update_external_chit as update_external_chit_record,
)
from app.modules.subscribers.service import ensure_subscriber_profile
from app.modules.external_chits.entry_service import (
    create_external_chit_entry as create_external_chit_entry_record,
    list_external_chit_entries,
    update_external_chit_entry as update_external_chit_entry_record,
)
from app.modules.external_chits.serializers import serialize_external_chit_with_history
from app.modules.external_chits.validation import (
    require_external_chit_access,
    validate_external_chit_create_payload,
    validate_external_chit_entry_payload,
    validate_external_chit_entry_update_payload,
    validate_external_chit_monthly_entry_payload,
    validate_external_chit_update_payload,
)


def _payload_value(payload, *names):
    for name in names:
        if isinstance(payload, dict) and name in payload:
            return payload[name]
        if hasattr(payload, name):
            return getattr(payload, name)
    return None


def _normalize_optional_int(value) -> int | None:
    return money_int_or_none(value)


def _normalize_bool(value) -> bool:
    return bool(value)


def _resolve_chit_monthly_installment(chit) -> int:
    monthly_installment = _normalize_optional_int(
        _payload_value(chit, "monthly_installment", "monthlyInstallment")
    )
    if monthly_installment is not None:
        return monthly_installment
    fallback_installment = _normalize_optional_int(
        _payload_value(chit, "installment_amount", "installmentAmount")
    )
    if fallback_installment is None:
        raise ValueError("External chit monthly installment is required for calculation")
    return fallback_installment


def _resolve_chit_total_members(chit, *, monthly_installment: int) -> int:
    total_members = _normalize_optional_int(_payload_value(chit, "total_members", "totalMembers"))
    if total_members is not None:
        return total_members

    chit_value = _normalize_optional_int(_payload_value(chit, "chit_value", "chitValue"))
    if chit_value is None or monthly_installment <= 0 or chit_value % monthly_installment != 0:
        raise ValueError("External chit total members is required for calculation")
    return chit_value // monthly_installment


def _resolve_chit_user_slots(chit) -> int:
    user_slots = _normalize_optional_int(_payload_value(chit, "user_slots", "userSlots"))
    return user_slots if user_slots is not None else 1


def _preserve_or_compute(existing_value, computed_value, *, is_overridden: bool) -> int:
    if is_overridden and existing_value is not None:
        return existing_value
    return computed_value


def calculate_external_chit_month(entry, chit) -> dict[str, int | str | None | bool]:
    monthly_installment = _resolve_chit_monthly_installment(chit)
    total_members = _resolve_chit_total_members(chit, monthly_installment=monthly_installment)
    user_slots = _resolve_chit_user_slots(chit)
    month_number = _normalize_optional_int(_payload_value(entry, "month_number", "monthNumber"))
    bid_amount = _normalize_optional_int(_payload_value(entry, "bid_amount", "bidAmount"))
    winner_type_value = _payload_value(entry, "winner_type", "winnerType")
    winner_type = winner_type_value.strip().upper() if isinstance(winner_type_value, str) and winner_type_value.strip() else None
    first_month_organizer = _normalize_bool(
        _payload_value(chit, "first_month_organizer", "firstMonthOrganizer")
    )
    chit_value = monthly_installment * total_members

    existing_share_per_slot = _normalize_optional_int(_payload_value(entry, "share_per_slot", "sharePerSlot"))
    existing_my_share = _normalize_optional_int(_payload_value(entry, "my_share", "myShare"))
    existing_my_payable = _normalize_optional_int(_payload_value(entry, "my_payable", "myPayable"))
    existing_my_payout = _normalize_optional_int(_payload_value(entry, "my_payout", "myPayout"))

    is_share_overridden = _normalize_bool(_payload_value(entry, "is_share_overridden", "isShareOverridden"))
    is_payable_overridden = _normalize_bool(_payload_value(entry, "is_payable_overridden", "isPayableOverridden"))
    is_payout_overridden = _normalize_bool(_payload_value(entry, "is_payout_overridden", "isPayoutOverridden"))
    is_bid_overridden = _normalize_bool(_payload_value(entry, "is_bid_overridden", "isBidOverridden"))

    if month_number == 1 and first_month_organizer:
        computed_share_per_slot = 0
        computed_my_share = 0
        computed_my_payable = monthly_installment * user_slots
        computed_my_payout = 0
    elif bid_amount is None:
        computed_share_per_slot = existing_share_per_slot or 0
        computed_my_share = existing_my_share or 0
        computed_my_payable = existing_my_payable or 0
        computed_my_payout = existing_my_payout or 0
    else:
        computed_share_per_slot = bid_amount // total_members
        computed_my_share = computed_share_per_slot * user_slots

        effective_share_per_slot = _preserve_or_compute(
            existing_share_per_slot,
            computed_share_per_slot,
            is_overridden=is_share_overridden,
        )
        effective_my_share = _preserve_or_compute(
            existing_my_share,
            computed_my_share,
            is_overridden=is_share_overridden,
        )

        computed_my_payable = (monthly_installment * user_slots) - effective_my_share
        if winner_type == "SELF":
            payout = chit_value - bid_amount
            computed_my_payout = payout - (monthly_installment * user_slots) + effective_my_share
        else:
            computed_my_payout = 0

        computed_share_per_slot = effective_share_per_slot
        computed_my_share = effective_my_share

    share_per_slot = _preserve_or_compute(
        existing_share_per_slot,
        computed_share_per_slot,
        is_overridden=is_share_overridden,
    )
    my_share = _preserve_or_compute(
        existing_my_share,
        computed_my_share,
        is_overridden=is_share_overridden,
    )
    my_payable = _preserve_or_compute(
        existing_my_payable,
        computed_my_payable,
        is_overridden=is_payable_overridden,
    )
    my_payout = _preserve_or_compute(
        existing_my_payout,
        computed_my_payout,
        is_overridden=is_payout_overridden,
    )

    return {
        "monthNumber": month_number,
        "bidAmount": bid_amount,
        "winnerType": winner_type,
        "sharePerSlot": int(share_per_slot),
        "myShare": int(my_share),
        "myPayable": int(my_payable),
        "myPayout": int(my_payout),
        "isBidOverridden": is_bid_overridden,
        "isShareOverridden": is_share_overridden,
        "isPayableOverridden": is_payable_overridden,
        "isPayoutOverridden": is_payout_overridden,
        "monthlyInstallment": monthly_installment,
        "totalMembers": total_members,
        "userSlots": user_slots,
        "chitValue": chit_value,
    }


def list_external_chits(
    db: Session,
    current_user: CurrentUser,
    *,
    page: int | None = None,
    page_size: int | None = None,
):
    subscriber = ensure_subscriber_profile(db, current_user)
    return list_external_chit_records(db, current_user, subscriber.id, page=page, page_size=page_size)


def create_external_chit(db: Session, payload, current_user: CurrentUser):
    subscriber = ensure_subscriber_profile(db, current_user)
    payload_data = {
        "subscriberId": subscriber.id,
        "title": payload.title,
        "name": getattr(payload, "name", None),
        "organizerName": payload.organizerName,
        "chitValue": payload.chitValue,
        "installmentAmount": payload.installmentAmount,
        "monthlyInstallment": getattr(payload, "monthlyInstallment", None),
        "totalMembers": getattr(payload, "totalMembers", None),
        "totalMonths": getattr(payload, "totalMonths", None),
        "userSlots": getattr(payload, "userSlots", None),
        "firstMonthOrganizer": getattr(payload, "firstMonthOrganizer", None),
        "cycleFrequency": payload.cycleFrequency,
        "startDate": payload.startDate,
        "endDate": getattr(payload, "endDate", None),
        "notes": getattr(payload, "notes", None),
        "status": getattr(payload, "status", None),
    }
    validated_payload = validate_external_chit_create_payload(payload_data)
    normalized_payload = type("ExternalChitPayload", (), validated_payload)()
    return create_external_chit_record(db, normalized_payload, current_user)


def get_external_chit_detail(db: Session, chit_id: int, current_user: CurrentUser):
    external_chit = require_external_chit_access(db, current_user, chit_id)
    entries = db.scalars(
        select(ExternalChitEntry)
        .where(ExternalChitEntry.external_chit_id == external_chit.id)
        .order_by(ExternalChitEntry.entry_date.asc(), ExternalChitEntry.id.asc())
    ).all()
    return serialize_external_chit_with_history(external_chit, entries)


def get_external_chit_summary(db: Session, chit_id: int, current_user: CurrentUser):
    from app.modules.external_chits.serializers import serialize_external_chit_summary

    external_chit = require_external_chit_access(db, current_user, chit_id)
    entries = db.scalars(
        select(ExternalChitEntry)
        .where(ExternalChitEntry.external_chit_id == external_chit.id)
        .order_by(ExternalChitEntry.entry_date.asc(), ExternalChitEntry.id.asc())
    ).all()

    total_paid = sum(_normalize_optional_int(entry.my_payable) or 0 for entry in entries)
    total_received = sum((_normalize_optional_int(entry.my_share) or 0) + (_normalize_optional_int(entry.my_payout) or 0) for entry in entries)
    profit = total_received - total_paid

    winning_entry = min(
        (
            entry
            for entry in entries
            if isinstance(entry.winner_type, str) and entry.winner_type.strip().upper() == "SELF"
        ),
        key=lambda entry: (
            entry.month_number is None,
            entry.month_number if entry.month_number is not None else 10**9,
            entry.entry_date,
            entry.id,
        ),
        default=None,
    )
    winning_month = _normalize_optional_int(winning_entry.month_number) if winning_entry is not None else None

    return serialize_external_chit_summary(
        total_paid=int(total_paid),
        total_received=int(total_received),
        profit=int(profit),
        winning_month=winning_month,
    )


def update_external_chit(db: Session, chit_id: int, payload, current_user: CurrentUser):
    validated_payload = validate_external_chit_update_payload(payload)
    normalized_payload = type("ExternalChitUpdatePayload", (), validated_payload)()
    return update_external_chit_record(db, chit_id, normalized_payload, current_user)


def delete_external_chit(db: Session, chit_id: int, current_user: CurrentUser):
    return delete_external_chit_record(db, chit_id, current_user)


def list_external_chit_history(
    db: Session,
    chit_id: int,
    current_user: CurrentUser,
    *,
    page: int | None = None,
    page_size: int | None = None,
):
    return list_external_chit_entries(db, chit_id, current_user, page=page, page_size=page_size)


def create_external_chit_history_entry(db: Session, chit_id: int, payload, current_user: CurrentUser):
    validated_payload = validate_external_chit_entry_payload(payload)
    validated_payload.update(validate_external_chit_monthly_entry_payload(payload))
    validated_payload["externalChitId"] = chit_id
    normalized_payload = type("ExternalChitEntryPayload", (), validated_payload)()
    return create_external_chit_entry_record(db, normalized_payload, current_user)


def update_external_chit_history_entry(db: Session, chit_id: int, entry_id: int, payload, current_user: CurrentUser):
    validated_payload = validate_external_chit_entry_update_payload(payload)
    validated_payload["externalChitId"] = chit_id
    validated_payload["entryId"] = entry_id
    normalized_payload = type("ExternalChitEntryUpdatePayload", (), validated_payload)()
    return update_external_chit_entry_record(db, normalized_payload, current_user)
