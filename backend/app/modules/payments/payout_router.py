from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, get_current_user
from app.modules.payments.payout_service import mark_owner_payout_paid
from app.modules.payments.schemas import PayoutResponse


router = APIRouter(prefix="/api/payouts", tags=["payouts"])


@router.post("/{payout_id}/mark-paid", response_model=PayoutResponse)
async def mark_payout_paid_endpoint(
    payout_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return mark_owner_payout_paid(db, payout_id, current_user)
