from pydantic import BaseModel, Field, UUID4
from datetime import datetime
from typing import List, Optional
from enum import Enum
from uuid import UUID


class BookingStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class SeatStatus(str, Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    SOLD = "sold"
    MAINTENANCE = "maintenance"


# ===== Seat Schemas =====
class SeatBase(BaseModel):
    row_label: str = Field(..., description="Row label (e.g., A, B, C)")
    seat_number: int = Field(..., gt=0, description="Seat number")


class SeatInfo(SeatBase):
    seat_id: int = Field(..., description="Seat ID")
    status: SeatStatus
    screen_id: int


class AvailableSeat(BaseModel):
    seat_id: int
    row_label: str
    seat_number: int
    status: str


# ===== Booking Request Schemas =====
class ReserveSeatRequest(BaseModel):
    """Request to reserve seats (Step 1: User proceeds to payment)"""
    user_id: UUID = Field(..., description="User UUID from Supabase auth")
    screen_id: int = Field(..., description="Screen ID")
    seat_ids: List[int] = Field(..., min_length=1, max_length=10, description="List of seat IDs to reserve")
    price_per_seat: float = Field(default=15.00, gt=0, description="Price per seat in THB")
    loyalty_points_to_use: int = Field(default=0, ge=0, description="Loyalty points to redeem")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "screen_id": 1,
                "seat_ids": [1, 2, 3],
                "price_per_seat": 15.00,
                "loyalty_points_to_use": 100
            }
        }


class ReserveSeatResponse(BaseModel):
    """Response after reserving seats"""
    success: bool
    booking_id: Optional[int] = None
    payment_deadline: Optional[datetime] = None
    total_amount: Optional[float] = None
    loyalty_points_used: Optional[int] = None
    discount_amount: Optional[float] = None
    error: Optional[str] = None
    unavailable_seats: Optional[List[int]] = None


class ConfirmPaymentRequest(BaseModel):
    """Request to confirm payment (Step 2: Payment successful)"""
    booking_id: int = Field(..., description="Booking ID")
    payment_intent_id: Optional[str] = Field(None, description="Payment gateway transaction ID")


class ConfirmPaymentResponse(BaseModel):
    """Response after confirming payment"""
    success: bool
    message: str
    booking_id: Optional[int] = None
    tickets: Optional[List[dict]] = None


class CancelBookingRequest(BaseModel):
    """Request to cancel a booking"""
    booking_id: int


class CancelBookingResponse(BaseModel):
    """Response after canceling booking"""
    success: bool
    message: str


# ===== Booking Models =====
class BookingBase(BaseModel):
    screen_id: int
    total_amount: float


class BookingCreate(BookingBase):
    user_id: UUID
    status: BookingStatus = BookingStatus.PENDING


class BookingUpdate(BaseModel):
    status: Optional[BookingStatus] = None
    payment_intent_id: Optional[str] = None


class BookingInDB(BookingBase):
    id: int
    user_id: UUID
    status: BookingStatus
    payment_deadline: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BookingDetail(BaseModel):
    """Detailed booking information with seats"""
    booking_id: int
    user_id: UUID
    booking_status: str
    total_amount: float
    payment_deadline: datetime
    created_at: datetime
    screen_name: str
    seats: List[str]  # e.g., ["A1", "A2", "A3"]
    movie_title: Optional[str] = None
    poster_url: Optional[str] = None
    showtime_start: Optional[str] = None
    showtime_id: Optional[int] = None


class TicketInfo(BaseModel):
    """Individual ticket information"""
    ticket_id: int
    booking_id: int
    seat_id: int
    row_label: str
    seat_number: int

class UserBookingsResponse(BaseModel):
    """List of user's bookings"""
    bookings: List[BookingDetail]
    total_count: int


# ===== Screen Schemas =====
class ScreenInfo(BaseModel):
    screen_id: int
    name: str
    size: str
    total_seats: int


class ScreenStatistics(BaseModel):
    """Screen occupancy statistics"""
    screen_id: int
    screen_name: str
    total_seats: int
    available_seats: int
    reserved_seats: int
    sold_seats: int
    maintenance_seats: int


# ===== Expiry Worker Response =====
class ExpiryWorkerResponse(BaseModel):
    """Response from expiry worker"""
    released_count: int
    booking_ids: Optional[List[str]] = None
    timestamp: datetime = Field(default_factory=datetime.now)
