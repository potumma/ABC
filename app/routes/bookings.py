"""
Booking API Routes
Handles all booking-related endpoints
"""
from fastapi import APIRouter, HTTPException, status, Query, Depends
from typing import List, Optional
from uuid import UUID
from app.schemas.booking import (
    ReserveSeatRequest,
    ReserveSeatResponse,
    ConfirmPaymentRequest,
    ConfirmPaymentResponse,
    CancelBookingRequest,
    CancelBookingResponse,
    BookingDetail,
    UserBookingsResponse,
    AvailableSeat,
    ScreenInfo,
    ScreenStatistics,
    ExpiryWorkerResponse
)
from app.crud.booking import CRUDBooking
from app.crud.loyalty import CRUDLoyalty
from app.core.supabase import supabase
from app.core.security import get_current_user, CurrentUser
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bookings", tags=["bookings"])
crud_booking = CRUDBooking(supabase)
crud_loyalty = CRUDLoyalty(supabase)


# ========== Seat Selection Endpoints ==========

@router.get("/screens", response_model=List[ScreenInfo])
async def get_screens():
    """Get all available screens"""
    try:
        screens = await crud_booking.get_all_screens()
        return screens
    except Exception as e:
        logger.error(f"Error getting screens: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch screens: {str(e)}"
        )


@router.get("/screens/{screen_id}", response_model=ScreenInfo)
async def get_screen(screen_id: int):
    """Get screen details by ID"""
    try:
        screen = await crud_booking.get_screen_by_id(screen_id)
        if not screen:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Screen not found"
            )
        return screen
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting screen: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch screen: {str(e)}"
        )


@router.get("/screens/{screen_id}/seats", response_model=List[AvailableSeat])
async def get_available_seats(screen_id: int):
    """
    Get all available seats for a specific screen.
    This is called when the user opens the seat selection page.
    """
    try:
        seats = await crud_booking.get_available_seats(screen_id)
        return seats
    except Exception as e:
        logger.error(f"Error getting available seats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch available seats: {str(e)}"
        )


@router.get("/screens/{screen_id}/seats/all")
async def get_all_seats(screen_id: int):
    """
    Get all seats for a screen (including reserved/sold).
    Useful for rendering the seat map with different states.
    """
    try:
        seats = await crud_booking.get_all_seats_for_screen(screen_id)
        return seats
    except Exception as e:
        logger.error(f"Error getting all seats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch seats: {str(e)}"
        )



# ========== Booking Flow Endpoints ==========

@router.post("/reserve", response_model=ReserveSeatResponse)
async def reserve_seats(request: ReserveSeatRequest):
    """
    Step 1: Reserve seats and create pending booking.
    Called when user proceeds to payment.
    Starts the 5-minute countdown timer.
    """
    try:
        result = await crud_booking.reserve_seats(request)

        if not result.get('success'):
            return ReserveSeatResponse(
                success=False,
                error=result.get('error', 'Failed to reserve seats'),
                unavailable_seats=result.get('unavailable_seats')
            )

        total_amount = request.price_per_seat * len(request.seat_ids)
        loyalty_points_used = None
        discount_amount = None

        if request.loyalty_points_to_use > 0:
            redeem_result = await crud_loyalty.redeem_booking_points(
                result['booking_id'],
                request.loyalty_points_to_use
            )

            if not redeem_result.get('success'):
                logger.warning(
                    "Loyalty redemption failed for booking %s: %s",
                    result['booking_id'],
                    redeem_result.get('error')
                )
                try:
                    await crud_booking.cancel_booking(result['booking_id'])
                except Exception as cancel_err:
                    logger.error(f"Failed to cancel booking after redemption error: {cancel_err}")

                return ReserveSeatResponse(
                    success=False,
                    error=redeem_result.get('error', 'Failed to redeem loyalty points')
                )

            loyalty_points_used = redeem_result.get('points_used')
            discount_amount = redeem_result.get('discount_amount')
            total_amount = redeem_result.get('new_total_amount', total_amount)

        return ReserveSeatResponse(
            success=True,
            booking_id=result['booking_id'],
            payment_deadline=result['payment_deadline'],
            total_amount=total_amount,
            loyalty_points_used=loyalty_points_used,
            discount_amount=discount_amount
        )

    except Exception as e:
        logger.error(f"Error reserving seats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reserve seats: {str(e)}"
        )


