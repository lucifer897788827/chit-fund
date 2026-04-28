from pydantic import BaseModel
from typing import Any


class FinancialSummaryResponse(BaseModel):
    total_paid: int
    total_received: int
    dividend: int
    net: int
    netPosition: int


class UserDashboardResponse(BaseModel):
    role: str
    financial_summary: FinancialSummaryResponse
    stats: dict[str, Any]
