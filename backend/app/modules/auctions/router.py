import logging

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.logging import APP_LOGGER_NAME
from app.core.security import CurrentUser, get_current_user
from app.core.websocket import connection_manager
from app.modules.auctions.schemas import (
    AuctionFinalizeResponse,
    OwnerAuctionConsoleResponse,
    AuctionRoomResponse,
    BidCreate,
    BidResponse,
)
from app.modules.auctions.service import (
    finalize_auction,
    get_owner_auction_console,
    get_room,
    place_bid,
)

router = APIRouter(prefix="/api/auctions", tags=["auctions"])
logger = logging.getLogger(APP_LOGGER_NAME)


@router.get("/{session_id}/room", response_model=AuctionRoomResponse)
async def get_room_endpoint(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return get_room(db, session_id, current_user)


@router.post("/{session_id}/bids", response_model=BidResponse)
async def place_bid_endpoint(
    session_id: int,
    payload: BidCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    result = place_bid(db, session_id, payload, current_user)
    try:
        await connection_manager.broadcast(
            session_id,
            jsonable_encoder(
                {
                    "eventType": "auction.bid.placed",
                    "sessionId": session_id,
                    "payload": {
                        "bidId": result["bidId"],
                        "room": result["room"],
                    },
                }
            ),
        )
    except Exception:
        logger.exception(
            "Auction bid websocket broadcast failed",
            extra={
                "event": "auction.bid.websocket_broadcast_failed",
                "auction_session_id": session_id,
                "bid_id": result["bidId"],
            },
        )
    return result


@router.get("/{session_id}/owner-console", response_model=OwnerAuctionConsoleResponse)
async def get_owner_auction_console_endpoint(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return get_owner_auction_console(db, session_id, current_user)


@router.post("/{session_id}/finalize", response_model=AuctionFinalizeResponse)
async def finalize_auction_endpoint(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    result = finalize_auction(db, session_id, current_user)
    if result.get("status") == "finalized":
        try:
            await connection_manager.broadcast(
                session_id,
                jsonable_encoder(
                    {
                        "eventType": "auction.finalized",
                        "sessionId": session_id,
                        "payload": {
                            "console": result["console"],
                        },
                    }
                ),
            )
        except Exception:
            logger.exception(
                "Auction finalize websocket broadcast failed",
                extra={
                    "event": "auction.finalize.websocket_broadcast_failed",
                    "auction_session_id": session_id,
                },
            )
    return result