@router.post("/confirm-payment", response_model=ConfirmPaymentResponse)
async def confirm_payment(request: ConfirmPaymentRequest):
    """
    Step 2: Confirm payment and finalize booking.
    Called after payment gateway confirms successful payment.
    Changes seat status from 'reserved' to 'sold'.
    """
    try:
        # First check if booking exists
        booking = await crud_booking.get_booking_by_id(request.booking_id)
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found"
            )

        logger.info(f"Confirming payment for booking {request.booking_id}, current status: {booking.get('status')}")

        # If already confirmed, return the tickets (idempotent behavior)
        if booking['status'] == 'confirmed':
            logger.info(f"Booking {request.booking_id} already confirmed, returning existing tickets")
            tickets = await crud_booking.get_tickets_for_booking(request.booking_id)
            return ConfirmPaymentResponse(
                success=True,
                message="Payment already confirmed",
                booking_id=request.booking_id,
                tickets=tickets
            )

        if booking['status'] != 'pending':
            logger.warning(f"Cannot confirm payment - booking {request.booking_id} status is '{booking['status']}', expected 'pending' or 'confirmed'")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Booking cannot be confirmed. Current status: {booking['status']}"
            )

        # Confirm payment
        result = await crud_booking.confirm_payment(
            request.booking_id,
            request.payment_intent_id
        )

        if not result.get('success'):
            return ConfirmPaymentResponse(
                success=False,
                message=result.get('error', 'Failed to confirm payment')
            )

        # Get tickets
        tickets = await crud_booking.get_tickets_for_booking(request.booking_id)

        try:
            loyalty_result = await crud_loyalty.award_booking_points(request.booking_id)
            if not loyalty_result.get('success'):
                logger.warning(
                    "Failed to award booking points for %s: %s",
                    request.booking_id,
                    loyalty_result.get('error')
                )
        except Exception as loyalty_err:
            logger.error(f"Error awarding booking points: {loyalty_err}")

        return ConfirmPaymentResponse(
            success=True,
            message="Payment confirmed successfully",
            booking_id=request.booking_id,
            tickets=tickets
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error confirming payment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to confirm payment: {str(e)}"
        )


@router.post("/cancel", response_model=CancelBookingResponse)
async def cancel_booking(request: CancelBookingRequest):
    """
    Cancel a pending booking.
    Called when user explicitly cancels or closes the payment page.
    Releases seats back to available status.
    """
    try:
        result = await crud_booking.cancel_booking(request.booking_id)

        if not result.get('success'):
            return CancelBookingResponse(
                success=False,
                message=result.get('error', 'Failed to cancel booking')
            )

        try:
            refund_result = await crud_loyalty.refund_booking_points(request.booking_id)
            if not refund_result.get('success'):
                logger.warning(
                    "Failed to refund booking points for %s: %s",
                    request.booking_id,
                    refund_result.get('error')
                )
        except Exception as loyalty_err:
            logger.error(f"Error refunding booking points: {loyalty_err}")

        return CancelBookingResponse(
            success=True,
            message="Booking cancelled successfully"
        )

    except Exception as e:
        logger.error(f"Error cancelling booking: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel booking: {str(e)}"
        )


# ========== Booking Information Endpoints ==========

@router.get("/me", response_model=UserBookingsResponse)
async def get_my_bookings(
    current_user: CurrentUser = Depends(get_current_user),
    booking_status: Optional[str] = Query(None, alias="status", description="Filter by status (pending, confirmed, cancelled, expired)")
):
    """Get all bookings for the currently authenticated user"""
    try:
        user_id = UUID(current_user.user_id)
        bookings = await crud_booking.get_user_bookings(user_id, booking_status)
        return UserBookingsResponse(
            bookings=bookings,
            total_count=len(bookings)
        )
    except Exception as e:
        logger.error(f"Error getting user bookings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch user bookings: {str(e)}"
        )


