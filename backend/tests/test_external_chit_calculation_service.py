from types import SimpleNamespace

from app.modules.external_chits.service import calculate_external_chit_month


def _make_chit(**overrides):
    payload = {
        "monthly_installment": 10000,
        "total_members": 10,
        "user_slots": 2,
        "first_month_organizer": False,
        "chit_value": 100000,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _make_entry(**overrides):
    payload = {
        "month_number": 2,
        "bid_amount": 20000,
        "winner_type": "OTHER",
        "share_per_slot": None,
        "my_share": None,
        "my_payable": None,
        "my_payout": None,
        "is_bid_overridden": False,
        "is_share_overridden": False,
        "is_payable_overridden": False,
        "is_payout_overridden": False,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_calculate_external_chit_month_handles_first_month_organizer_special_case():
    result = calculate_external_chit_month(
        _make_entry(month_number=1, bid_amount=25000, winner_type="SELF"),
        _make_chit(first_month_organizer=True),
    )

    assert result["sharePerSlot"] == 0
    assert result["myShare"] == 0
    assert result["myPayable"] == 20000
    assert result["myPayout"] == 0
    assert all(isinstance(result[field], int) for field in ("sharePerSlot", "myShare", "myPayable", "myPayout"))


def test_calculate_external_chit_month_calculates_share_and_payable_for_other_winner():
    result = calculate_external_chit_month(_make_entry(), _make_chit())

    assert result["chitValue"] == 100000
    assert result["sharePerSlot"] == 2000
    assert result["myShare"] == 4000
    assert result["myPayable"] == 16000
    assert result["myPayout"] == 0


def test_calculate_external_chit_month_calculates_self_winner_payout():
    result = calculate_external_chit_month(
        _make_entry(winner_type="SELF"),
        _make_chit(),
    )

    assert result["sharePerSlot"] == 2000
    assert result["myShare"] == 4000
    assert result["myPayable"] == 16000
    assert result["myPayout"] == 64000


def test_calculate_external_chit_month_respects_manual_share_override_when_deriving_other_fields():
    result = calculate_external_chit_month(
        _make_entry(
            share_per_slot=2500,
            my_share=5000,
            is_share_overridden=True,
        ),
        _make_chit(),
    )

    assert result["sharePerSlot"] == 2500
    assert result["myShare"] == 5000
    assert result["myPayable"] == 15000
    assert result["myPayout"] == 0


def test_calculate_external_chit_month_preserves_manual_payable_and_payout_overrides():
    result = calculate_external_chit_month(
        _make_entry(
            winner_type="SELF",
            my_payable=17000,
            my_payout=63000,
            is_payable_overridden=True,
            is_payout_overridden=True,
        ),
        _make_chit(),
    )

    assert result["sharePerSlot"] == 2000
    assert result["myShare"] == 4000
    assert result["myPayable"] == 17000
    assert result["myPayout"] == 63000


def test_calculate_external_chit_month_returns_safe_zero_defaults_when_bid_is_missing():
    result = calculate_external_chit_month(
        _make_entry(
            bid_amount=None,
            winner_type=None,
            share_per_slot=None,
            my_share=None,
            my_payable=None,
            my_payout=None,
        ),
        _make_chit(),
    )

    assert result["sharePerSlot"] == 0
    assert result["myShare"] == 0
    assert result["myPayable"] == 0
    assert result["myPayout"] == 0
    assert all(isinstance(result[field], int) for field in ("sharePerSlot", "myShare", "myPayable", "myPayout"))
