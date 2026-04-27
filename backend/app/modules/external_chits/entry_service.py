from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.money import money_int, parse_whole_amount
from app.core.pagination import PaginatedResponse, apply_pagination, build_paginated_response, count_statement, resolve_pagination
from app.core.security import CurrentUser
from app.models.external import ExternalChit, ExternalChitEntry
from app.models.user import Subscriber
from app.modules.external_chits.serializers import serialize_external_chit_entry
from app.modules.external_chits.validation import validate_external_chit_monthly_entry_payload
from app.modules.subscribers.service import ensure_subscriber_profile

ALLOWED_EXTERNAL_CHIT_ENTRY_TYPES = {"due", "paid", "won", "penalty", "note"}


@dataclass(slots=True)
class ExternalChitEntryContext:
    subscriber: Subscriber
    external_chit: ExternalChit


def _get_payload_value(payload, *names):
    for name in names:
        if isinstance(payload, dict) and name in payload:
            return payload[name]
        if hasattr(payload, name):
            return getattr(payload, name)
    return None


def _payload_has_field(payload, *names) -> bool:
    if isinstance(payload, dict):
        return any(name in payload for name in names)
    field_set = getattr(payload, "model_fields_set", None)
    if field_set is not None:
        return any(name in field_set for name in names)
    return any(hasattr(payload, name) for name in names)


def _resolve_external_chit_entry_context(
    db: Session,
    external_chit_id: int,
    current_user: CurrentUser,
) -> ExternalChitEntryContext:
    current_subscriber = ensure_subscriber_profile(db, current_user)

    external_chit = db.scalar(select(ExternalChit).where(ExternalChit.id == external_chit_id))
    if external_chit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External chit not found")

    chit_subscriber = db.scalar(select(Subscriber).where(Subscriber.id == external_chit.subscriber_id))
    if chit_subscriber is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External chit not found")

    if current_subscriber.id != chit_subscriber.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot access another subscriber's data")
    return ExternalChitEntryContext(subscriber=current_subscriber, external_chit=external_chit)


def _validate_external_chit_entry_payload(payload) -> tuple[str, date, int | None, str]:
    entry_type = _get_payload_value(payload, "entryType", "entry_type")
    if not isinstance(entry_type, str) or not entry_type.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Entry type is required")
    entry_type = entry_type.strip().lower()
    if entry_type not in ALLOWED_EXTERNAL_CHIT_ENTRY_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid entry type")

    entry_date = _get_payload_value(payload, "entryDate", "entry_date")
    if not isinstance(entry_date, date):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Entry date is required")
    if entry_date > date.today():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Entry date cannot be in the future")

    description = _get_payload_value(payload, "description")
    if not isinstance(description, str) or not description.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Description is required")
    description = description.strip()

    amount = _get_payload_value(payload, "amount")
    bid_amount = _get_payload_value(payload, "bidAmount", "bid_amount")
    has_monthly_ledger_fields = _payload_has_monthly_ledger_fields(payload)
    if entry_type == "note":
        if amount is not None:
            normalized_amount = parse_whole_amount(amount)
            if normalized_amount <= 0:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Amount must be positive")
        else:
            normalized_amount = None
    else:
        if amount is None and bid_amount is not None:
            amount = bid_amount
        if amount is None and has_monthly_ledger_fields:
            normalized_amount = None
        else:
            if amount is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Amount is required")
            normalized_amount = parse_whole_amount(amount)
            if normalized_amount <= 0:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Amount must be positive")

    return entry_type, entry_date, normalized_amount, description


def _payload_has_monthly_ledger_fields(payload) -> bool:
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


def _resolve_month_number(value) -> int | None:
    if value is None:
        return None
    return int(value)


def _validate_monthly_entry_sequence(
    db: Session,
    external_chit: ExternalChit,
    *,
    month_number: int | None,
    entry_id: int | None = None,
) -> None:
    if month_number is None:
        return

    if external_chit.total_months is not None and month_number > int(external_chit.total_months):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Month number cannot exceed total months",
        )

    existing_entries = db.scalars(
        select(ExternalChitEntry)
        .where(ExternalChitEntry.external_chit_id == external_chit.id, ExternalChitEntry.month_number.is_not(None))
        .order_by(ExternalChitEntry.month_number.asc(), ExternalChitEntry.id.asc())
    ).all()

    other_months: list[int] = []
    for existing_entry in existing_entries:
        if entry_id is not None and existing_entry.id == entry_id:
            continue
        if existing_entry.month_number is None:
            continue
        existing_month_number = int(existing_entry.month_number)
        if existing_month_number == month_number:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Month number already exists for this chit",
            )
        other_months.append(existing_month_number)

    if entry_id is None and other_months and month_number < max(other_months):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Month entries must be added in ascending order",
        )


