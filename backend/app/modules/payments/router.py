from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.payments.schemas import PaymentCreate, PaymentResponse
from app.modules.payments.service import record_payment

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.post("", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def record_payment_endpoint(payload: PaymentCreate, db: Session = Depends(get_db)):
    return record_payment(db, payload)
