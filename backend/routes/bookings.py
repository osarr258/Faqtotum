"""Bookings router — Sprint 14 Phase 1 Bloc 4.

Migrated endpoints (from server.py lines 271-345):
- POST   /api/bookings
- GET    /api/bookings/mine        (client-side listing)
- GET    /api/bookings/received    (artisan-side listing)
- PATCH  /api/bookings/{booking_id}

Guarantees
----------
- **Ownership on every path**: reader/mutator must be client_id OR artisan_user_id.
- **State machine** lives in services/status_transitions.py — the endpoint just
  reads the current status, calls `check_booking_transition`, and stores the new one.
- **404 uniform** when the resource does not belong to the caller (no enumeration).
- **Audit logs**: creation + every status change.
- **Validation** via Pydantic (max_length, regex on date/slot).
"""
from __future__ import annotations
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, validator

from services import security as security_svc
from services import status_transitions as st


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class BookingInput(BaseModel):
    artisan_id: str = Field(..., min_length=1, max_length=64)
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    # Accept either `HH:MM` (Sprint 14) or legacy range `HH:MM-HH:MM` for backward compat.
    slot: str = Field(..., pattern=r"^([01]\d|2[0-3]):[0-5]\d(?:-([01]\d|2[0-3]):[0-5]\d)?$")
    description: str = Field("", max_length=2000)

    @validator("description")
    def _no_html(cls, v: str) -> str:  # noqa: N805
        if "<script" in v.lower() or "</script" in v.lower():
            raise ValueError("Contenu potentiellement malveillant refusé")
        return v[:2000]

    @validator("artisan_id")
    def _valid_id(cls, v: str) -> str:  # noqa: N805
        if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
            raise ValueError("Identifiant artisan invalide")
        return v


class BookingStatusInput(BaseModel):
    status: str = Field(..., min_length=1, max_length=32)


def build_bookings_router(
    db, get_current_user,
    *,
    enrich_artisan,
    annotate_reviewed,
    trust_engine,
):
    r = APIRouter()

    @r.post("/bookings")
    async def create_booking(data: BookingInput, user=Depends(get_current_user)):
        artisan = await db.artisan_profiles.find_one(
            {"artisan_id": data.artisan_id}, {"_id": 0},
        )
        if not artisan:
            raise HTTPException(status_code=404, detail="Artisan introuvable")
        booking_id = _new_id("bk")
        conv_id = "conv_" + booking_id.split("_", 1)[1]
        booking = {
            "booking_id": booking_id,
            "conversation_id": conv_id,
            "client_id": user["user_id"],
            "client_name": user["name"],
            "artisan_id": data.artisan_id,
            "artisan_user_id": artisan.get("user_id"),
            "artisan_name": artisan.get("name") or artisan.get("title"),
            "trade_name": artisan.get("trade_name"),
            "date": data.date,
            "slot": data.slot,
            "description": data.description,
            "status": "pending",
            "simulated": True,
            "created_at": _now_iso(),
        }
        await db.bookings.insert_one(dict(booking))
        await db.conversations.insert_one({
            "conversation_id": conv_id,
            "booking_id": booking_id,
            "client_id": user["user_id"],
            "client_name": user["name"],
            "artisan_user_id": artisan.get("user_id"),
            "artisan_id": data.artisan_id,
            "artisan_name": artisan.get("name") or artisan.get("title"),
            "trade_name": artisan.get("trade_name"),
            "last_message": "Réservation créée",
            "last_at": _now_iso(),
            "created_at": _now_iso(),
        })
        booking.pop("_id", None)
        await security_svc.audit_log(
            db, action="booking.created", actor_id=user["user_id"],
            actor_role="client", target=booking_id,
            metadata={"artisan_id": data.artisan_id, "date": data.date}, severity="info",
        )
        return booking

    @r.get("/bookings/mine")
    async def my_bookings(user=Depends(get_current_user)):
        # Sort in Mongo (not Python) so newest bookings win when caller has >500 rows.
        bookings = await db.bookings.find(
            {"client_id": user["user_id"]}, {"_id": 0},
        ).sort("created_at", -1).to_list(500)
        return await annotate_reviewed(bookings, user["user_id"])

    @r.get("/bookings/received")
    async def received_bookings(user=Depends(get_current_user)):
        bookings = await db.bookings.find(
            {"artisan_user_id": user["user_id"]}, {"_id": 0},
        ).sort("created_at", -1).to_list(500)
        return await annotate_reviewed(bookings, user["user_id"])

    @r.patch("/bookings/{booking_id}")
    async def update_booking(
        booking_id: str, data: BookingStatusInput, user=Depends(get_current_user),
    ):
        # 1. Read + ownership
        booking = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
        if not booking:
            raise HTTPException(status_code=404, detail="Réservation introuvable")
        actor = st.actor_role_for(booking, user["user_id"])
        if actor is None:
            # 404 to avoid disclosing existence to strangers
            await security_svc.audit_log(
                db, action="booking.access_denied",
                actor_id=user["user_id"], target=booking_id,
                metadata={"attempted_status": data.status}, severity="warn",
            )
            raise HTTPException(status_code=404, detail="Réservation introuvable")

        # 2. State machine
        current = booking.get("status", "pending")
        st.check_booking_transition(current, data.status, actor)

        # 3. Atomic compare-and-set
        result = await db.bookings.update_one(
            {"booking_id": booking_id, "status": current},
            {"$set": {"status": data.status, "status_updated_at": _now_iso()}},
        )
        if result.modified_count == 0:
            # Someone else updated concurrently
            raise HTTPException(
                status_code=409,
                detail="Le statut a changé dans l'intervalle, rechargez la réservation",
            )

        booking["status"] = data.status
        await security_svc.audit_log(
            db, action=f"booking.status.{data.status}",
            actor_id=user["user_id"], actor_role=actor, target=booking_id,
            metadata={"from": current, "to": data.status}, severity="info",
        )

        if data.status == "completed":
            # Loyalty ledger removed in V1 — booking completion no longer
            # awards points. Trust score recomputation still happens below.
            pass
        if booking.get("artisan_id"):
            try:
                await trust_engine.persist(db, booking["artisan_id"])
            except Exception:
                pass
        return booking

    return r
