"""
reviews router — V1 migration (Option B: fast structural partition).

Legacy routes previously defined inline in ``server.py`` are moved here
verbatim (bodies unchanged) and mounted via ``build_reviews_router(**deps)``.
All external references (db, helpers, services, Pydantic models) are
injected via keyword arguments so this module has no circular import back
to ``server``.

Do NOT add new business logic here without splitting into a dedicated file —
this file exists to keep server.py small; the "canonical" refactor (typed
Pydantic input models per route, explicit dependency signatures) is a
follow-up sprint.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from services import trust_engine
from datetime import datetime, timezone

# `db`, `get_current_user`, and every helper/service/model this module needs
# are captured in the closure of `build_reviews_router(**deps)` below.


def build_reviews_router(**deps) -> APIRouter:
    """Factory: returns an APIRouter mounting every reviews endpoint.

    `deps` MUST include (all names as used inside the extracted route bodies):
    db, get_current_user, now_utc, new_id, trust_engine, recompute_artisan_rating, ReviewInput
    """
    # Explode deps into locals so the extracted route bodies find them by name.
    globals().update(deps)  # noqa: F821 — populates module scope for closures
    _locals = deps
    for _k, _v in _locals.items():
        locals()[_k] = _v

    r = APIRouter()

    @r.post("/reviews")
    async def create_review(data: ReviewInput, user=Depends(get_current_user)):
        booking = await db.bookings.find_one({"booking_id": data.booking_id}, {"_id": 0})
        if not booking:
            raise HTTPException(status_code=404, detail="Réservation introuvable")
        if booking["status"] != "completed":
            raise HTTPException(status_code=400, detail="Vous pourrez noter une fois la mission terminée")
        if data.rating < 1 or data.rating > 5:
            raise HTTPException(status_code=400, detail="La note doit être entre 1 et 5")
        if user["user_id"] == booking["client_id"]:
            to_role = "artisan"
            to_user_id = booking.get("artisan_user_id")
            artisan_id = booking["artisan_id"]
            to_name = booking["artisan_name"]
        elif user["user_id"] == booking.get("artisan_user_id"):
            to_role = "client"
            to_user_id = booking["client_id"]
            artisan_id = None
            to_name = booking["client_name"]
        else:
            raise HTTPException(status_code=403, detail="Non autorisé")
        existing = await db.reviews.find_one({"booking_id": data.booking_id, "from_user_id": user["user_id"]})
        if existing:
            raise HTTPException(status_code=400, detail="Vous avez déjà laissé un avis")
        review = {
            "review_id": new_id("rev"),
            "booking_id": data.booking_id,
            "from_user_id": user["user_id"],
            "from_name": user["name"],
            "to_user_id": to_user_id,
            "to_name": to_name,
            "to_role": to_role,
            "artisan_id": artisan_id,
            "rating": data.rating,
            "comment": data.comment,
            "created_at": now_utc().isoformat(),
        }
        await db.reviews.insert_one(review)
        review.pop("_id", None)
        if to_role == "artisan" and artisan_id:
            await recompute_artisan_rating(artisan_id)
            await trust_engine.persist(db, artisan_id)
        return review


    @r.get("/reviews/artisan/{artisan_id}")
    async def artisan_reviews(artisan_id: str):
        revs = await db.reviews.find({"artisan_id": artisan_id, "to_role": "artisan"}, {"_id": 0}).to_list(500)
        revs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return revs


    return r
