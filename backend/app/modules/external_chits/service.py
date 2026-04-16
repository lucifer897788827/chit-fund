from sqlalchemy.orm import Session

from app.models.external import ExternalChit


def list_external_chits(db: Session, subscriber_id: int):
    chits = (
        db.query(ExternalChit)
        .filter(ExternalChit.subscriber_id == subscriber_id)
        .order_by(ExternalChit.id.asc())
        .all()
    )
    return [
        {
            "id": chit.id,
            "subscriberId": chit.subscriber_id,
            "title": chit.title,
            "organizerName": chit.organizer_name,
            "chitValue": float(chit.chit_value),
            "installmentAmount": float(chit.installment_amount),
            "cycleFrequency": chit.cycle_frequency,
            "startDate": chit.start_date,
            "status": chit.status,
        }
        for chit in chits
    ]


def create_external_chit(db: Session, payload):
    external_chit = ExternalChit(
        subscriber_id=payload.subscriberId,
        title=payload.title,
        organizer_name=payload.organizerName,
        chit_value=payload.chitValue,
        installment_amount=payload.installmentAmount,
        cycle_frequency=payload.cycleFrequency,
        start_date=payload.startDate,
        status="active",
    )
    db.add(external_chit)
    db.commit()
    db.refresh(external_chit)
    return {
        "id": external_chit.id,
        "subscriberId": external_chit.subscriber_id,
        "title": external_chit.title,
        "organizerName": external_chit.organizer_name,
        "chitValue": float(external_chit.chit_value),
        "installmentAmount": float(external_chit.installment_amount),
        "cycleFrequency": external_chit.cycle_frequency,
        "startDate": external_chit.start_date,
        "status": external_chit.status,
    }
