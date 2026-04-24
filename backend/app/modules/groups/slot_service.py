from dataclasses import dataclass

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.chit import ChitGroup, GroupMembership, MembershipSlot
from app.models.user import Subscriber


@dataclass(frozen=True, slots=True)
class MembershipSlotSummary:
    total_slots: int
    won_slots: int
    available_slots: int
    can_bid: bool
    has_any_won: bool


def _resolve_membership_user_id(db: Session, membership: GroupMembership) -> int:
    user_id = db.scalar(
        select(Subscriber.user_id).where(Subscriber.id == membership.subscriber_id)
    )
    if user_id is None:
        raise ValueError(f"Subscriber {membership.subscriber_id} does not exist for membership {membership.id}")
    return int(user_id)


def _get_slot_count_breakdown(db: Session, *, group_id: int, user_id: int) -> tuple[int, int]:
    total_slots, available_slots = db.execute(
        select(
            func.count(MembershipSlot.id),
            func.coalesce(
                func.sum(
                    case(
                        (MembershipSlot.has_won.is_(False), 1),
                        else_=0,
                    )
                ),
                0,
            ),
        ).where(
            MembershipSlot.group_id == group_id,
            MembershipSlot.user_id == user_id,
        )
    ).one()
    return int(total_slots or 0), int(available_slots or 0)


def _apply_membership_slot_state(
    membership: GroupMembership,
    *,
    total_slots: int,
    available_slots: int,
    prized_cycle_no: int | None = None,
) -> MembershipSlotSummary:
    if total_slots <= 0:
        has_any_won = membership.prized_status == "prized"
        available_slots = 0 if has_any_won else 1
        can_bid = membership.membership_status == "active" and membership.can_bid and not has_any_won
        summary = MembershipSlotSummary(
            total_slots=1,
            won_slots=1 if has_any_won else 0,
            available_slots=available_slots,
            can_bid=can_bid,
            has_any_won=has_any_won,
        )
        membership.can_bid = summary.can_bid
        membership.prized_status = "prized" if summary.has_any_won else "unprized"
        membership.prized_cycle_no = prized_cycle_no if summary.has_any_won else None
        return summary

    won_slots = max(total_slots - available_slots, 0)
    has_any_won = won_slots > 0
    can_bid = membership.membership_status == "active" and available_slots > 0
    summary = MembershipSlotSummary(
        total_slots=total_slots,
        won_slots=won_slots,
        available_slots=available_slots,
        can_bid=can_bid,
        has_any_won=has_any_won,
    )
    membership.can_bid = summary.can_bid
    membership.prized_status = "prized" if summary.has_any_won else "unprized"
    membership.prized_cycle_no = prized_cycle_no if summary.has_any_won else None
    return summary


def _list_group_slot_numbers(db: Session, *, group_id: int) -> set[int]:
    slot_numbers = db.scalars(
        select(MembershipSlot.slot_number).where(MembershipSlot.group_id == group_id)
    ).all()
    return {int(slot_number) for slot_number in slot_numbers}


def _build_slot_numbers_to_allocate(
    *,
    used_slot_numbers: set[int],
    maximum_slot_number: int,
    requested_slot_count: int,
    preferred_slot_numbers: list[int] | None = None,
) -> list[int]:
    slot_numbers: list[int] = []
    for slot_number in preferred_slot_numbers or []:
        if len(slot_numbers) >= requested_slot_count:
            break
        normalized_slot_number = int(slot_number)
        if normalized_slot_number < 1 or normalized_slot_number > maximum_slot_number:
            continue
        if normalized_slot_number in used_slot_numbers:
            continue
        slot_numbers.append(normalized_slot_number)
        used_slot_numbers.add(normalized_slot_number)

    candidate = 1
    while len(slot_numbers) < requested_slot_count and candidate <= maximum_slot_number:
        if candidate not in used_slot_numbers:
            slot_numbers.append(candidate)
            used_slot_numbers.add(candidate)
        candidate += 1
    return slot_numbers


def create_membership_slots(
    db: Session,
    membership: GroupMembership,
    *,
    slot_count: int,
    preferred_slot_numbers: list[int] | None = None,
) -> list[MembershipSlot]:
    user_id = _resolve_membership_user_id(db, membership)
    group = db.scalar(select(ChitGroup).where(ChitGroup.id == membership.group_id))
    if group is None:
        raise ValueError(f"Group {membership.group_id} does not exist for membership {membership.id}")

    used_slot_numbers = _list_group_slot_numbers(db, group_id=membership.group_id)
    slot_numbers = _build_slot_numbers_to_allocate(
        used_slot_numbers=used_slot_numbers,
        maximum_slot_number=int(group.member_count),
        requested_slot_count=int(slot_count),
        preferred_slot_numbers=preferred_slot_numbers,
    )
    created_slots: list[MembershipSlot] = []
    for slot_number in slot_numbers:
        slot = MembershipSlot(
            user_id=user_id,
            group_id=membership.group_id,
            slot_number=slot_number,
            has_won=membership.prized_status == "prized",
        )
        db.add(slot)
        created_slots.append(slot)
    if created_slots:
        db.flush()
    return created_slots


