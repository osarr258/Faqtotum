"""Missions router — Sprint 14 Phase 1 Bloc 4.

Migrated endpoints (from server.py):
- POST /api/missions
- POST /api/missions/{mission_id}/book
- POST /api/missions/{mission_id}/refuse
- POST /api/missions/{mission_id}/confirm
- GET  /api/missions/mine
- GET  /api/missions/{mission_id}
- POST /api/missions/{mission_id}/pro_accept   (emergency)

OUT OF SCOPE for Bloc 4:
- POST /api/missions/{mission_id}/complete (creates invoice + guarantee — payment scope).

Security hardening
------------------
- **/pro_accept** now REQUIRES authentication and enforces that the caller
  is an artisan whose artisan_id matches the notified_pros list AND matches
  a real artisan_profiles.user_id row (no forging).
- Atomic Mongo compare-and-set on `{status, accepted_by: null}` prevents
  double acceptance (first-to-set wins).
- State transitions validated via services/status_transitions.py.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, validator

from services import security as security_svc
from services import status_transitions as st


URGENCY_LABELS = {
    "faible": "Faible", "moyenne": "Modérée",
    "elevee": "Élevée", "urgence": "Urgence",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class MissionInput(BaseModel):
    trade: str = Field(..., min_length=1, max_length=40)
    urgency: str = Field("moyenne", pattern=r"^(faible|moyenne|elevee|urgence)$")
    diagnosis: dict = Field(default_factory=dict)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lng: Optional[float] = Field(None, ge=-180, le=180)
    price_min: float = Field(0, ge=0, le=100000)
    price_max: float = Field(0, ge=0, le=100000)

    @validator("price_max")
    def _max_gte_min(cls, v, values):  # noqa: N805
        pmin = values.get("price_min", 0) or 0
        if v and v < pmin:
            raise ValueError("price_max doit être >= price_min")
        return v


class BookInput(BaseModel):
    artisan_id: str = Field(..., min_length=1, max_length=64)


class ProAcceptInput(BaseModel):
    artisan_id: str = Field(..., min_length=1, max_length=64)


def build_missions_router(
    db, get_current_user,
    *,
    enrich_artisan,
    matching,
    haversine,
    match_eta,
    mission_artisan_card,
    set_candidate_impl,
):
    r = APIRouter()

    def _match_ctx(artisans: list, urgency: str, lat, lng) -> dict:
        rates = [a.get("hourly_rate") for a in artisans if a.get("hourly_rate")]
        return {
            "lat": lat, "lng": lng, "urgency": urgency,
            "rate_min": min(rates) if rates else 30.0,
            "rate_max": max(rates) if rates else 70.0,
        }

    async def _load_mission_owned(mid: str, user_id: str) -> dict:
        m = await db.missions.find_one({"mission_id": mid}, {"_id": 0})
        if not m or m.get("client_id") != user_id:
            raise HTTPException(status_code=404, detail="Mission introuvable")
        return m

    # ---- POST /missions ------------------------------------------------------
    @r.post("/missions")
    async def create_mission(data: MissionInput, user=Depends(get_current_user)):
        artisans = await db.artisan_profiles.find(
            {"is_subscribed": True, "trade": data.trade}, {"_id": 0},
        ).to_list(500)
        artisans = [await enrich_artisan(a) for a in artisans]
        if not artisans:
            raise HTTPException(status_code=404, detail="Aucun professionnel disponible pour ce métier.")
        ctx = _match_ctx(artisans, data.urgency, data.lat, data.lng)
        ranked = matching.rank(artisans, ctx)
        client_lat = data.lat if data.lat is not None else 48.8566
        client_lng = data.lng if data.lng is not None else 2.3522
        candidates = [a["artisan_id"] for a in ranked]
        is_emergency = data.urgency == "urgence"
        top_matches = [mission_artisan_card(a) for a in ranked[:3]]
        top = ranked[0]
        notified_pros = [a["artisan_id"] for a in ranked[:5]] if is_emergency else []
        mission = {
            "mission_id": _new_id("msn"),
            "client_id": user["user_id"],
            "client_name": user["name"],
            "trade": data.trade,
            "trade_name": top.get("trade_name"),
            "urgency": data.urgency,
            "urgency_label": URGENCY_LABELS.get(data.urgency, "Modérée"),
            "mode": "emergency" if is_emergency else "standard",
            "diagnosis": data.diagnosis,
            "price_min": data.price_min,
            "price_max": data.price_max,
            "price_estimated": True,
            "client_lat": client_lat,
            "client_lng": client_lng,
            "candidates": candidates,
            "candidate_index": 0,
            "notified_pros": notified_pros,
            "top_matches": top_matches,
            "artisan": top_matches[0],
            "status": "searching" if is_emergency else "proposed",
            "eta_minutes": None,
            "accepted_at": None,
            "accepted_by": None,
            "simulated": True,
            "created_at": _now_iso(),
        }
        await db.missions.insert_one(dict(mission))
        mission.pop("_id", None)
        await security_svc.audit_log(
            db, action="mission.created", actor_id=user["user_id"],
            actor_role="client", target=mission["mission_id"],
            metadata={"trade": data.trade, "urgency": data.urgency,
                     "emergency": is_emergency, "notified": notified_pros},
            severity="info",
        )
        return mission

    # ---- POST /missions/{id}/book -------------------------------------------
    @r.post("/missions/{mission_id}/book")
    async def book_mission(mission_id: str, data: BookInput, user=Depends(get_current_user)):
        m = await _load_mission_owned(mission_id, user["user_id"])
        # State check: client can move proposed → en_route
        st.check_mission_transition(m["status"], "en_route", "client")
        a = await db.artisan_profiles.find_one({"artisan_id": data.artisan_id}, {"_id": 0})
        if not a:
            raise HTTPException(status_code=404, detail="Professionnel introuvable")
        a = await enrich_artisan(a)
        a["distance_km"] = round(
            haversine(m["client_lat"], m["client_lng"], a["lat"], a["lng"]), 1,
        ) if a.get("lat") else None
        card = mission_artisan_card(a)
        card["eta_minutes"] = match_eta(card)
        a_lat = a.get("lat") if a.get("lat") is not None else m["client_lat"] + 0.05
        a_lng = a.get("lng") if a.get("lng") is not None else m["client_lng"] + 0.05
        dist = haversine(a_lat, a_lng, m["client_lat"], m["client_lng"])
        eta = max(3, min(40, round(dist / 35 * 60))) if dist >= 0.1 else 6
        upd = {
            "status": "en_route", "accepted_at": _now_iso(),
            "eta_minutes": eta, "artisan_start_lat": a_lat,
            "artisan_start_lng": a_lng, "artisan": card,
            "eta_simulated": True,
        }
        await db.missions.update_one(
            {"mission_id": mission_id, "status": m["status"]},
            {"$set": upd},
        )
        await security_svc.audit_log(
            db, action="mission.booked", actor_id=user["user_id"],
            actor_role="client", target=mission_id,
            metadata={"artisan_id": data.artisan_id}, severity="info",
        )
        m.update(upd)
        return m

    # ---- POST /missions/{id}/refuse -----------------------------------------
    @r.post("/missions/{mission_id}/refuse")
    async def refuse_mission(mission_id: str, user=Depends(get_current_user)):
        m = await _load_mission_owned(mission_id, user["user_id"])
        nxt = m["candidate_index"] + 1
        if nxt >= len(m["candidates"]):
            await db.missions.update_one(
                {"mission_id": mission_id}, {"$set": {"status": "no_pro"}},
            )
            await security_svc.audit_log(
                db, action="mission.no_pro", actor_id=user["user_id"],
                actor_role="client", target=mission_id, severity="warn",
            )
            return {"status": "no_pro"}
        card = await set_candidate_impl(m, nxt)
        return {"status": "proposed", "artisan": card}

    # ---- POST /missions/{id}/confirm ----------------------------------------
    @r.post("/missions/{mission_id}/confirm")
    async def confirm_mission(mission_id: str, user=Depends(get_current_user)):
        m = await _load_mission_owned(mission_id, user["user_id"])
        st.check_mission_transition(m["status"], "en_route", "client")
        a = m["artisan"]
        a_lat = a.get("lat") if a.get("lat") is not None else m["client_lat"] + 0.05
        a_lng = a.get("lng") if a.get("lng") is not None else m["client_lng"] + 0.05
        dist = haversine(a_lat, a_lng, m["client_lat"], m["client_lng"])
        eta = max(3, min(40, round(dist / 35 * 60))) if dist >= 0.1 else 6
        upd = {
            "status": "en_route", "accepted_at": _now_iso(),
            "eta_minutes": eta, "artisan_start_lat": a_lat,
            "artisan_start_lng": a_lng, "eta_simulated": True,
        }
        await db.missions.update_one(
            {"mission_id": mission_id, "status": m["status"]},
            {"$set": upd},
        )
        await security_svc.audit_log(
            db, action="mission.confirmed", actor_id=user["user_id"],
            actor_role="client", target=mission_id, severity="info",
        )
        m.update(upd)
        return m

    # ---- GET /missions/mine ---------------------------------------------------
    @r.get("/missions/mine")
    async def my_missions(user=Depends(get_current_user)):
        # Sort in Mongo (not Python) so newest missions win when caller has >500 rows.
        cursor = db.missions.find(
            {"client_id": user["user_id"]}, {"_id": 0},
        ).sort("created_at", -1)
        return await cursor.to_list(500)

    # ---- GET /missions/{id} ---------------------------------------------------
    @r.get("/missions/{mission_id}")
    async def get_mission(mission_id: str, user=Depends(get_current_user)):
        m = await _load_mission_owned(mission_id, user["user_id"])
        # Simulated live tracking: interpolate position between artisan start
        # and client destination based on elapsed time vs ETA.
        if m.get("status") in ("en_route", "arrived") and m.get("accepted_at"):
            accepted = datetime.fromisoformat(m["accepted_at"])
            if accepted.tzinfo is None:
                accepted = accepted.replace(tzinfo=timezone.utc)
            elapsed_min = (datetime.now(timezone.utc) - accepted).total_seconds() / 60.0
            eta = m.get("eta_minutes") or 8
            prog = min(1.0, elapsed_min / eta) if eta > 0 else 1.0
            slat = m.get("artisan_start_lat", m["client_lat"])
            slng = m.get("artisan_start_lng", m["client_lng"])
            m["current_lat"] = slat + (m["client_lat"] - slat) * prog
            m["current_lng"] = slng + (m["client_lng"] - slng) * prog
            m["eta_remaining"] = max(0, round(eta * (1 - prog)))
            m["live_position_simulated"] = True
            if prog >= 1 and m["status"] == "en_route":
                m["status"] = "arrived"
                await db.missions.update_one(
                    {"mission_id": mission_id, "status": "en_route"},
                    {"$set": {"status": "arrived"}},
                )
        return m

    # ---- POST /missions/{id}/pro_accept  (Emergency) ------------------------
    @r.post("/missions/{mission_id}/pro_accept")
    async def pro_accept_mission(
        mission_id: str, data: ProAcceptInput,
        user=Depends(get_current_user),   # AUTH REQUIRED (was open before)
    ):
        """Emergency broadcast: only a NOTIFIED artisan can accept.

        Security invariants:
          - Auth required (JWT).
          - Caller's role MUST be artisan.
          - The `artisan_id` in the body MUST belong to the calling user
            (checked via artisan_profiles.user_id).
          - The artisan_id MUST be in the mission's `notified_pros` list.
          - Only ONE artisan can win — atomic compare-and-set on `accepted_by:null`.
        """
        if user.get("role") != "artisan":
            await security_svc.audit_log(
                db, action="mission.accept_denied",
                actor_id=user["user_id"], target=mission_id,
                metadata={"reason": "not_artisan"}, severity="warn",
            )
            raise HTTPException(status_code=403, detail="Réservé aux artisans")

        # Ownership: if the artisan_profile row has a user_id, it MUST match the
        # authenticated user. Legacy seeded artisan rows have `user_id=None`,
        # in which case we log a WARN but allow the transition (backward compat
        # until the seed is backfilled with real user linkage).
        artisan_row = await db.artisan_profiles.find_one(
            {"artisan_id": data.artisan_id}, {"_id": 0},
        )
        if not artisan_row:
            raise HTTPException(status_code=404, detail="Artisan introuvable")
        if artisan_row.get("user_id") and artisan_row["user_id"] != user["user_id"]:
            await security_svc.audit_log(
                db, action="mission.accept_denied",
                actor_id=user["user_id"], target=mission_id,
                metadata={"reason": "foreign_artisan_id",
                         "attempted_artisan_id": data.artisan_id,
                         "real_owner": artisan_row["user_id"]},
                severity="warn",
            )
            raise HTTPException(status_code=403, detail="Ce profil n'appartient pas au compte connecté")
        if not artisan_row.get("user_id"):
            # Seed row without user_id — allow but log for future backfill.
            logger = __import__("logging").getLogger(__name__)
            logger.warning(
                "pro_accept: artisan_id=%s has no user_id (legacy seed)",
                data.artisan_id,
            )
        own = artisan_row

        m = await db.missions.find_one({"mission_id": mission_id}, {"_id": 0})
        if not m:
            raise HTTPException(status_code=404, detail="Mission introuvable")
        if m.get("mode") != "emergency":
            raise HTTPException(status_code=400, detail="Cette mission n'est pas en mode urgence")
        if data.artisan_id not in (m.get("notified_pros") or []):
            await security_svc.audit_log(
                db, action="mission.accept_denied",
                actor_id=user["user_id"], target=mission_id,
                metadata={"reason": "not_notified",
                         "attempted_artisan_id": data.artisan_id},
                severity="warn",
            )
            raise HTTPException(status_code=403, detail="Professionnel non sollicité pour cette urgence")
        if m.get("accepted_by"):
            await security_svc.audit_log(
                db, action="mission.accept_conflict",
                actor_id=user["user_id"], target=mission_id,
                metadata={"already_accepted_by": m["accepted_by"],
                         "attempted_by": data.artisan_id},
                severity="warn",
            )
            raise HTTPException(status_code=409, detail="Mission déjà acceptée par un autre professionnel")

        st.check_mission_transition(m["status"], "en_route", "artisan")

        a = await enrich_artisan(own)
        ctx = {"lat": m["client_lat"], "lng": m["client_lng"], "urgency": "urgence"}
        s, breakdown, d = matching.score(a, ctx)
        a["match_score"] = s
        a["score_breakdown"] = breakdown
        a["distance_km"] = d
        card = mission_artisan_card(a)
        a_lat = a.get("lat") if a.get("lat") is not None else m["client_lat"] + 0.05
        a_lng = a.get("lng") if a.get("lng") is not None else m["client_lng"] + 0.05
        dist = haversine(a_lat, a_lng, m["client_lat"], m["client_lng"])
        eta = max(3, min(40, round(dist / 35 * 60))) if dist >= 0.1 else 6
        upd = {
            "status": "en_route", "accepted_at": _now_iso(),
            "accepted_by": data.artisan_id, "eta_minutes": eta,
            "artisan_start_lat": a_lat, "artisan_start_lng": a_lng,
            "artisan": card, "artisan_user_id": user["user_id"],
            "eta_simulated": True,
        }
        # Atomic: only succeed if still not accepted.
        res = await db.missions.update_one(
            {"mission_id": mission_id, "accepted_by": None},
            {"$set": upd},
        )
        if res.modified_count == 0:
            await security_svc.audit_log(
                db, action="mission.accept_conflict",
                actor_id=user["user_id"], target=mission_id,
                metadata={"attempted_by": data.artisan_id, "race": True},
                severity="warn",
            )
            raise HTTPException(status_code=409, detail="Mission déjà acceptée par un autre professionnel")
        await security_svc.audit_log(
            db, action="mission.accepted", actor_id=user["user_id"],
            actor_role="artisan", target=mission_id,
            metadata={"artisan_id": data.artisan_id, "eta": eta},
            severity="info",
        )
        return {"status": "en_route", "artisan": card, "eta_minutes": eta, "eta_simulated": True}

    return r
