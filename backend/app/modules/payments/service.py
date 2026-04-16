from sqlalchemy.orm import Session

from app.models.money import Payment


def record_payment(db: Session, payload):
    payment = Payment(
        owner_id=payload.ownerId,
        subscriber_id=payload.subscriberId,
        membership_id=payload.membershipId,
        installment_id=payload.installmentId,
        payment_type=payload.paymentType,
        payment_method=payload.paymentMethod,
        amount=payload.amount,
        payment_date=payload.paymentDate,
        reference_no=payload.referenceNo,
        recorded_by_user_id=1,
        status="recorded",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return {
        "id": payment.id,
        "ownerId": payment.owner_id,
        "subscriberId": payment.subscriber_id,
        "membershipId": payment.membership_id,
        "installmentId": payment.installment_id,
        "paymentType": payment.payment_type,
        "paymentMethod": payment.payment_method,
        "amount": float(payment.amount),
        "paymentDate": payment.payment_date,
        "referenceNo": payment.reference_no,
        "status": payment.status,
    }
