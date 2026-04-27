from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, get_current_user
from app.modules.users.schemas import FinancialSummaryResponse, UserDashboardResponse
from app.modules.users.service import get_my_dashboard, get_my_financial_summary


router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me/financial-summary", response_model=FinancialSummaryResponse)
async def get_my_financial_summary_endpoint(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return get_my_financial_summary(db, current_user)


@router.get("/me/dashboard", response_model=UserDashboardResponse)
async def get_my_dashboard_endpoint(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return get_my_dashboard(db, current_user)
