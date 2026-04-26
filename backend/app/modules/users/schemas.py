from pydantic import BaseModel


class FinancialSummaryResponse(BaseModel):
    total_paid: int
    total_received: int
    dividend: int
    net: int
