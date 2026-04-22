from datetime import date
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.money import parse_whole_amount


class PaymentCreate(BaseModel):
    ownerId: int
    subscriberId: int
    membershipId: int | None = None
    installmentId: int | None = None
    cycleNo: int | None = None
    paymentType: str
    paymentMethod: str
    amount: int = Field(gt=0)
    paymentDate: date
    referenceNo: str | None = None

    @field_validator("amount", mode="before")
    @classmethod
    def _validate_amount(cls, value):
        return parse_whole_amount(value)


class PaymentResponse(PaymentCreate):
    id: int
    status: str
    paymentStatus: str | None = None
    groupId: int | None = None
    installmentStatus: str | None = None
    installmentBalanceAmount: int | None = None
    penaltyAmount: int | None = None
    arrearsAmount: int | None = None
    nextDueAmount: int | None = None
    nextDueDate: date | None = None
    outstandingAmount: int | None = None
    ledgerEntryId: int | None = None


class MemberBalanceResponse(BaseModel):
    groupId: int
    subscriberId: int
    membershipId: int
    memberNo: int
    slotCount: int = 1
    wonSlotCount: int = 0
    remainingSlotCount: int = 1
    totalDue: int
    totalPaid: int
    outstandingAmount: int
    penaltyAmount: int | None = None
    paymentStatus: str
    arrearsAmount: int
    nextDueAmount: int
    nextDueDate: date | None = None


class PayoutResponse(BaseModel):
    id: int
    ownerId: int
    auctionResultId: int
    subscriberId: int
    membershipId: int
    groupId: int
    groupCode: str | None = None
    groupTitle: str | None = None
    cycleNo: int
    subscriberName: str | None = None
    memberNo: int | None = None
    grossAmount: int
    deductionsAmount: int
    netAmount: int
    payoutMethod: str
    payoutDate: date | None = None
    referenceNo: str | None = None
    status: str
    paymentStatus: str | None = None
    penaltyAmount: int | None = None
    arrearsAmount: int | None = None
    nextDueAmount: int | None = None
    nextDueDate: date | None = None
    outstandingAmount: int | None = None
    createdAt: datetime
    updatedAt: datetime


class PayoutSettleRequest(BaseModel):
    payoutMethod: str | None = None
    payoutDate: date | None = None
    referenceNo: str | None = None
