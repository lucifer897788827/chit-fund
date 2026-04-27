from datetime import date
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.money import WHOLE_AMOUNT_ERROR, parse_whole_amount
from app.core.security import CurrentUser, require_owner, require_subscriber
from app.models.external import ExternalChit, ExternalChitEntry
from app.models.user import Subscriber
from app.modules.external_chits.access_control import CHIT_PARTICIPANT_ROLES, is_chit_participant
from app.modules.subscribers.service import ensure_subscriber_profile

ALLOWED_EXTERNAL_CHIT_STATUSES = {"active", "inactive", "deleted", "paused", "closed", "completed"}
ALLOWED_EXTERNAL_CHIT_CYCLE_FREQUENCIES = {"weekly", "monthly", "quarterly", "yearly"}
ALLOWED_EXTERNAL_CHIT_ENTRY_TYPES = {"due", "paid", "won", "penalty", "note"}
ALLOWED_EXTERNAL_CHIT_WINNER_TYPES = {"SELF", "OTHER"}


def _payload_value(payload: Any, *names: str) -> Any:
    if isinstance(payload, dict):
        for name in names:
            if name in payload:
                return payload[name]
        return None

    for name in names:
        if hasattr(payload, name):
            return getattr(payload, name)
    return None


def _payload_has_field(payload: Any, *names: str) -> bool:
    if isinstance(payload, dict):
        return any(name in payload for name in names)
    field_set = getattr(payload, "model_fields_set", None)
    if field_set is not None:
        return any(name in field_set for name in names)
    return any(hasattr(payload, name) for name in names)


def _normalize_required_text(payload: Any, *names: str, field_name: str) -> str:
    value = _payload_value(payload, *names)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_name} is required")
    return value.strip()


def _normalize_optional_status(payload: Any) -> str:
    value = _payload_value(payload, "status")
    if value is None:
        return "active"
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Status is required")
    status_value = value.strip().lower()
    if status_value not in ALLOWED_EXTERNAL_CHIT_STATUSES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status")
    return status_value


def _normalize_cycle_frequency(payload: Any, *, field_name: str = "Cycle frequency") -> str:
    value = _payload_value(payload, "cycleFrequency", "cycle_frequency")
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_name} is required")
    cycle_frequency = value.strip().lower()
    if cycle_frequency not in ALLOWED_EXTERNAL_CHIT_CYCLE_FREQUENCIES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid cycle frequency")
    return cycle_frequency


def _normalize_positive_amount(payload: Any, *names: str, field_name: str) -> int:
    value = _payload_value(payload, *names)
    if value is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_name} is required")
    try:
        normalized_value = parse_whole_amount(value)
    except ValueError as exc:  # pragma: no cover - defensive conversion guard
        detail = WHOLE_AMOUNT_ERROR if str(exc) == WHOLE_AMOUNT_ERROR else f"{field_name} must be a whole number"
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail) from exc
    if normalized_value <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_name} must be positive")
    return normalized_value


def _normalize_optional_non_negative_int(payload: Any, *names: str, field_name: str) -> int | None:
    value = _payload_value(payload, *names)
    if value is None:
        return None
    if isinstance(value, bool):
        normalized_value = int(value)
    else:
        try:
            normalized_value = parse_whole_amount(value)
        except ValueError as exc:  # pragma: no cover - defensive conversion guard
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=WHOLE_AMOUNT_ERROR if str(exc) == WHOLE_AMOUNT_ERROR else f"{field_name} must be an integer",
            ) from exc
    if normalized_value < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{field_name} must be zero or more",
        )
    return normalized_value


def _normalize_optional_bool(payload: Any, *names: str) -> bool | None:
    value = _payload_value(payload, *names)
    if value is None:
        return None
    return bool(value)


def _normalize_date(payload: Any, *names: str, field_name: str) -> date:
    value = _payload_value(payload, *names)
    if not isinstance(value, date):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field_name} is required")
    return value


def _has_monthly_ledger_fields(payload: Any) -> bool:
    field_names = (
        "monthNumber",
        "month_number",
        "bidAmount",
        "bid_amount",
        "winnerType",
        "winner_type",
        "winnerName",
        "winner_name",
        "sharePerSlot",
        "share_per_slot",
        "myShare",
        "my_share",
        "myPayable",
        "my_payable",
        "myPayout",
        "my_payout",
        "isBidOverridden",
        "is_bid_overridden",
        "isShareOverridden",
        "is_share_overridden",
        "isPayableOverridden",
        "is_payable_overridden",
        "isPayoutOverridden",
        "is_payout_overridden",
    )
    return _payload_has_field(payload, *field_names)


