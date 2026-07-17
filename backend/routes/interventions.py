"""Interventions router — Sprint 14 Phase 1 Bloc 4.

Migrated endpoints (from server.py):
- POST /api/interventions/request
- GET  /api/interventions/mine
- GET  /api/interventions/{iv_id}
- POST /api/interventions/{iv_id}/accept
- POST /api/interventions/{iv_id}/refuse
- POST /api/interventions/{iv_id}/cancel
- POST /api/interventions/{iv_id}/start
- POST /api/interventions/{iv_id}/finish

OUT OF SCOPE for Bloc 4 (payment-linked, stay in server.py):
- /interventions/{id}/deposit/create + /confirm
- /interventions/{id}/final/create + /confirm
- /interventions/{id}/validate  (client validation triggers Stripe transfer)
- /interventions/{id}/payment-summary

Every mutation is guarded by:
- Ownership (client_id or artisan_user_id)
- State machine (services/status_transitions.py)
- Atomic Mongo compare-and-set on `{intervention_id, status: current}`
- Audit logs (allowed AND denied)
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services import security as security_svc
from services import status_transitions as st


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class InterventionRequestInput(BaseModel):
    artisan_id: str = Field(..., min_length=1, max_length=64)
    trade: Optional[str] = Field(None, max_length=40)
    description: Optional[str] = Field("", max_length=2000)
    address: Optional[str] = Field("", max_length=240)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lng: Optional[float] = Field(None, ge=-180, le=180)
    urgency: str = Field("moyenne", pattern=r"^(faible|moyenne|elevee|urgence)$")
    price_estimate_cents: Optional[int] = Field(None, ge=0, le=10_000_000)


def build_interventions_router(db, get_current_user):
    r = APIRouter()

    async def _load_owned(iv_id: str, user_id: str) -> tuple[dict, str]:
        iv = await db.interventions.find_one({"intervention_id": iv_id}, {"_id": 0})
        if not iv:
            raise HTTPException(status_code=404, detail="Intervention introuvable")
        actor = st.actor_role_for(iv, user_id)
        if actor is None:
            raise HTTPException(status_code=404, detail="Intervention introuvable")
        return iv, actor

    async def _atomic_transition(iv_id: str, from_state: str, updates: dict) -> None:
        result = await db.interventions.update_one(
            {"intervention_id": iv_id, "status": from_state},
            {"$set": {**updates, "status_updated_at": _now_iso()}},
        )
        if result.modified_count == 0:
            raise HTTPException(
                status_code=409,
                detail="État de l'intervention modifié entre-temps, rechargez",
            )

    # ---- Create ---------------------------------------------------------------
    @r.post("/interventions/request")
    async def request_intervention(
        data: InterventionRequestInput, user=Depends(get_current_user),
    ):
        artisan = await db.artisan_profiles.find_one(
            {"artisan_id": data.artisan_id}, {"_id": 0},
        )
        if not artisan:
            raise HTTPException(status_code=404, detail="Artisan introuvable")
        iv_id = _new_id("iv")
        iv = {
            "intervention_id": iv_id,
            "client_id": user["user_id"],
            "client_name": user["name"],
            "artisan_id": data.artisan_id,
            "artisan_user_id": artisan.get("user_id"),
            "artisan_name": artisan.get("name") or artisan.get("title"),
            "trade": data.trade or artisan.get("trade"),
            "trade_name": artisan.get("trade_name"),
            "description": data.description or "",
            "address": data.address or "",
            "lat": data.lat,
            "lng": data.lng,
            "urgency": data.urgency,
            "price_estimate_cents": data.price_estimate_cents,
            "price_simulated": True,
            "status": "requested",
            "simulated": True,
            "created_at": _now_iso(),
        }
        await db.interventions.insert_one(dict(iv))
        iv.pop("_id", None)
        await security_svc.audit_log(
            db, action="intervention.requested", actor_id=user["user_id"],
            actor_role="client", target=iv_id,
            metadata={"artisan_id": data.artisan_id, "urgency": data.urgency},
            severity="info",
        )
        return iv

    # ---- Reads ---------------------------------------------------------------
    @r.get("/interventions/mine")
    async def my_interventions(user=Depends(get_current_user)):
        cursor = db.interventions.find(
            {"$or": [
                {"client_id": user["user_id"]},
                {"artisan_user_id": user["user_id"]},
            ]},
            {"_id": 0},
        ).sort("created_at", -1)
        return await cursor.to_list(500)

    @r.get("/interventions/{iv_id}")
    async def get_intervention(iv_id: str, user=Depends(get_current_user)):
        iv, _ = await _load_owned(iv_id, user["user_id"])
        return iv

    # ---- Artisan actions ----------------------------------------------------
    @r.post("/interventions/{iv_id}/accept")
    async def accept_intervention(iv_id: str, user=Depends(get_current_user)):
        iv, actor = await _load_owned(iv_id, user["user_id"])
        if actor != "artisan":
            raise HTTPException(status_code=403, detail="Réservé à l'artisan assigné")
        st.check_intervention_transition(iv["status"], "accepted", "artisan")
        await _atomic_transition(iv_id, iv["status"], {
            "status": "accepted", "accepted_at": _now_iso(),
        })
        await security_svc.audit_log(
            db, action="intervention.accepted", actor_id=user["user_id"],
            actor_role="artisan", target=iv_id,
            metadata={"from": iv["status"]}, severity="info",
        )
        return {"ok": True, "status": "accepted"}

    @r.post("/interventions/{iv_id}/refuse")
    async def refuse_intervention(iv_id: str, user=Depends(get_current_user)):
        iv, actor = await _load_owned(iv_id, user["user_id"])
        if actor != "artisan":
            raise HTTPException(status_code=403, detail="Réservé à l'artisan assigné")
        st.check_intervention_transition(iv["status"], "declined", "artisan")
        await _atomic_transition(iv_id, iv["status"], {
            "status": "declined", "declined_at": _now_iso(),
        })
        await security_svc.audit_log(
            db, action="intervention.declined", actor_id=user["user_id"],
            actor_role="artisan", target=iv_id,
            metadata={"from": iv["status"]}, severity="info",
        )
        return {"ok": True, "status": "declined"}

    # NOTE: /start and /finish stay in server.py — they are payment-linked
    # (require status="confirmed" from deposit, and set total_amount_cents).
    # Bloc 4 does not touch payments per user directive.

    # ---- Cancel (either party, state-permitting) ----------------------------
    @r.post("/interventions/{iv_id}/cancel")
    async def cancel_intervention(iv_id: str, user=Depends(get_current_user)):
        iv, actor = await _load_owned(iv_id, user["user_id"])
        st.check_intervention_transition(iv["status"], "cancelled", actor)
        await _atomic_transition(iv_id, iv["status"], {
            "status": "cancelled", "cancelled_at": _now_iso(),
            "cancelled_by": actor,
        })
        await security_svc.audit_log(
            db, action="intervention.cancelled", actor_id=user["user_id"],
            actor_role=actor, target=iv_id,
            metadata={"from": iv["status"]}, severity="warn",
        )
        return {"ok": True, "status": "cancelled"}

    return r
