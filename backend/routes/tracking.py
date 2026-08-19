"""FAQTOTUM V1 — Suivi (tracking) client-side.

Endpoint unifié pour la vue "carte de suivi" côté client, indépendamment
du type d'origine (booking classique ou broadcast).

Fusionne :
  - `bookings` (status, client_id, artisan_user_id, urgent, date/slot)
  - `artisan_profiles.current_lat/lng` (position live poussée par l'artisan)
  - `intervention.client_lat/lng` si dispo, sinon on masque
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException


def build_tracking_router(db, get_current_user) -> APIRouter:
    r = APIRouter()

    @r.get("/tracking/{booking_id}")
    async def get_tracking(booking_id: str, user=Depends(get_current_user)):
        b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
        if not b:
            raise HTTPException(status_code=404, detail="Booking introuvable")
        # Access control : client OR winning artisan.
        is_client = b.get("client_id") == user["user_id"]
        is_artisan = b.get("artisan_user_id") == user["user_id"]
        if not (is_client or is_artisan):
            raise HTTPException(status_code=404, detail="Booking introuvable")
        payload: Dict[str, Any] = {
            "booking_id": b["booking_id"],
            "status": b.get("status") or "pending",
            "urgent": bool(b.get("urgent")),
            "date": b.get("date"),
            "slot": b.get("slot"),
            "description": b.get("description"),
            "client_name": b.get("client_name"),
            "estimated_price_min_eur": b.get("estimated_price_min_eur"),
            "estimated_price_max_eur": b.get("estimated_price_max_eur"),
            "caution_cents": b.get("caution_cents"),
        }
        # Artisan profile snapshot (public safe).
        art: Optional[Dict[str, Any]] = None
        if b.get("artisan_id"):
            art = await db.artisan_profiles.find_one(
                {"artisan_id": b["artisan_id"]},
                {
                    "_id": 0, "artisan_id": 1, "name": 1, "title": 1, "photo": 1,
                    "trade_name": 1, "trade": 1, "rating": 1, "jobs_done": 1,
                    "current_lat": 1, "current_lng": 1,
                    "available_now": 1, "response_min": 1,
                },
            )
        payload["artisan"] = art or None
        # Adresse : révélée UNIQUEMENT à l'artisan attitré, une fois accepté.
        if is_artisan and b.get("status") in {
            "accepted", "confirmed", "en_route",
            "arrived", "in_progress", "awaiting_validation",
        }:
            payload["client_address"] = b.get("address") or b.get("client_address")
        return payload

    return r