def validate_external_chit_create_payload(payload: Any) -> dict:
    subscriber_id = _payload_value(payload, "subscriberId", "subscriber_id")
    if not isinstance(subscriber_id, int) or subscriber_id <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Subscriber is required")

    title = _normalize_required_text(payload, "title", field_name="Title")
    organizer_name = _normalize_required_text(payload, "organizerName", "organizer_name", field_name="Organizer name")
    chit_value = _normalize_positive_amount(payload, "chitValue", "chit_value", field_name="Chit value")
    installment_amount = _normalize_positive_amount(
        payload,
        "installmentAmount",
        "installment_amount",
        field_name="Installment amount",
    )
    cycle_frequency = _normalize_cycle_frequency(payload)
    start_date = _normalize_date(payload, "startDate", "start_date", field_name="Start date")
    end_date = _payload_value(payload, "endDate", "end_date")
    notes = _payload_value(payload, "notes")
    name = _payload_value(payload, "name")
    if isinstance(name, str):
        name = name.strip() or None
    monthly_installment = _normalize_optional_non_negative_int(
        payload, "monthlyInstallment", "monthly_installment", field_name="Monthly installment"
    )
    total_members = _normalize_optional_non_negative_int(
        payload, "totalMembers", "total_members", field_name="Total members"
    )
    total_months = _normalize_optional_non_negative_int(
        payload, "totalMonths", "total_months", field_name="Total months"
    )
    user_slots = _normalize_optional_non_negative_int(
        payload, "userSlots", "user_slots", field_name="User slots"
    )
    first_month_organizer = _normalize_optional_bool(payload, "firstMonthOrganizer", "first_month_organizer")
    if isinstance(notes, str):
        notes = notes.strip() or None
    status_value = _normalize_optional_status(payload)

    return {
        "subscriberId": subscriber_id,
        "title": title,
        "name": name,
        "organizerName": organizer_name,
        "chitValue": chit_value,
        "installmentAmount": installment_amount,
        "monthlyInstallment": monthly_installment,
        "totalMembers": total_members,
        "totalMonths": total_months,
        "userSlots": user_slots,
        "firstMonthOrganizer": bool(first_month_organizer) if first_month_organizer is not None else False,
        "cycleFrequency": cycle_frequency,
        "startDate": start_date,
        "endDate": end_date,
        "notes": notes,
        "status": status_value,
    }


def validate_external_chit_update_payload(payload: Any) -> dict:
    normalized: dict[str, Any] = {}

    if _payload_has_field(payload, "subscriberId", "subscriber_id"):
        subscriber_id = _payload_value(payload, "subscriberId", "subscriber_id")
        if not isinstance(subscriber_id, int) or subscriber_id <= 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Subscriber is required")
        normalized["subscriberId"] = subscriber_id

    if _payload_has_field(payload, "title"):
        normalized["title"] = _normalize_required_text(payload, "title", field_name="Title")

    if _payload_has_field(payload, "name"):
        name = _payload_value(payload, "name")
        if isinstance(name, str):
            name = name.strip() or None
        normalized["name"] = name

    if _payload_has_field(payload, "organizerName", "organizer_name"):
        normalized["organizerName"] = _normalize_required_text(
            payload,
            "organizerName",
            "organizer_name",
            field_name="Organizer name",
        )

    if _payload_has_field(payload, "chitValue", "chit_value"):
        normalized["chitValue"] = _normalize_positive_amount(payload, "chitValue", "chit_value", field_name="Chit value")

    if _payload_has_field(payload, "installmentAmount", "installment_amount"):
        normalized["installmentAmount"] = _normalize_positive_amount(
            payload,
            "installmentAmount",
            "installment_amount",
            field_name="Installment amount",
        )

    if _payload_has_field(payload, "monthlyInstallment", "monthly_installment"):
        normalized["monthlyInstallment"] = _normalize_optional_non_negative_int(
            payload, "monthlyInstallment", "monthly_installment", field_name="Monthly installment"
        )

    if _payload_has_field(payload, "totalMembers", "total_members"):
        normalized["totalMembers"] = _normalize_optional_non_negative_int(
            payload, "totalMembers", "total_members", field_name="Total members"
        )

    if _payload_has_field(payload, "totalMonths", "total_months"):
        normalized["totalMonths"] = _normalize_optional_non_negative_int(
            payload, "totalMonths", "total_months", field_name="Total months"
        )

    if _payload_has_field(payload, "userSlots", "user_slots"):
        normalized["userSlots"] = _normalize_optional_non_negative_int(
            payload, "userSlots", "user_slots", field_name="User slots"
        )

    if _payload_has_field(payload, "firstMonthOrganizer", "first_month_organizer"):
        first_month_organizer = _payload_value(payload, "firstMonthOrganizer", "first_month_organizer")
        normalized["firstMonthOrganizer"] = bool(first_month_organizer)

    if _payload_has_field(payload, "cycleFrequency", "cycle_frequency"):
        normalized["cycleFrequency"] = _normalize_cycle_frequency(payload)

    if _payload_has_field(payload, "startDate", "start_date"):
        normalized["startDate"] = _normalize_date(payload, "startDate", "start_date", field_name="Start date")

    if _payload_has_field(payload, "endDate", "end_date"):
        normalized["endDate"] = _payload_value(payload, "endDate", "end_date")

    if _payload_has_field(payload, "notes"):
        notes = _payload_value(payload, "notes")
        if isinstance(notes, str):
            notes = notes.strip() or None
        normalized["notes"] = notes

    if _payload_has_field(payload, "status"):
        normalized["status"] = _normalize_optional_status(payload)

    return normalized