def ensure_membership_slot(db: Session, membership: GroupMembership, *, user_id: int | None = None) -> MembershipSlot:
    resolved_user_id = int(user_id) if user_id is not None else _resolve_membership_user_id(db, membership)
    slot = db.scalar(
        select(MembershipSlot).where(
            MembershipSlot.group_id == membership.group_id,
            MembershipSlot.user_id == resolved_user_id,
            MembershipSlot.slot_number == membership.member_no,
        )
    )
    if slot is None:
        created_slots = create_membership_slots(
            db,
            membership,
            slot_count=1,
            preferred_slot_numbers=[membership.member_no],
        )
        if not created_slots:
            raise ValueError(
                f"Unable to allocate a slot for membership {membership.id} in group {membership.group_id}"
            )
        slot = created_slots[0]
    elif membership.prized_status == "prized" and not slot.has_won:
        slot.has_won = True
        db.flush()
    return slot


def get_user_slot_count(db: Session, *, group_id: int, user_id: int) -> int:
    count = db.scalar(
        select(func.count(MembershipSlot.id)).where(
            MembershipSlot.group_id == group_id,
            MembershipSlot.user_id == user_id,
        )
    )
    return int(count or 0)


def get_user_available_slot_count(db: Session, *, group_id: int, user_id: int) -> int:
    count = db.scalar(
        select(func.count(MembershipSlot.id)).where(
            MembershipSlot.group_id == group_id,
            MembershipSlot.user_id == user_id,
            MembershipSlot.has_won.is_(False),
        )
    )
    return int(count or 0)


def build_membership_slot_summary(db: Session, membership: GroupMembership) -> MembershipSlotSummary:
    user_id = _resolve_membership_user_id(db, membership)
    total_slots, available_slots = _get_slot_count_breakdown(
        db,
        group_id=membership.group_id,
        user_id=user_id,
    )
    return _apply_membership_slot_state(
        membership,
        total_slots=total_slots,
        available_slots=available_slots,
        prized_cycle_no=membership.prized_cycle_no,
    )


def sync_membership_slot_state(db: Session, membership: GroupMembership) -> MembershipSlotSummary:
    user_id = _resolve_membership_user_id(db, membership)
    total_slots, available_slots = _get_slot_count_breakdown(
        db,
        group_id=membership.group_id,
        user_id=user_id,
    )
    summary = _apply_membership_slot_state(
        membership,
        total_slots=total_slots,
        available_slots=available_slots,
        prized_cycle_no=membership.prized_cycle_no,
    )
    db.flush()
    return summary


def get_membership_bid_eligibility(db: Session, membership: GroupMembership) -> bool:
    return build_membership_slot_summary(db, membership).can_bid


def mark_membership_slot_won(
    db: Session,
    membership: GroupMembership,
    *,
    cycle_no: int | None = None,
) -> MembershipSlot:
    user_id = _resolve_membership_user_id(db, membership)
    slot = db.scalar(
        select(MembershipSlot)
        .where(
            MembershipSlot.group_id == membership.group_id,
            MembershipSlot.user_id == user_id,
            MembershipSlot.has_won.is_(False),
        )
        .order_by(MembershipSlot.slot_number.asc(), MembershipSlot.id.asc())
    )
    if slot is None:
        ensure_membership_slot(db, membership, user_id=user_id)
        slot = db.scalar(
            select(MembershipSlot)
            .where(
                MembershipSlot.group_id == membership.group_id,
                MembershipSlot.user_id == user_id,
                MembershipSlot.has_won.is_(False),
            )
            .order_by(MembershipSlot.slot_number.asc(), MembershipSlot.id.asc())
        )
        if slot is None:
            raise ValueError(
                f"User {user_id} does not have an available slot in group {membership.group_id}"
            )

    slot.has_won = True
    db.flush()
    total_slots, available_slots = _get_slot_count_breakdown(
        db,
        group_id=membership.group_id,
        user_id=user_id,
    )
    _apply_membership_slot_state(
        membership,
        total_slots=total_slots,
        available_slots=available_slots,
        prized_cycle_no=cycle_no,
    )
    db.flush()
    return slot


def release_membership_won_slot(db: Session, membership: GroupMembership) -> MembershipSlot | None:
    user_id = _resolve_membership_user_id(db, membership)
    slot = db.scalar(
        select(MembershipSlot)
        .where(
            MembershipSlot.group_id == membership.group_id,
            MembershipSlot.user_id == user_id,
            MembershipSlot.has_won.is_(True),
        )
        .order_by(MembershipSlot.slot_number.desc(), MembershipSlot.id.desc())
    )
    if slot is None:
        total_slots, available_slots = _get_slot_count_breakdown(
            db,
            group_id=membership.group_id,
            user_id=user_id,
        )
        _apply_membership_slot_state(
            membership,
            total_slots=total_slots,
            available_slots=available_slots,
            prized_cycle_no=membership.prized_cycle_no,
        )
        db.flush()
        return None

    slot.has_won = False
    db.flush()
    total_slots, available_slots = _get_slot_count_breakdown(
        db,
        group_id=membership.group_id,
        user_id=user_id,
    )
    _apply_membership_slot_state(
        membership,
        total_slots=total_slots,
        available_slots=available_slots,
        prized_cycle_no=membership.prized_cycle_no,
    )
    db.flush()
    return slot
