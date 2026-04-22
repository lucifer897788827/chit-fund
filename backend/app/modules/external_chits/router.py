from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.pagination import PaginatedResponse
from app.core.security import CurrentUser, get_current_user
from app.modules.external_chits.schemas import (
    ExternalChitCreate,
    ExternalChitDetailResponse,
    ExternalChitEntryCreate,
    ExternalChitEntryResponse,
    ExternalChitSummaryResponse,
    ExternalChitEntryUpdate,
    ExternalChitResponse,
    ExternalChitUpdate,
)
from app.modules.external_chits.service import (
    create_external_chit,
    create_external_chit_history_entry,
    delete_external_chit,
    get_external_chit_detail,
    get_external_chit_summary,
    list_external_chit_history,
    list_external_chits,
    update_external_chit_history_entry,
    update_external_chit,
)

router = APIRouter(prefix="/api/external-chits", tags=["external-chits"])


@router.get("", response_model=list[ExternalChitResponse] | PaginatedResponse[ExternalChitResponse])
async def list_external_chits_endpoint(
    page: int | None = Query(None, ge=1),
    pageSize: int | None = Query(None, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_external_chits(db, current_user, page=page, page_size=pageSize)


@router.post("", response_model=ExternalChitResponse, status_code=status.HTTP_201_CREATED)
async def create_external_chit_endpoint(
    payload: ExternalChitCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return create_external_chit(db, payload, current_user)


@router.get("/{chit_id}", response_model=ExternalChitDetailResponse)
async def get_external_chit_detail_endpoint(
    chit_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return get_external_chit_detail(db, chit_id, current_user)


@router.get("/{chit_id}/summary", response_model=ExternalChitSummaryResponse)
async def get_external_chit_summary_endpoint(
    chit_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return get_external_chit_summary(db, chit_id, current_user)


@router.patch("/{chit_id}", response_model=ExternalChitResponse)
async def update_external_chit_endpoint(
    chit_id: int,
    payload: ExternalChitUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return update_external_chit(db, chit_id, payload, current_user)


@router.delete("/{chit_id}", response_model=ExternalChitResponse)
async def delete_external_chit_endpoint(
    chit_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return delete_external_chit(db, chit_id, current_user)


@router.get("/{chit_id}/entries", response_model=list[ExternalChitEntryResponse] | PaginatedResponse[ExternalChitEntryResponse])
async def list_external_chit_entries_endpoint(
    chit_id: int,
    page: int | None = Query(None, ge=1),
    pageSize: int | None = Query(None, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return list_external_chit_history(db, chit_id, current_user, page=page, page_size=pageSize)


@router.post("/{chit_id}/entries", response_model=ExternalChitEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_external_chit_entry_endpoint(
    chit_id: int,
    payload: ExternalChitEntryCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return create_external_chit_history_entry(db, chit_id, payload, current_user)


@router.put("/{chit_id}/entries/{entry_id}", response_model=ExternalChitEntryResponse)
async def update_external_chit_entry_endpoint(
    chit_id: int,
    entry_id: int,
    payload: ExternalChitEntryUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return update_external_chit_history_entry(db, chit_id, entry_id, payload, current_user)