def validate_external_chit_entry_payload(payload: Any) -> dict:
    entry_type = _normalize_required_text(payload, "entryType", "entry_type", field_name="Entry type").lower()
    if entry_type not in ALLOWED_EXTERNAL_CHIT_ENTRY_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid entry type")

    entry_date = _normalize_date(payload, "entryDate", "entry_date", field_name="Entry date")
    description = _normalize_required_text(payload, "description", field_name="Description")

    amount_value = _payload_value(payload, "amount")
    bid_amount_value = _payload_value(payload, "bidAmount", "bid_amount")
    has_monthly_ledger_fields = _has_monthly_ledger_fields(payload)
    if entry_type == "note":
        amount = None
        if amount_value is not None:
            amount = _normalize_positive_amount(payload, "amount", field_name="Amount")
    else:
        if amount_value is not None:
            amount = _normalize_positive_amount(payload, "amount", field_name="Amount")
        elif bid_amount_value is not None:
            amount = _normalize_positive_amount(payload, "bidAmount", "bid_amount", field_name="Bid amount")
        elif has_monthly_ledger_fields:
            amount = None
        else:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Amount is required")

    return {
        "entryType": entry_type,
        "entryDate": entry_date,
        "amount": amount,
        "description": description,
    }


def validate_external_chit_monthly_entry_payload(payload: Any) -> dict:
    month_number = _normalize_optional_non_negative_int(payload, "monthNumber", "month_number", field_name="Month number")
    if month_number == 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Month number must be at least 1")

    bid_amount = _normalize_optional_non_negative_int(payload, "bidAmount", "bid_amount", field_name="Bid amount")
    share_per_slot = _normalize_optional_non_negative_int(payload, "sharePerSlot", "share_per_slot", field_name="Share per slot")
    my_share = _normalize_optional_non_negative_int(payload, "myShare", "my_share", field_name="My share")
    my_payable = _normalize_optional_non_negative_int(payload, "myPayable", "my_payable", field_name="My payable")
    my_payout = _normalize_optional_non_negative_int(payload, "myPayout", "my_payout", field_name="My payout")

    winner_type_raw = _payload_value(payload, "winnerType", "winner_type")
    winner_type = None
    if winner_type_raw is not None:
        if not isinstance(winner_type_raw, str) or not winner_type_raw.strip():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Winner type is required")
        winner_type = winner_type_raw.strip().upper()
        if winner_type not in ALLOWED_EXTERNAL_CHIT_WINNER_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid winner type")

    winner_name = _payload_value(payload, "winnerName", "winner_name")
    if isinstance(winner_name, str):
        winner_name = winner_name.strip() or None
    if winner_type == "SELF":
        winner_name = None

    explicit_bid_override = _normalize_optional_bool(payload, "isBidOverridden", "is_bid_overridden")
    explicit_share_override = _normalize_optional_bool(payload, "isShareOverridden", "is_share_overridden")
    explicit_payable_override = _normalize_optional_bool(payload, "isPayableOverridden", "is_payable_overridden")
    explicit_payout_override = _normalize_optional_bool(payload, "isPayoutOverridden", "is_payout_overridden")

    if explicit_share_override and share_per_slot is None and my_share is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Share override requires a manual share value",
        )
    if explicit_payable_override and my_payable is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Payable override requires a manual payable value",
        )
    if explicit_payout_override and my_payout is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Payout override requires a manual payout value",
        )
    if explicit_bid_override and bid_amount is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Bid override requires a manual bid amount",
        )

    is_bid_overridden = bool(explicit_bid_override) or bid_amount is not None
    is_share_overridden = bool(explicit_share_override) or share_per_slot is not None or my_share is not None
    is_payable_overridden = bool(explicit_payable_override) or my_payable is not None
    is_payout_overridden = bool(explicit_payout_override) or my_payout is not None

    return {
        "monthNumber": month_number,
        "bidAmount": bid_amount,
        "winnerType": winner_type,
        "winnerName": winner_name,
        "sharePerSlot": share_per_slot,
        "myShare": my_share,
        "myPayable": my_payable,
        "myPayout": my_payout,
        "isBidOverridden": is_bid_overridden,
        "isShareOverridden": is_share_overridden,
        "isPayableOverridden": is_payable_overridden,
        "isPayoutOverridden": is_payout_overridden,
    }


