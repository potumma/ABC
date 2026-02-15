from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from app.schemas.review import (
    ReviewCreate,
    ReviewUpdate,
    ReviewListResponse,
    ReviewResponse,
    ReviewLikeResponse
)
from app.crud.review import CRUDReview
from app.crud.loyalty import CRUDLoyalty
from app.core.supabase import supabase
from app.core.security import get_current_user, CurrentUser
from app.core.exceptions import NotFoundException, AppException
import logging

router = APIRouter(prefix="/api/reviews", tags=["reviews"])
crud_review = CRUDReview(supabase)
crud_loyalty = CRUDLoyalty(supabase)
logger = logging.getLogger(__name__)


# -------- GET REVIEWS (WITH TOTAL COUNT) --------
@router.get("/movie/{movie_id}", response_model=ReviewListResponse)
async def read_reviews_by_movie(
    movie_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100)
):
    """Get all reviews for a specific movie"""
    return await crud_review.get_by_movie(movie_id, skip, limit)


# -------- CREATE --------
@router.post("", response_model=ReviewResponse)
async def create_review(
    review_in: ReviewCreate,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Create a new review for a movie"""
    try:
        # Add user info to review data
        review_data = review_in.model_dump()
        review_data["user_id"] = current_user.user_id
        review_data["username"] = current_user.user_name or current_user.email.split("@")[0]
        created = await crud_review.create(review_data)

        try:
            loyalty_result = await crud_loyalty.award_review_points(
                current_user.user_id,
                review_in.movie_id
            )
            if not loyalty_result.get('success'):
                logger.info(
                    "Review points not awarded for user %s movie %s: %s",
                    current_user.user_id,
                    review_in.movie_id,
                    loyalty_result.get('error')
                )
        except Exception as loyalty_err:
            logger.error(f"Error awarding review points: {loyalty_err}")

        return created
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# -------- UPDATE --------
@router.put("/{review_id}", response_model=ReviewResponse)
async def update_review(
    review_id: int,
    review_in: ReviewUpdate,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Update an existing review (only if owner)"""
    updated = await crud_review.update(
        review_id,
        review_in.model_dump(exclude_unset=True),
        current_user.user_id
    )
    if not updated:
        raise NotFoundException("Review", str(review_id))
    return updated


# -------- DELETE --------
@router.delete("/{review_id}")
async def delete_review(
    review_id: int,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Delete a review (only if owner)"""
    success = await crud_review.delete(review_id, current_user.user_id)
    if not success:
        raise NotFoundException("Review", str(review_id))
    return {"status": "success", "message": "Review deleted"}


# -------- LIKE --------
@router.post("/{review_id}/likes", response_model=ReviewLikeResponse)
async def add_review_like(
    review_id: int,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Like a review"""
    try:
        return await crud_review.add_like(review_id, current_user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{review_id}/likes")
async def remove_review_like(
    review_id: int,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Unlike a review"""
    success = await crud_review.remove_like(review_id, current_user.user_id)
    if not success:
        raise HTTPException(status_code=400, detail="Like not found")
    return {"status": "success", "message": "Like removed"}
