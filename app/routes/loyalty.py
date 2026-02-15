from fastapi import APIRouter, Depends, Query, status, HTTPException
from app.schemas.loyalty import LoyaltyBalanceResponse, LoyaltyHistoryResponse
from app.crud.loyalty import CRUDLoyalty
from app.core.supabase import supabase
from app.core.security import get_current_user, CurrentUser
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/loyalty", tags=["loyalty"])
crud_loyalty = CRUDLoyalty(supabase)


@router.get("/balance", response_model=LoyaltyBalanceResponse)
async def get_loyalty_balance(
    current_user: CurrentUser = Depends(get_current_user)
):
    try:
        balance = await crud_loyalty.get_balance(current_user.user_id)
        return LoyaltyBalanceResponse(loyalty_points=balance)
    except Exception as e:
        logger.error(f"Error fetching loyalty balance: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch loyalty balance"
        )


@router.get("/history", response_model=LoyaltyHistoryResponse)
async def get_loyalty_history(
    current_user: CurrentUser = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    try:
        result = await crud_loyalty.get_history(current_user.user_id, limit, offset)
        return LoyaltyHistoryResponse(
            items=result.get("items", []),
            total_count=result.get("total_count", 0)
        )
    except Exception as e:
        logger.error(f"Error fetching loyalty history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch loyalty history"
        )