@router.get("/{booking_id}", response_model=BookingDetail)
async def get_booking(
    booking_id: int,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Get detailed booking information including seats"""
    try:
        booking = await crud_booking.get_booking_details(booking_id)
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found"
            )

        # Basic Authorization: Owner or Admin
        if not current_user.is_admin and str(booking.user_id) != current_user.user_id:
            logger.warning(f"Unauthorized access attempt to booking {booking_id} by user {current_user.user_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view this booking"
            )

        return booking
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting booking: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch booking: {str(e)}"
        )


@router.get("/{booking_id}/tickets")
async def get_booking_tickets(
    booking_id: int,
    current_user: CurrentUser = Depends(get_current_user)
):
    """Get all tickets for a booking (with QR codes)"""
    try:
        # Check ownership first
        booking = await crud_booking.get_booking_by_id(booking_id)
        if not booking:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found"
            )

        if not current_user.is_admin and str(booking.get('user_id')) != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view these tickets"
            )

        tickets = await crud_booking.get_tickets_for_booking(booking_id)
        if not tickets:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No tickets found for this booking"
            )
        return {"tickets": tickets}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tickets: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch tickets: {str(e)}"
        )


@router.get("/user/{user_id}/bookings", response_model=UserBookingsResponse)
async def get_user_bookings(
    user_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    booking_status: Optional[str] = Query(None, alias="status", description="Filter by status (pending, confirmed, cancelled, expired)")
):
    """Get all bookings for a specific user"""
    try:
        # Authorization: Self or Admin
        if not current_user.is_admin and str(user_id) != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view this user's bookings"
            )

        bookings = await crud_booking.get_user_bookings(user_id, booking_status)
        return UserBookingsResponse(
            bookings=bookings,
            total_count=len(bookings)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user bookings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch user bookings: {str(e)}"
        )


# ========== Statistics Endpoints ==========

@router.get("/stats/screens", response_model=List[ScreenStatistics])
async def get_screen_statistics():
    """
    Get occupancy statistics for all screens.
    Shows available, reserved, sold, and maintenance seats count.
    """
    try:
        stats = await crud_booking.get_screen_statistics()
        return stats
    except Exception as e:
        logger.error(f"Error getting screen statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch screen statistics: {str(e)}"
        )


# ========== Worker Endpoint (Internal Use) ==========

@router.post("/internal/release-expired", response_model=ExpiryWorkerResponse)
async def release_expired_reservations():
    """
    Internal endpoint to release expired reservations.
    Should be called by a cron job or worker every minute.
    Can also be called manually for testing.
    """
    try:
        result = await crud_booking.release_expired_reservations()

        from datetime import datetime
        return ExpiryWorkerResponse(
            released_count=result.get('released_count', 0),
            booking_ids=result.get('booking_ids'),
            timestamp=datetime.now()
        )

    except Exception as e:
        logger.error(f"Error releasing expired reservations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to release expired reservations: {str(e)}"
        )


# ========== Admin Endpoints (Optional) ==========

@router.get("/admin/all")
async def get_all_bookings(
    current_user: CurrentUser = Depends(get_current_user),
    booking_status: Optional[str] = Query(None, alias="status", description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """Admin endpoint: Get all bookings with pagination"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    try:
        bookings = await crud_booking.get_all_bookings(booking_status, limit, offset)
        return {"bookings": bookings, "count": len(bookings)}
    except Exception as e:
        logger.error(f"Error getting all bookings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch bookings: {str(e)}"
        )


@router.get("/admin/stats/pending")
async def get_pending_count(current_user: CurrentUser = Depends(get_current_user)):
    """Admin endpoint: Get count of pending bookings"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )

    try:
        count = await crud_booking.get_pending_bookings_count()
        return {"pending_count": count}
    except Exception as e:
        logger.error(f"Error getting pending count: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch pending count: {str(e)}"
        )