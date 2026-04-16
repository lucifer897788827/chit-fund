from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.external_chits.schemas import ExternalChitCreate, ExternalChitResponse
from app.modules.external_chits.service import create_external_chit, list_external_chits

router = APIRouter(prefix="/api/external-chits", tags=["external-chits"])


@router.get("", response_model=list[ExternalChitResponse])
async def list_external_chits_endpoint(subscriberId: int, db: Session = Depends(get_db)):
    return list_external_chits(db, subscriberId)


@router.post("", response_model=ExternalChitResponse, status_code=status.HTTP_201_CREATED)
async def create_external_chit_endpoint(payload: ExternalChitCreate, db: Session = Depends(get_db)):
    return create_external_chit(db, payload)
