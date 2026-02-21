"""
CRUD operations for booking system
Handles database operations for seats, bookings, and tickets
"""
from typing import Optional, List, Dict, Any
from uuid import UUID
from supabase import Client
from app.schemas.booking import (
    ReserveSeatRequest,
    BookingDetail,
    AvailableSeat,
    ScreenInfo,
    ScreenStatistics
)
import logging
import asyncio
import json
import ast

logger = logging.getLogger(__name__)


class CRUDBooking:
    """CRUD operations for bookings using Supabase RPC functions"""

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    def _extract_json_from_error(self, e: Exception) -> Optional[Dict[str, Any]]:
        """
        Extract JSON data from Supabase error when response is bytes.
        Handles the case where Supabase returns bytes that it can't parse.
        """
        # Try to get error_dict from args or attributes
        error_dict = None
        if hasattr(e, 'args') and len(e.args) > 0 and isinstance(e.args[0], dict):
            error_dict = e.args[0]
        elif hasattr(e, 'details'):
            # Some exceptions (like APIError) have attributes directly
            error_dict = {
                'message': getattr(e, 'message', str(e)),
                'details': getattr(e, 'details', None),
                'code': getattr(e, 'code', None)
            }

        if error_dict and 'details' in error_dict:
            details = error_dict['details']
            if not details:
                return None

            # If details is already a dict
            if isinstance(details, dict):
                return details

            # If details is bytes
            if isinstance(details, bytes):
                try:
                    return json.loads(details.decode('utf-8'))
                except Exception:
                    pass

            # Extract JSON from bytes string representation (e.g. "b'{\"success\": true}'")
            if isinstance(details, str):
                if details.startswith("b'") or details.startswith('b"'):
                    try:
                        # Use ast.literal_eval to safely convert string representation of bytes
                        bytes_obj = ast.literal_eval(details)
                        if isinstance(bytes_obj, bytes):
                            return json.loads(bytes_obj.decode('utf-8'))
                    except Exception as eval_err:
                        logger.debug(f"ast.literal_eval failed: {eval_err}")
                        # Fallback to manual replacement
                        try:
                            json_str = details[2:-1].replace("\\'", "'").replace('\\"', '"')
                            return json.loads(json_str)
                        except Exception:
                            pass
                else:
                    # Maybe it's just a JSON string
                    try:
                        return json.loads(details)
                    except Exception:
                        pass
        return None

    # ========== Seat Operations ==========

    async def get_available_seats(self, screen_id: int) -> List[AvailableSeat]:
        """Get all available seats for a screen"""
        try:
            response = await asyncio.to_thread(
                lambda: self.client.rpc('get_available_seats', {
                    'p_screen_id': screen_id
                }).execute()
            )

            if response.data:
                return [AvailableSeat(**seat) for seat in response.data]
            return []
        except Exception as e:
            logger.error(f"Error getting available seats: {e}")
            raise

    async def get_all_seats_for_screen(self, screen_id: int) -> List[Dict[str, Any]]:
        """Get all seats for a screen (including unavailable)"""
        try:
            response = await asyncio.to_thread(
                lambda: self.client.table('seats')
                    .select('*')
                    .eq('screen_id', screen_id)
                    .order('row_label', desc=False)
                    .order('seat_number', desc=False)
                    .execute()
            )

            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Error getting seats for screen: {e}")
            raise

    # ========== Booking Operations ==========

    async def reserve_seats(self, request: ReserveSeatRequest) -> Dict[str, Any]:
        """
        Reserve seats for a user (Step 1: User proceeds to payment)
        Calls the Supabase RPC function reserve_seats
        """
        try:
            response = await asyncio.to_thread(
                lambda: self.client.rpc('reserve_seats', {
                    'p_user_id': str(request.user_id),
                    'p_screen_id': request.screen_id,
                    'p_seat_ids': request.seat_ids,
                    'p_price_per_seat': request.price_per_seat
                }).execute()
            )

            if response.data:
                # Handle bytes response from Supabase
                if isinstance(response.data, bytes):
                    return json.loads(response.data.decode('utf-8'))
                return response.data
            raise ValueError("No data returned from reserve_seats")
        except Exception as e:
            # Try to extract JSON from error details
            data = self._extract_json_from_error(e)
            if data:
                return data
            logger.error(f"Error reserving seats: {e}")
            raise

    async def confirm_payment(self, booking_id: int, payment_intent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Confirm payment for a booking (Step 2: Payment successful)
        Calls the Supabase RPC function confirm_payment
        """
        try:
            response = await asyncio.to_thread(
                lambda: self.client.rpc('confirm_payment', {
                    'p_booking_id': booking_id
                }).execute()
            )

            if response.data:
                # Handle bytes response from Supabase
                data = response.data
                if isinstance(data, bytes):
                    data = json.loads(data.decode('utf-8'))

                # Optionally store payment_intent_id
                if payment_intent_id:
                    await asyncio.to_thread(
                        lambda: self.client.table('bookings')
                            .update({'payment_intent_id': payment_intent_id})
                            .eq('id', booking_id)
                            .execute()
                    )

                return data
            raise ValueError("No data returned from confirm_payment")
        except Exception as e:
            # Try to extract JSON from error details
            data = self._extract_json_from_error(e)
            if data:
                # Optionally store payment_intent_id
                if payment_intent_id:
                    await asyncio.to_thread(
                        lambda: self.client.table('bookings')
                            .update({'payment_intent_id': payment_intent_id})
                            .eq('id', booking_id)
                            .execute()
                    )
                return data

            logger.error(f"Error confirming payment: {e}")
            raise

    async def cancel_booking(self, booking_id: int) -> Dict[str, Any]:
        """
        Cancel a booking (User cancels before payment)
        Calls the Supabase RPC function cancel_booking
        """
        try:
            response = await asyncio.to_thread(
                lambda: self.client.rpc('cancel_booking', {
                    'p_booking_id': booking_id
                }).execute()
            )

            if response.data:
                # Handle bytes response from Supabase
                if isinstance(response.data, bytes):
                    return json.loads(response.data.decode('utf-8'))
                return response.data
            raise ValueError("No data returned from cancel_booking")
        except Exception as e:
            # Try to extract JSON from error details
            data = self._extract_json_from_error(e)
            if data:
                return data
            logger.error(f"Error cancelling booking: {e}")
            raise

    async def release_expired_reservations(self) -> Dict[str, Any]:
        """
        Release expired reservations (Called by worker)
        Calls the Supabase RPC function release_expired_reservations
        """
        try:
            response = await asyncio.to_thread(
                lambda: self.client.rpc('release_expired_reservations').execute()
            )

            if response.data:
                # Handle bytes response from Supabase
                if isinstance(response.data, bytes):
                    return json.loads(response.data.decode('utf-8'))
                return response.data
            return {'released_count': 0}
        except Exception as e:
            # Try to extract JSON from error details
            data = self._extract_json_from_error(e)
            if data:
                return data
            logger.error(f"Error releasing expired reservations: {e}")
            raise

    async def get_booking_by_id(self, booking_id: int) -> Optional[Dict[str, Any]]:
        """Get booking details by ID"""
        try:
            response = await asyncio.to_thread(
                lambda: self.client.table('bookings')
                    .select('*')
                    .eq('id', booking_id)
                    .single()
                    .execute()
            )

            return response.data if response.data else None
        except Exception as e:
            logger.error(f"Error getting booking by ID: {e}")
            return None

    async def get_booking_details(self, booking_id: int) -> Optional[BookingDetail]:
        """Get detailed booking information with seats"""
        try:
            response = await asyncio.to_thread(
                lambda: self.client.from_('booking_details')
                    .select('*')
                    .eq('booking_id', booking_id)
                    .single()
                    .execute()
            )

            if response.data:
                return BookingDetail(**response.data)
            return None
        except Exception as e:
            logger.error(f"Error getting booking details: {e}")
            return None

    async def get_user_bookings(self, user_id: UUID, status: Optional[str] = None) -> List[BookingDetail]:
        """Get all bookings for a user"""
        try:
            def _fetch():
                query = self.client.from_('booking_details')\
                    .select('*')\
                    .eq('user_id', str(user_id))\
                    .order('created_at', desc=True)

                if status:
                    query = query.eq('booking_status', status)

                return query.execute()

            response = await asyncio.to_thread(_fetch)

            if response.data:
                return [BookingDetail(**booking) for booking in response.data]
            return []
        except Exception as e:
            logger.error(f"Error getting user bookings: {e}")
            raise

    async def get_tickets_for_booking(self, booking_id: int) -> List[Dict[str, Any]]:
        """Get all tickets for a booking"""
        try:
            response = await asyncio.to_thread(
                lambda: self.client.table('tickets')
                    .select('*, seats(row_label, seat_number)')
                    .eq('booking_id', booking_id)
                    .execute()
            )

            if response.data:
                # Format the data
                tickets = []
                for ticket in response.data:
                    ticket_info = {
                        'ticket_id': ticket['id'],
                        'booking_id': ticket['booking_id'],
                        'seat_id': ticket['seat_id'],
                        'price_paid': ticket['price_paid'],
                        'qr_code_slug': ticket['qr_code_slug'],
                        'row_label': ticket['seats']['row_label'],
                        'seat_number': ticket['seats']['seat_number']
                    }
                    tickets.append(ticket_info)
                return tickets
            return []
        except Exception as e:
            logger.error(f"Error getting tickets for booking: {e}")
            raise

    # ========== Screen Operations ==========

    async def get_all_screens(self) -> List[ScreenInfo]:
        """Get all screens"""
        try:
            response = await asyncio.to_thread(
                lambda: self.client.table('screens')
                    .select('*')
                    .execute()
            )

            if response.data:
                return [ScreenInfo(
                    screen_id=screen['id'],
                    name=screen['name'],
                    size=screen['size'],
                    total_seats=screen['total_seats']
                ) for screen in response.data]
            return []
        except Exception as e:
            logger.error(f"Error getting screens: {e}")
            raise

    async def get_screen_by_id(self, screen_id: int) -> Optional[ScreenInfo]:
        """Get screen by ID"""
        try:
            response = await asyncio.to_thread(
                lambda: self.client.table('screens')
                    .select('*')
                    .eq('id', screen_id)
                    .single()
                    .execute()
            )

            if response.data:
                screen = response.data
                return ScreenInfo(
                    screen_id=screen['id'],
                    name=screen['name'],
                    size=screen['size'],
                    total_seats=screen['total_seats']
                )
            return None
        except Exception as e:
            logger.error(f"Error getting screen by ID: {e}")
            return None

    async def get_screen_statistics(self) -> List[ScreenStatistics]:
        """Get occupancy statistics for all screens"""
        try:
            response = await asyncio.to_thread(
                lambda: self.client.from_('screen_statistics')
                    .select('*')
                    .execute()
            )

            if response.data:
                return [ScreenStatistics(**stat) for stat in response.data]
            return []
        except Exception as e:
            logger.error(f"Error getting screen statistics: {e}")
            raise

    # ========== Admin Operations ==========

    async def update_booking_status(self, booking_id: int, status: str) -> Optional[Dict[str, Any]]:
        """Update booking status (admin only)"""
        try:
            response = await asyncio.to_thread(
                lambda: self.client.table('bookings')
                    .update({'status': status})
                    .eq('id', booking_id)
                    .execute()
            )

            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error updating booking status: {e}")
            raise

    async def get_all_bookings(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get all bookings (admin only)"""
        try:
            def _fetch():
                query = self.client.table('bookings')\
                    .select('*')\
                    .order('created_at', desc=True)\
                    .limit(limit)\
                    .offset(offset)

                if status:
                    query = query.eq('status', status)

                return query.execute()

            response = await asyncio.to_thread(_fetch)
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Error getting all bookings: {e}")
            raise

    async def get_pending_bookings_count(self) -> int:
        """Get count of pending bookings"""
        try:
            response = await asyncio.to_thread(
                lambda: self.client.table('bookings')
                    .select('id', count='exact')
                    .eq('status', 'pending')
                    .execute()
            )

            return response.count if response.count else 0
        except Exception as e:
            logger.error(f"Error getting pending bookings count: {e}")
            return 0