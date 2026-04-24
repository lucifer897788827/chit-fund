from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentUser, get_current_user
from app.modules.auth.schemas import (
    AuthMeResponse,
    LoginRequest,
    LogoutRequest,
    PasswordResetConfirmRequest,
    PasswordResetConfirmResponse,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    RefreshRequest,
    SignupRequest,
    TokenResponse,
)
from app.modules.auth.service import (
    build_auth_me_response,
    confirm_password_reset,
    login_user,
    logout_user,
    refresh_session,
    request_password_reset,
    signup_user,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: Session = Depends(get_db)):
    return login_user(db, payload.phone, payload.password)


@router.post("/signup", response_model=TokenResponse, status_code=201)
async def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    return signup_user(db, payload)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    return refresh_session(db, payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: LogoutRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    logout_user(db, current_user, payload.refresh_token)


@router.get("/me", response_model=AuthMeResponse)
async def me(current_user: CurrentUser = Depends(get_current_user)):
    return build_auth_me_response(current_user)


@router.post("/request-reset", response_model=PasswordResetRequestResponse)
async def request_reset(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    return request_password_reset(db, payload.phone)


@router.post("/confirm-reset", response_model=PasswordResetConfirmResponse)
async def confirm_reset(payload: PasswordResetConfirmRequest, db: Session = Depends(get_db)):
    return confirm_password_reset(db, payload.token, payload.new_password)
