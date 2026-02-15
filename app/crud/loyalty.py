from supabase import Client
from typing import Dict, Any
import asyncio
import json
import logging

logger = logging.getLogger(__name__)


class CRUDLoyalty:
    __slots__ = ('client',)

    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    def _parse_rpc_response(self, data: Any) -> Dict[str, Any]:
        if isinstance(data, bytes):
            try:
                return json.loads(data.decode('utf-8'))
            except Exception as e:
                logger.error(f"Failed to decode RPC bytes response: {e}")
                return {}
        if isinstance(data, str):
            try:
                return json.loads(data)
            except Exception:
                return {}
        if isinstance(data, dict):
            return data
        return {}

    async def get_balance(self, user_id: str) -> int:
        response = await asyncio.to_thread(
            lambda: self.client.table("users")
                .select("loyalty_points")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
        )
        if not response.data:
            return 0
        return int(response.data.get("loyalty_points") or 0)

    async def get_history(self, user_id: str, limit: int, offset: int) -> Dict[str, Any]:
        response = await asyncio.to_thread(
            lambda: self.client.table("loyalty_transactions")
                .select("*", count="exact")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
        )
        return {
            "items": response.data or [],
            "total_count": response.count or 0
        }

    async def award_booking_points(self, booking_id: int) -> Dict[str, Any]:
        response = await asyncio.to_thread(
            lambda: self.client.rpc("award_booking_points", {
                "p_booking_id": booking_id
            }).execute()
        )
        return self._parse_rpc_response(response.data)

    async def award_review_points(self, user_id: str, movie_id: int) -> Dict[str, Any]:
        response = await asyncio.to_thread(
            lambda: self.client.rpc("award_review_points", {
                "p_user_id": user_id,
                "p_movie_id": movie_id
            }).execute()
        )
        return self._parse_rpc_response(response.data)

    async def redeem_booking_points(self, booking_id: int, points_to_use: int) -> Dict[str, Any]:
        response = await asyncio.to_thread(
            lambda: self.client.rpc("redeem_booking_points", {
                "p_booking_id": booking_id,
                "p_points_to_use": points_to_use
            }).execute()
        )
        return self._parse_rpc_response(response.data)

    async def refund_booking_points(self, booking_id: int) -> Dict[str, Any]:
        response = await asyncio.to_thread(
            lambda: self.client.rpc("refund_booking_points", {
                "p_booking_id": booking_id
            }).execute()
        )
        return self._parse_rpc_response(response.data)
