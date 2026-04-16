from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.subscribers.schemas import SubscriberCreate
from app.modules.subscribers.service import create_subscriber

router = APIRouter(prefix="/api/subscribers", tags=["subscribers"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_subscriber_endpoint(payload: SubscriberCreate, db: Session = Depends(get_db)):
    return create_subscriber(db, payload)
