from datetime import date, datetime, timezone

from app.models.external import ExternalChit, ExternalChitEntry
from app.modules.external_chits.serializers import (
    serialize_external_chit,
    serialize_external_chit_entry,
    serialize_external_chit_entry_history,
    serialize_external_chit_summary,
    serialize_external_chit_with_history,
)


def test_serialize_external_chit_uses_camelcase_and_optional_fields():
    chit = ExternalChit(
        id=11,
        subscriber_id=7,
        user_id=70,
        title="Village Fund",
        name="Village Ledger",
        organizer_name="Anita",
        chit_value=150000,
        installment_amount=7500,
        monthly_installment=7500,
        total_members=20,
        total_months=20,
        user_slots=2,
        first_month_organizer=True,
        cycle_frequency="monthly",
        start_date=date(2026, 5, 1),
        end_date=date(2027, 4, 1),
        status="active",
        notes="Collected locally",
        created_at=datetime(2026, 4, 21, 10, 30, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 21, 11, 0, tzinfo=timezone.utc),
    )

    payload = serialize_external_chit(chit)

    assert payload == {
        "id": 11,
        "subscriberId": 7,
        "userId": 70,
        "title": "Village Fund",
        "name": "Village Ledger",
        "organizerName": "Anita",
        "chitValue": 150000.0,
        "installmentAmount": 7500.0,
        "monthlyInstallment": 7500,
        "totalMembers": 20,
        "totalMonths": 20,
        "userSlots": 2,
        "firstMonthOrganizer": True,
        "cycleFrequency": "monthly",
        "startDate": date(2026, 5, 1),
        "endDate": date(2027, 4, 1),
        "status": "active",
        "notes": "Collected locally",
    }


def test_serialize_external_chit_entry_uses_camelcase():
    entry = ExternalChitEntry(
        id=21,
        external_chit_id=11,
        month_number=3,
        bid_amount=21000,
        winner_type="OTHER",
        winner_name="Ravi",
        share_per_slot=2100,
        my_share=4200,
        my_payable=10800,
        my_payout=0,
        is_bid_overridden=True,
        is_share_overridden=True,
        is_payable_overridden=False,
        is_payout_overridden=False,
        entry_type="payment",
        entry_date=date(2026, 5, 8),
        amount=7500,
        description="Installment received",
        created_at=datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 8, 13, 0, tzinfo=timezone.utc),
    )

    payload = serialize_external_chit_entry(entry)

    assert payload == {
        "id": 21,
        "externalChitId": 11,
        "monthNumber": 3,
        "bidAmount": 21000,
        "winnerType": "OTHER",
        "winnerName": "Ravi",
        "sharePerSlot": 2100,
        "myShare": 4200,
        "myPayable": 10800,
        "myPayout": 0,
        "isBidOverridden": True,
        "isShareOverridden": True,
        "isPayableOverridden": False,
        "isPayoutOverridden": False,
        "entryType": "payment",
        "entryDate": date(2026, 5, 8),
        "amount": 7500.0,
        "description": "Installment received",
        "createdAt": datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
        "updatedAt": datetime(2026, 5, 8, 13, 0, tzinfo=timezone.utc),
    }


def test_serialize_external_chit_with_history_reuses_flat_entry_serializer():
    chit = ExternalChit(
        id=11,
        subscriber_id=7,
        title="Village Fund",
        organizer_name="Anita",
        chit_value=150000,
        installment_amount=7500,
        cycle_frequency="monthly",
        start_date=date(2026, 5, 1),
        status="active",
        notes=None,
    )
    entries = [
        ExternalChitEntry(
            id=21,
            external_chit_id=11,
            entry_type="payment",
            entry_date=date(2026, 5, 8),
            amount=7500,
            description="Installment received",
            created_at=datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
        ),
        ExternalChitEntry(
            id=22,
            external_chit_id=11,
            entry_type="note",
            entry_date=date(2026, 5, 9),
            amount=None,
            description="Member asked for a receipt",
            created_at=datetime(2026, 5, 9, 9, 15, tzinfo=timezone.utc),
        ),
    ]

    flat_history = serialize_external_chit_entry_history(entries)
    payload = serialize_external_chit_with_history(chit, entries)

    assert payload["entryHistory"] == flat_history
    assert payload["entryHistory"][0]["entryType"] == "payment"
    assert payload["entryHistory"][1]["amount"] is None


def test_serialize_external_chit_summary_uses_camelcase():
    payload = serialize_external_chit_summary(
        total_paid=30000,
        total_received=72000,
        profit=42000,
        winning_month=3,
    )

    assert payload == {
        "totalPaid": 30000,
        "totalReceived": 72000,
        "profit": 42000,
        "winningMonth": 3,
    }
