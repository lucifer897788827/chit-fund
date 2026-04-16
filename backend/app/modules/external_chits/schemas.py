from datetime import date

from pydantic import BaseModel


class ExternalChitCreate(BaseModel):
    subscriberId: int
    title: str
    organizerName: str
    chitValue: float
    installmentAmount: float
    cycleFrequency: str
    startDate: date


class ExternalChitResponse(ExternalChitCreate):
    id: int
    status: str
