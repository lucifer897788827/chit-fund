from datetime import datetime

from pydantic import AliasChoices, BaseModel, Field



class LoginRequest(BaseModel):
    phone: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str = Field(validation_alias=AliasChoices("refresh_token", "refreshToken"))


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("refresh_token", "refreshToken"),
    )


class SignupRequest(BaseModel):
    fullName: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    email: str | None = None
    password: str = Field(min_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str
    refresh_token_expires_at: datetime
    access_token_expires_in: int = 900
    refresh_token_expires_in: int = 2592000
    role: str
    owner_id: int | None = None
    subscriber_id: int | None = None
    has_subscriber_profile: bool = False


class PasswordResetRequest(BaseModel):
    phone: str


class PasswordResetRequestResponse(BaseModel):
    message: str
    reset_token: str | None = None
    reset_token_expires_at: datetime | None = None


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str


class PasswordResetConfirmResponse(BaseModel):
    message: str
