from sqlalchemy.orm import Session

from app.models.user import Subscriber, User


def create_subscriber(db: Session, payload):
    user = User(
        email=payload.email,
        phone=payload.phone,
        password_hash="",
        role="subscriber",
        is_active=True,
    )
    db.add(user)
    db.flush()

    subscriber = Subscriber(
        user_id=user.id,
        owner_id=payload.ownerId,
        full_name=payload.fullName,
        phone=payload.phone,
        email=payload.email,
        status="active",
    )
    db.add(subscriber)
    db.commit()
    db.refresh(subscriber)
    return {
        "id": subscriber.id,
        "ownerId": subscriber.owner_id,
        "fullName": subscriber.full_name,
        "phone": subscriber.phone,
        "email": subscriber.email,
        "status": subscriber.status,
    }
