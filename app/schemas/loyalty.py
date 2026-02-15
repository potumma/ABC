from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional


class LoyaltyBalanceResponse(BaseModel):
    loyalty_points: int = Field(..., ge=0)


class LoyaltyTransaction(BaseModel):
    id: int
    user_id: str
    points_change: int
    type: str
    description: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class LoyaltyHistoryResponse(BaseModel):
    items: List[LoyaltyTransaction]
    total_count: int