def _apply_monthly_ledger_fields(entry: ExternalChitEntry, external_chit: ExternalChit, payload) -> None:
    from app.modules.external_chits.service import calculate_external_chit_month

    normalized_payload = validate_external_chit_monthly_entry_payload(payload)

    if normalized_payload["monthNumber"] is not None:
        entry.month_number = normalized_payload["monthNumber"]
    if normalized_payload["bidAmount"] is not None:
        entry.bid_amount = normalized_payload["bidAmount"]
    if normalized_payload["winnerType"] is not None:
        entry.winner_type = normalized_payload["winnerType"]
    if _get_payload_value(payload, "winnerName", "winner_name") is not None or normalized_payload["winnerType"] == "SELF":
        entry.winner_name = normalized_payload["winnerName"]

    entry.is_bid_overridden = normalized_payload["isBidOverridden"] or bool(entry.is_bid_overridden)
    entry.is_share_overridden = normalized_payload["isShareOverridden"] or bool(entry.is_share_overridden)
    entry.is_payable_overridden = normalized_payload["isPayableOverridden"] or bool(entry.is_payable_overridden)
    entry.is_payout_overridden = normalized_payload["isPayoutOverridden"] or bool(entry.is_payout_overridden)

    if _payload_has_field(payload, "sharePerSlot", "share_per_slot"):
        entry.share_per_slot = normalized_payload["sharePerSlot"]
    if _payload_has_field(payload, "myShare", "my_share"):
        entry.my_share = normalized_payload["myShare"]
    if _payload_has_field(payload, "myPayable", "my_payable"):
        entry.my_payable = normalized_payload["myPayable"]
    if _payload_has_field(payload, "myPayout", "my_payout"):
        entry.my_payout = normalized_payload["myPayout"]

    calculated = calculate_external_chit_month(entry, external_chit)
    entry.share_per_slot = calculated["sharePerSlot"]
    entry.my_share = calculated["myShare"]
    entry.my_payable = calculated["myPayable"]
    entry.my_payout = calculated["myPayout"]
    entry.is_bid_overridden = calculated["isBidOverridden"]
    entry.is_share_overridden = calculated["isShareOverridden"]
    entry.is_payable_overridden = calculated["isPayableOverridden"]
    entry.is_payout_overridden = calculated["isPayoutOverridden"]


def create_external_chit_entry(db: Session, payload, current_user: CurrentUser) -> dict:
    external_chit_id = _get_payload_value(payload, "externalChitId", "external_chit_id")
    if external_chit_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="External chit is required")

    context = _resolve_external_chit_entry_context(db, int(external_chit_id), current_user)
    entry_type, entry_date, amount, description = _validate_external_chit_entry_payload(payload)
    if _payload_has_monthly_ledger_fields(payload):
        _validate_monthly_entry_sequence(
            db,
            context.external_chit,
            month_number=_resolve_month_number(_get_payload_value(payload, "monthNumber", "month_number")),
        )

    entry = ExternalChitEntry(
        external_chit_id=context.external_chit.id,
        entry_type=entry_type,
        entry_date=entry_date,
        amount=amount,
        description=description,
    )
    if _payload_has_monthly_ledger_fields(payload):
        _apply_monthly_ledger_fields(entry, context.external_chit, payload)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return serialize_external_chit_entry(entry)


def update_external_chit_entry(db: Session, payload, current_user: CurrentUser) -> dict:
    external_chit_id = _get_payload_value(payload, "externalChitId", "external_chit_id")
    entry_id = _get_payload_value(payload, "entryId", "entry_id")
    if external_chit_id is None or entry_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="External chit entry is required")

    context = _resolve_external_chit_entry_context(db, int(external_chit_id), current_user)
    entry = db.scalar(
        select(ExternalChitEntry).where(
            ExternalChitEntry.id == int(entry_id),
            ExternalChitEntry.external_chit_id == context.external_chit.id,
        )
    )
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="External chit entry not found")

    if _payload_has_field(payload, "entryType", "entry_type"):
        entry_type = _get_payload_value(payload, "entryType", "entry_type")
        entry.entry_type = entry_type
    if _payload_has_field(payload, "entryDate", "entry_date"):
        entry_date = _get_payload_value(payload, "entryDate", "entry_date")
        entry.entry_date = entry_date
    if _payload_has_field(payload, "amount"):
        entry.amount = money_int(_get_payload_value(payload, "amount")) if _get_payload_value(payload, "amount") is not None else None
    if _payload_has_field(payload, "description"):
        description = _get_payload_value(payload, "description")
        entry.description = description

    if _payload_has_monthly_ledger_fields(payload):
        next_month_number = _resolve_month_number(_get_payload_value(payload, "monthNumber", "month_number"))
        if next_month_number is not None:
            _validate_monthly_entry_sequence(
                db,
                context.external_chit,
                month_number=next_month_number,
                entry_id=entry.id,
            )
        _apply_monthly_ledger_fields(entry, context.external_chit, payload)

    db.add(entry)
    db.commit()
    db.refresh(entry)
    return serialize_external_chit_entry(entry)


def list_external_chit_entries(
    db: Session,
    external_chit_id: int,
    current_user: CurrentUser,
    *,
    page: int | None = None,
    page_size: int | None = None,
) -> list[dict] | PaginatedResponse[dict]:
    context = _resolve_external_chit_entry_context(db, external_chit_id, current_user)
    statement = (
        select(ExternalChitEntry)
        .where(ExternalChitEntry.external_chit_id == context.external_chit.id)
        .order_by(ExternalChitEntry.entry_date.asc(), ExternalChitEntry.id.asc())
    )
    pagination = resolve_pagination(page, page_size)
    if pagination is None:
        entries = db.scalars(statement).all()
        return [serialize_external_chit_entry(entry) for entry in entries]

    total_count = count_statement(db, statement)
    entries = db.scalars(apply_pagination(statement, pagination)).all()
    return build_paginated_response([serialize_external_chit_entry(entry) for entry in entries], pagination, total_count)
