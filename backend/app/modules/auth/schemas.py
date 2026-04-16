from pydantic import BaseModel


class LoginRequest(BaseModel):
    phone: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    owner_id: int | None = None
    subscriber_id: int | None = None
    has_subscriber_profile: bool = False
