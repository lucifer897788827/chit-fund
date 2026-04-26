from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.startup_warmup import build_finalize_response_warmup_payload, warm_finalize_function_paths
from app.models.auction import AuctionBid, AuctionResult, AuctionSession
from app.modules.auctions.schemas import AuctionFinalizeResponse
from tests.test_auction_flow import _seed_live_auction


def test_app_lifespan_runs_startup_warmup_before_serving(app, monkeypatch):
    from app import main as main_module

    calls: list[str] = []
    monkeypatch.setattr(main_module, "bootstrap_database", lambda: calls.append("bootstrap"))
    monkeypatch.setattr(main_module, "run_startup_warmup", lambda: calls.append("warmup"))

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert calls == ["bootstrap", "warmup"]


def test_build_finalize_response_warmup_payload_matches_api_schema():
    payload = build_finalize_response_warmup_payload()

    model = AuctionFinalizeResponse.model_validate(payload)
    encoded = jsonable_encoder(model)

    assert encoded["status"] == "finalized"
    assert encoded["resultSummary"]["winnerMembershipId"] == 1
    assert encoded["console"]["groupCode"] == "WARMUP-000"


def test_warm_finalize_function_paths_does_not_write_finalize_state(app, db_session):
    session_id, membership_id, _group_id = _seed_live_auction(db_session)
    db_session.add(
        AuctionBid(
            auction_session_id=session_id,
            membership_id=membership_id,
            bidder_user_id=1,
            idempotency_key="warmup-bid",
            bid_amount=12000,
            bid_discount_amount=0,
            is_valid=True,
        )
    )
    db_session.commit()

    result = warm_finalize_function_paths(db_session)

    db_session.expire_all()
    session = db_session.get(AuctionSession, session_id)
    auction_result = db_session.scalar(select(AuctionResult).where(AuctionResult.auction_session_id == session_id))

    assert result["status"] == "ready"
    assert session is not None
    assert session.status == "open"
    assert auction_result is None
