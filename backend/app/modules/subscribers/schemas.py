from pydantic import BaseModel


class SubscriberCreate(BaseModel):
    ownerId: int | None = None
    fullName: str
    phone: str
    email: str | None = None