def validate_external_chit_entry_update_payload(payload: Any) -> dict:
    normalized: dict[str, Any] = {}

    if _payload_has_field(payload, "entryType", "entry_type"):
        entry_type = _normalize_required_text(payload, "entryType", "entry_type", field_name="Entry type").lower()
        if entry_type not in ALLOWED_EXTERNAL_CHIT_ENTRY_TYPES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid entry type")
        normalized["entryType"] = entry_type

    if _payload_has_field(payload, "entryDate", "entry_date"):
        entry_date = _normalize_date(payload, "entryDate", "entry_date", field_name="Entry date")
        if entry_date > date.today():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Entry date cannot be in the future")
        normalized["entryDate"] = entry_date

    if _payload_has_field(payload, "description"):
        normalized["description"] = _normalize_required_text(payload, "description", field_name="Description")

    if _payload_has_field(payload, "amount"):
        amount = _payload_value(payload, "amount")
        if amount is None:
            normalized["amount"] = None
        else:
            normalized["amount"] = _normalize_positive_amount(payload, "amount", field_name="Amount")

    monthly_fields = (
        "monthNumber",
        "month_number",
        "bidAmount",
        "bid_amount",
        "winnerType",
        "winner_type",
        "winnerName",
        "winner_name",
        "sharePerSlot",
        "share_per_slot",
        "myShare",
        "my_share",
        "myPayable",
        "my_payable",
        "myPayout",
        "my_payout",
        "isBidOverridden",
        "is_bid_overridden",
        "isShareOverridden",
        "is_share_overridden",
        "isPayableOverridden",
        "is_payable_overridden",
        "isPayoutOverridden",
        "is_payout_overridden",
    )
    if _payload_has_field(payload, *monthly_fields):
        normalized.update(validate_external_chit_monthly_entry_payload(payload))
    return normalized


def _require_subscriber_for_current_user(db: Session, current_user: CurrentUser, subscriber_id: int) -> Subscriber:
    if current_user.owner is not None and current_user.user.role in CHIT_PARTICIPANT_ROLES:
        ensure_subscriber_profile(db, current_user)
        owner = require_owner(current_user)
        subscriber = db.get(Subscriber, subscriber_id)
        if subscriber is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")
        if subscriber.owner_id != owner.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot manage another owner's subscriber",
            )
        return subscriber

    if is_chit_participant(current_user):
        current_subscriber = require_subscriber(current_user)
        if current_subscriber.id != subscriber_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot access another subscriber's data",
            )
        return current_subscriber

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="External chit participant access required")


def require_external_chit_access(db: Session, current_user: CurrentUser, external_chit_id: int) -> ExternalChit:
    external_chit = db.get(ExternalChit, external_chit_id)
    if external_chit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External chit not found")

    _require_subscriber_for_current_user(db, current_user, external_chit.subscriber_id)
    return external_chit


def require_external_chit_entry_access(
    db: Session,
    current_user: CurrentUser,
    external_chit_entry_id: int,
) -> ExternalChitEntry:
    entry = db.get(ExternalChitEntry, external_chit_entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External chit entry not found")

    external_chit = db.get(ExternalChit, entry.external_chit_id)
    if external_chit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External chit not found")

    _require_subscriber_for_current_user(db, current_user, external_chit.subscriber_id)
    return entry
