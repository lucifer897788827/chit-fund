from datetime import date

from pydantic import BaseModel


class PaymentCreate(BaseModel):
    ownerId: int
    subscriberId: int
    membershipId: int | None = None
    installmentId: int | None = None
    paymentType: str
    paymentMethod: str
    amount: float
    paymentDate: date
    referenceNo: str | None = None


class PaymentResponse(PaymentCreate):
    id: int
    status: str
