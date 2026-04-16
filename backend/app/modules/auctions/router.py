from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.auctions.schemas import AuctionRoomResponse, BidCreate, BidResponse
from app.modules.auctions.service import get_room, place_bid

router = APIRouter(prefix="/api/auctions", tags=["auctions"])


@router.get("/{session_id}/room", response_model=AuctionRoomResponse)
async def get_room_endpoint(session_id: int, db: Session = Depends(get_db)):
    return get_room(db, session_id)


@router.post("/{session_id}/bids", response_model=BidResponse)
async def place_bid_endpoint(
    session_id: int, payload: BidCreate, db: Session = Depends(get_db)
):
    return place_bid(db, session_id, payload.membershipId, payload.bidAmount)
