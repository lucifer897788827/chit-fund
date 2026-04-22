from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.pagination import PaginatedResponse
from app.core.security import CurrentUser, get_current_user
from app.modules.payments.payout_service import list_owner_payouts, settle_owner_payout
from app.modules.payments.schemas import (
    MemberBalanceResponse,
    PaymentCreate,
    PaymentResponse,
    PayoutResponse,
    PayoutSettleRequest,
)
from app.modules.payments.service import list_member_balances, list_payment_history, record_payment

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.post("", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def record_payment_endpoint(
    payload: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return record_payment(db, payload, current_user)


@router.get("", response_model=list[PaymentResponse] | PaginatedResponse[PaymentResponse])
async def list_payments_endpoint(
    subscriberId: int | None = None,
    groupId: int | None = None,
    page: int | None = Query(None, ge=1),
    pageSize: int | None = Query(None, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_payment_history(
        db,
        current_user,
        subscriber_id=subscriberId,
        group_id=groupId,
        page=page,
        page_size=pageSize,
    )


@router.get("/balances", response_model=list[MemberBalanceResponse] | PaginatedResponse[MemberBalanceResponse])
async def list_member_balances_endpoint(
    subscriberId: int | None = None,
    groupId: int | None = None,
    page: int | None = Query(None, ge=1),
    pageSize: int | None = Query(None, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_member_balances(
        db,
        current_user,
        subscriber_id=subscriberId,
        group_id=groupId,
        page=page,
        page_size=pageSize,
    )


@router.get("/payouts", response_model=list[PayoutResponse] | PaginatedResponse[PayoutResponse])
async def list_owner_payouts_endpoint(
    subscriberId: int | None = None,
    groupId: int | None = None,
    status: str | None = None,
    page: int | None = Query(None, ge=1),
    pageSize: int | None = Query(None, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_owner_payouts(
        db,
        current_user,
        subscriber_id=subscriberId,
        group_id=groupId,
        status=status,
        page=page,
        page_size=pageSize,
    )


@router.post("/payouts/{payout_id}/settle", response_model=PayoutResponse)
async def settle_owner_payout_endpoint(
    payout_id: int,
    payload: PayoutSettleRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return settle_owner_payout(
        db,
        payout_id,
        current_user,
        payout_method=payload.payoutMethod,
        payout_date=payload.payoutDate,
        reference_no=payload.referenceNo,
    )
