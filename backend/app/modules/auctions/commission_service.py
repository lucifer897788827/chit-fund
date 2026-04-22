from fastapi import HTTPException, status

from app.core.money import parse_whole_amount
from app.models.auction import AuctionSession
from app.models.chit import ChitGroup

COMMISSION_NONE = "NONE"
COMMISSION_FIRST_MONTH = "FIRST_MONTH"
COMMISSION_PERCENTAGE = "PERCENTAGE"
COMMISSION_FIXED_AMOUNT = "FIXED_AMOUNT"
ALLOWED_COMMISSION_MODES = {
    COMMISSION_NONE,
    COMMISSION_FIRST_MONTH,
    COMMISSION_PERCENTAGE,
    COMMISSION_FIXED_AMOUNT,
}


def normalize_commission_mode(value: str | None) -> str:
    normalized = (value or COMMISSION_NONE).strip().upper()
    if normalized not in ALLOWED_COMMISSION_MODES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid commission mode")
    return normalized


def normalize_commission_value(value) -> int | None:
    return parse_whole_amount(value, allow_none=True)


def validate_commission_config(
    *,
    mode: str | None,
    value,
    group: ChitGroup,
) -> tuple[str, int | None]:
    normalized_mode = normalize_commission_mode(mode)
    normalized_value = normalize_commission_value(value)

    if normalized_mode == COMMISSION_NONE:
        if normalized_value not in {None, 0}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Commission value must be empty for NONE mode",
            )
        return normalized_mode, None

    if normalized_mode == COMMISSION_FIRST_MONTH:
        if normalized_value not in {None, 0}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Commission value must be empty for FIRST_MONTH mode",
            )
        if int(group.installment_amount) <= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="FIRST_MONTH commission requires a positive installment amount",
            )
        return normalized_mode, None

    if normalized_value is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Commission value is required for this commission mode",
        )

    if normalized_mode == COMMISSION_PERCENTAGE:
        if normalized_value <= 0 or normalized_value > 100:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="PERCENTAGE commission must be greater than 0 and at most 100",
            )
        return normalized_mode, normalized_value

    if normalized_mode == COMMISSION_FIXED_AMOUNT:
        if normalized_value < 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="FIXED_AMOUNT commission cannot be negative",
            )
        if normalized_value > int(group.chit_value):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="FIXED_AMOUNT commission cannot exceed the chit value",
            )
        return normalized_mode, normalized_value

    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid commission mode")


def calculate_owner_commission_amount(
    *,
    session: AuctionSession,
    group: ChitGroup,
    winning_bid_amount: int,
) -> int:
    commission_mode = normalize_commission_mode(getattr(session, "commission_mode", None))
    commission_value = normalize_commission_value(getattr(session, "commission_value", None))

    if commission_mode == COMMISSION_NONE:
        return 0
    if commission_mode == COMMISSION_FIRST_MONTH:
        return int(group.installment_amount)
    if commission_mode == COMMISSION_PERCENTAGE:
        rate = commission_value or 0
        return (int(winning_bid_amount) * rate) // 100
    if commission_mode == COMMISSION_FIXED_AMOUNT:
        return min(commission_value or 0, int(winning_bid_amount))
    return 0
