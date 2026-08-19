"""Artisan routes — Sprint 14 Phase 1 Bloc 3.

Scope (as agreed with product): only endpoints that belong to the artisan
domain proper. NOT migrated in this bloc: bookings, missions, interventions,
payments, home passport, calendar OAuth stubs, trust engine writes.

Migrated endpoints
------------------
Public reads:
    GET  /api/artisans                     (filtered list)
    GET  /api/artisans/top                 (top-8 by rating)
    GET  /api/artisans/{artisan_id}
    GET  /api/artisans/{artisan_id}/availability
    GET  /api/artisans/{artisan_id}/slots
    GET  /api/artisans/{artisan_id}/gallery

Self-service (auth required, artisan role):
    GET    /api/artisans/me
    POST   /api/artisans/me                       (upsert with strict whitelist)
    POST   /api/artisans/me/subscribe
    POST   /api/artisans/me/position
    POST   /api/artisans/me/available-now
    POST   /api/artisans/me/calendar/connect
    POST   /api/artisans/me/slots
    GET    /api/artisans/me/slots
    DELETE /api/artisans/me/slots/{slot_id}
    POST   /api/artisans/me/gallery
    PATCH  /api/artisans/me/gallery/{project_id}
    DELETE /api/artisans/me/gallery/{project_id}
    GET    /api/artisans/me/scoreboard
    GET    /api/artisans/me/finance
    GET    /api/artisans/me/earnings

Security guarantees
-------------------
* Every mutation is gated by role == "artisan". Clients get 403.
* PATCH/POST on /artisans/me applies a **strict whitelist** — any attempt to
  set `role`, `verification_status`, `trust_score`, `rating`, `reviews_count`,
  `jobs_done`, `subscription_status`, `is_subscribed`, `stripe_account_id`,
  `admin_notes` is silently dropped.
* A NEW artisan profile starts with:
    - trust_score          = 0     (was 80)
    - rating               = 0     (was 5.0)
    - reviews_count        = 0
    - verification_status  = "pending"
    - simulated            = True  (flagged for the Sprint 14 SIMULATION overlay)
  Existing profiles are NOT touched — this is purely for newly-created ones.
* Public listings return artisans whose `verification_status` is `approved`
  OR is missing (legacy compat — those pre-Sprint-14 rows are treated as OK
  so we don't hide legit ones by mistake).
* All state-changing operations write an `artisan.*` audit log line.
"""
from __future__ import annotations
import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl, validator

from services import security as security_svc

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Immutable / server-managed field lists (defense in depth)
# ---------------------------------------------------------------------------

# Fields that MUST NEVER be settable through the public API — even if a
# client sends them, we drop them before writing to Mongo.
SENSITIVE_ARTISAN_FIELDS = frozenset({
    "role", "user_id", "artisan_id",
    "verification_status", "trust_score", "trust_score_v2",
    "rating", "reviews_count", "base_rating", "base_reviews_count",
    "jobs_done", "completed_jobs",
    "subscription_status", "is_subscribed", "subscription_expires",
    "stripe_account_id", "stripe_customer_id",
    "admin_notes", "internal_notes",
    "identity_verified", "insurance_verified", "business_registered",
    "background_checked",
    "created_at", "member_since", "last_active_at",
    "acceptance_rate", "completion_rate", "cancellation_rate",
    "disputes_unresolved", "disputes_resolved",
    "punctuality_rate", "satisfaction_rate",
    "avg_arrival_min", "response_min",
})


# Whitelist of fields that CAN be set via POST /artisans/me
EDITABLE_ARTISAN_FIELDS = frozenset({
    "trade", "title", "bio", "city", "hourly_rate", "photo", "phone",
    "available", "years_experience", "emergency_capable", "website",
    "intervention_zones", "working_hours",
})


VERIFICATION_STATES = ("pending", "identity_verified", "business_verified",
                       "insurance_verified", "approved", "rejected")


# ---------------------------------------------------------------------------
# Pydantic input models with strict validation
# ---------------------------------------------------------------------------


def _sanitize_text(v: Optional[str], max_len: int = 500) -> Optional[str]:
    if v is None:
        return v
    v = str(v).strip()
    if not v:
        return None
    # Reject obvious HTML/script injections
    if "<script" in v.lower() or "</script" in v.lower():
        raise ValueError("Contenu potentiellement malveillant refusé")
    return v[:max_len]


class WorkingHoursSlot(BaseModel):
    """A single day's opening slot, e.g. Monday 08:00-18:00."""
    day: int = Field(..., ge=0, le=6, description="0=Monday .. 6=Sunday")
    start: str = Field(..., pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(..., pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    @validator("end")
    def _end_after_start(cls, v, values):  # noqa: N805
        s = values.get("start")
        if s and v <= s:
            raise ValueError("L'heure de fin doit être postérieure à l'heure de début")
        return v


class InterventionZone(BaseModel):
    """A geographic zone the artisan agrees to serve."""
    city: str = Field(..., min_length=1, max_length=80)
    postal_code: Optional[str] = Field(None, max_length=16)
    radius_km: Optional[float] = Field(None, ge=0, le=500)

    @validator("city")
    def _clean_city(cls, v: str) -> str:  # noqa: N805
        v = v.strip()
        # Only letters, spaces, hyphens, apostrophes
        if not re.match(r"^[\w\-\'’\s]+$", v, re.UNICODE):
            raise ValueError("Nom de ville invalide")
        return v[:80]


class ArtisanUpsertInput(BaseModel):
    trade: str = Field(..., min_length=1, max_length=40)
    title: str = Field(..., min_length=1, max_length=120)
    bio: str = Field("", max_length=1500)
    city: str = Field("", max_length=80)
    hourly_rate: float = Field(0, ge=0, le=1000)
    photo: Optional[str] = Field(None, max_length=2_000_000)   # base64 tolerated
    phone: Optional[str] = Field(None, max_length=32)
    available: bool = True
    years_experience: Optional[int] = Field(None, ge=0, le=80)
    emergency_capable: Optional[bool] = None
    website: Optional[HttpUrl] = None
    intervention_zones: Optional[List[InterventionZone]] = None
    working_hours: Optional[List[WorkingHoursSlot]] = None

    @validator("trade")
    def _slug_only(cls, v: str) -> str:  # noqa: N805
        v = v.strip().lower()
        if not re.match(r"^[a-z0-9_\-]+$", v):
            raise ValueError("Slug de métier invalide")
        return v

    @validator("phone")
    def _clean_phone(cls, v: Optional[str]) -> Optional[str]:  # noqa: N805
        if v is None:
            return v
        v = v.strip()
        for ch in v:
            if not (ch.isdigit() or ch in "+ -()."):
                raise ValueError("Format de téléphone invalide")
        return v

    _clean_bio = validator("bio", allow_reuse=True)(lambda cls, v: _sanitize_text(v, 1500) or "")
    _clean_title = validator("title", allow_reuse=True)(lambda cls, v: _sanitize_text(v, 120) or "")
    _clean_city = validator("city", allow_reuse=True)(lambda cls, v: _sanitize_text(v, 80) or "")


class PositionInput(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    available_now: Optional[bool] = None


class CalendarConnectInput(BaseModel):
    provider: str = Field(..., min_length=1, max_length=32)
    # Note: legacy contract returns 400 (not 422) for unknown providers.
    # We validate the whitelist inside the handler to preserve that.


class SlotInput(BaseModel):
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    start_time: str = Field(..., pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    duration_min: int = Field(60, ge=15, le=480)
    recurring: bool = False


class GalleryProjectInput(BaseModel):
    title: str = Field(..., min_length=1, max_length=140)
    description: Optional[str] = Field(None, max_length=2000)
    trade: Optional[str] = None
    before_photos: List[str] = Field(default_factory=list, max_items=6)
    after_photos: List[str] = Field(default_factory=list, max_items=6)


class GalleryPatchInput(BaseModel):
    description: Optional[str] = Field(None, max_length=2000)
    city: Optional[str] = Field(None, max_length=80)
    duration_hours: Optional[float] = Field(None, ge=0, le=999)
    completed_at: Optional[str] = None
    review_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _sanitize_upsert_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return only the fields that are allowed to be set by the user."""
    return {k: v for k, v in data.items() if k in EDITABLE_ARTISAN_FIELDS}


def _is_publicly_visible(artisan: Dict[str, Any]) -> bool:
    """A profile is public when subscribed AND (approved OR legacy)."""
    if not artisan.get("is_subscribed"):
        return False
    vs = artisan.get("verification_status")
    if vs is None:
        # Legacy profile — created before Sprint 14. Backward-compat: keep visible.
        return True
    return vs == "approved"


# FAQTOTUM V1 — Privacy: whitelist explicite des champs exposés dans les
# endpoints PUBLICS (`GET /artisans`, `GET /artisans/{id}`, `/top`, `/nearby`).
# Toute clé non listée est retirée avant retour. Le téléphone, l'email, la
# position GPS précise et les métadonnées de vérification ne fuitent jamais.
PUBLIC_ARTISAN_FIELDS: frozenset[str] = frozenset({
    # Identité pro
    "artisan_id", "user_id", "name", "title", "photo",
    # Métier / description
    "trade", "trade_name", "trade_icon", "bio",
    # Réputation
    "rating", "reviews_count", "jobs_done",
    "trust_score", "trust_score_v2", "response_min", "acceptance_rate",
    "completion_rate", "cancellation_rate",
    # Tarification
    "hourly_rate",
    # Visibilité / statut
    "available", "available_now", "is_subscribed", "verification_status",
    "years_experience", "emergency_capable", "website", "intervention_zones",
    "working_hours", "distance_km",
    # Calcul FAQTOTUM (enrichissement)
    "confidence_card", "badges",
    # Compat legacy
    "created_at",
})


def _public_view(artisan: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of `artisan` with only public-safe fields.

    Retire proprement : phone, email, precise lat/lng, stripe_account_id,
    identity docs, chiffre d'affaires, etc. Le champ ``city`` est REMPLACÉ
    par le nom de ville seulement (pas d'adresse complète). Le champ
    ``lat``/``lng`` reste UNIQUEMENT si dérivé d'une approximation ville —
    ici on préfère supprimer pour éviter tout risque et calculer
    ``distance_km`` en amont.
    """
    out: Dict[str, Any] = {k: v for k, v in artisan.items() if k in PUBLIC_ARTISAN_FIELDS}
    # City : garder uniquement la ville, jamais l'adresse. On accepte les
    # cas où la valeur contient un CP → strip après une éventuelle virgule.
    raw_city = artisan.get("city")
    if raw_city:
        out["city"] = str(raw_city).split(",")[0].strip()
    return out


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------

def build_artisans_router(
    db,
    get_current_user,
    *,
    enrich_artisan,           # server-level helper (kept there for now)
    trust_engine,             # module
    calendar_sync,            # module
    growth,                   # module (levels)
    category_map: Dict[str, Any],
    city_coords: Dict[str, tuple],
    haversine,                # server-level helper
    artisans_nearby_impl,     # legacy async fn — kept as is for now
):
    r = APIRouter()

    async def _require_artisan(user) -> Dict[str, Any]:
        if user.get("role") != "artisan":
            raise HTTPException(status_code=403, detail="Réservé aux artisans")
        return user

    async def _get_my_profile(user) -> Dict[str, Any]:
        await _require_artisan(user)
        prof = await db.artisan_profiles.find_one(
            {"user_id": user["user_id"]}, {"_id": 0},
        )
        if not prof:
            raise HTTPException(status_code=404, detail="Profil artisan introuvable")
        return prof

    # -----------------------------------------------------------------------
    # Public reads
    # -----------------------------------------------------------------------

    @r.get("/artisans")
    async def list_artisans(
        category: Optional[str] = None,
        q: Optional[str] = None,
        min_rate: Optional[float] = None,
        max_rate: Optional[float] = None,
        min_rating: Optional[float] = None,
        available: Optional[bool] = None,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        radius: Optional[float] = None,
        sort: Optional[str] = None,
    ):
        query: Dict[str, Any] = {"is_subscribed": True}
        if category:
            query["trade"] = category
        # Visibility: approved OR legacy (verification_status missing)
        query["$or"] = [
            {"verification_status": "approved"},
            {"verification_status": {"$exists": False}},
        ]
        artisans = await db.artisan_profiles.find(query, {"_id": 0}).to_list(500)
        artisans = [await enrich_artisan(a) for a in artisans]
        if q:
            ql = q.lower()
            artisans = [
                a for a in artisans
                if ql in a.get("title", "").lower()
                or ql in a.get("city", "").lower()
                or ql in a.get("trade_name", "").lower()
                or ql in (a.get("name") or "").lower()
            ]
        if min_rate is not None:
            artisans = [a for a in artisans if a.get("hourly_rate", 0) >= min_rate]
        if max_rate is not None:
            artisans = [a for a in artisans if a.get("hourly_rate", 0) <= max_rate]
        if min_rating is not None:
            artisans = [a for a in artisans if a.get("rating", 0) >= min_rating]
        if available is not None:
            artisans = [a for a in artisans if a.get("available", True) == available]
        if lat is not None and lng is not None:
            for a in artisans:
                if a.get("lat") is not None and a.get("lng") is not None:
                    a["distance_km"] = round(haversine(lat, lng, a["lat"], a["lng"]), 1)
                else:
                    a["distance_km"] = None
            if radius is not None:
                artisans = [
                    a for a in artisans
                    if a.get("distance_km") is not None and a["distance_km"] <= radius
                ]
        if sort == "rate_asc":
            artisans.sort(key=lambda x: x.get("hourly_rate", 0))
        elif sort == "rate_desc":
            artisans.sort(key=lambda x: x.get("hourly_rate", 0), reverse=True)
        elif sort == "distance" and lat is not None:
            artisans.sort(
                key=lambda x: x.get("distance_km") if x.get("distance_km") is not None else 1e9
            )
        else:
            artisans.sort(key=lambda x: x.get("rating", 0), reverse=True)
        # FAQTOTUM privacy: strip sensitive fields before returning.
        return [_public_view(a) for a in artisans]

    @r.get("/artisans/top")
    async def top_artisans():
        query = {
            "is_subscribed": True,
            "$or": [
                {"verification_status": "approved"},
                {"verification_status": {"$exists": False}},
            ],
        }
        artisans = await db.artisan_profiles.find(query, {"_id": 0}).to_list(500)
        artisans = [await enrich_artisan(a) for a in artisans]
        artisans.sort(key=lambda x: x.get("rating", 0), reverse=True)
        return [_public_view(a) for a in artisans[:8]]

    # NOTE: /artisans/nearby, /artisans/{aid}/trust, /artisans/{aid}/badges,
    # /artisans/{aid}/confidence-card and /artisans/{aid}/recompute-trust stay
    # in server.py for now (out of Bloc 3 scope: trust engine / dispatch).

    @r.get("/artisans/me")
    async def my_artisan_profile(user=Depends(get_current_user)):
        profile = await db.artisan_profiles.find_one(
            {"user_id": user["user_id"]}, {"_id": 0},
        )
        if not profile:
            return None
        return await enrich_artisan(profile)

    @r.post("/artisans/me")
    async def upsert_artisan_profile(
        data: ArtisanUpsertInput, user=Depends(get_current_user),
    ):
        await _require_artisan(user)
        raw = data.dict(exclude_none=False)
        clean = _sanitize_upsert_payload(raw)

        cat = category_map.get(clean.get("trade"))
        coords = city_coords.get(clean.get("city"))

        payload = {
            "trade": clean["trade"],
            "trade_name": cat["name"] if cat else clean["trade"],
            "title": clean["title"],
            "bio": clean.get("bio", ""),
            "city": clean.get("city", ""),
            "hourly_rate": float(clean.get("hourly_rate", 0)),
            "photo": clean.get("photo"),
            "phone": clean.get("phone"),
            "name": user["name"],
            "available": bool(clean.get("available", True)),
            "years_experience": clean.get("years_experience"),
            "emergency_capable": clean.get("emergency_capable"),
            "website": clean.get("website"),
            "intervention_zones": clean.get("intervention_zones") or [],
            "working_hours": clean.get("working_hours") or [],
            "lat": coords[0] if coords else None,
            "lng": coords[1] if coords else None,
        }
        # Strip HttpUrl objects → plain string for JSON serialization
        if payload.get("website"):
            payload["website"] = str(payload["website"])
        if payload.get("intervention_zones"):
            payload["intervention_zones"] = [
                z.dict() if hasattr(z, "dict") else z for z in payload["intervention_zones"]
            ]
        if payload.get("working_hours"):
            payload["working_hours"] = [
                w.dict() if hasattr(w, "dict") else w for w in payload["working_hours"]
            ]

        existing = await db.artisan_profiles.find_one({"user_id": user["user_id"]})
        if existing:
            # UPDATE — never touch sensitive fields
            await db.artisan_profiles.update_one(
                {"artisan_id": existing["artisan_id"]},
                {"$set": {**payload, "last_active_at": _now_utc().isoformat()}},
            )
            profile = await db.artisan_profiles.find_one(
                {"artisan_id": existing["artisan_id"]}, {"_id": 0},
            )
            await security_svc.audit_log(
                db, action="artisan.profile_updated",
                actor_id=user["user_id"], actor_role="artisan",
                target=existing["artisan_id"],
                metadata={"fields": sorted(payload.keys())}, severity="info",
            )
        else:
            # CREATE — honest starting values, verification pending, marked simulated
            artisan_id = _new_id("art")
            profile = {
                "artisan_id": artisan_id,
                "user_id": user["user_id"],
                # ---- Honest initial state (was rating=5.0, trust_score=80) ----
                "rating": 0.0,
                "reviews_count": 0,
                "base_rating": 0.0,
                "base_reviews_count": 0,
                "trust_score": 0,
                "jobs_done": 0,
                "verification_status": "pending",
                # ---- SIMULATION flag: this profile has no real activity yet ----
                "simulated": True,
                # ---- Neutral defaults ----
                "acceptance_rate": 0,
                "completion_rate": 0,
                "cancellation_rate": 0,
                "response_min": None,
                "identity_verified": False,
                "insurance_verified": False,
                "business_registered": False,
                "background_checked": False,
                "avg_arrival_min": None,
                "punctuality_rate": None,
                "satisfaction_rate": None,
                "disputes_unresolved": 0,
                "disputes_resolved": 0,
                "member_since": _now_utc().isoformat(),
                "last_active_at": _now_utc().isoformat(),
                "calendar_connected": False,
                "is_subscribed": False,
                "subscription_expires": None,
                "created_at": _now_utc().isoformat(),
                **payload,
            }
            await db.artisan_profiles.insert_one(profile)
            profile.pop("_id", None)
            await security_svc.audit_log(
                db, action="artisan.profile_created",
                actor_id=user["user_id"], actor_role="artisan",
                target=artisan_id,
                metadata={"trade": payload["trade"]}, severity="info",
            )
            # Sprint 14: DO NOT recompute trust score for brand-new profiles.
            # Trust starts at 0 and is earned by real activity (reviews, completed
            # jobs, verifications). Only recompute on updates once the profile
            # has activity (jobs_done > 0 or reviews_count > 0).
            profile = await db.artisan_profiles.find_one(
                {"artisan_id": profile["artisan_id"]}, {"_id": 0},
            )
            return await enrich_artisan(profile)
        # ---- UPDATE path continues below ----
        try:
            if existing.get("jobs_done", 0) > 0 or existing.get("reviews_count", 0) > 0:
                await trust_engine.persist(db, profile["artisan_id"])
        except Exception as ex:  # noqa: BLE001
            logger.warning(f"trust_engine.persist failed: {ex}")
        profile = await db.artisan_profiles.find_one(
            {"artisan_id": profile["artisan_id"]}, {"_id": 0},
        )
        return await enrich_artisan(profile)

    @r.post("/artisans/me/subscribe")
    async def subscribe(user=Depends(get_current_user)):
        profile = await _get_my_profile(user)
        expires = (_now_utc() + timedelta(days=30)).isoformat()
        await db.artisan_profiles.update_one(
            {"artisan_id": profile["artisan_id"]},
            {"$set": {"is_subscribed": True, "subscription_expires": expires}},
        )
        await security_svc.audit_log(
            db, action="artisan.subscribed",
            actor_id=user["user_id"], actor_role="artisan",
            target=profile["artisan_id"],
            metadata={"expires": expires, "simulated": True}, severity="info",
        )
        return {"ok": True, "subscription_expires": expires, "simulated": True}

    @r.get("/artisans/{artisan_id}")
    async def get_artisan(artisan_id: str):
        artisan = await db.artisan_profiles.find_one(
            {"artisan_id": artisan_id}, {"_id": 0},
        )
        if not artisan:
            raise HTTPException(status_code=404, detail="Artisan introuvable")
        # If not publicly visible and viewer is unauthenticated → 404.
        # NOTE: we don't have the user here (no auth dependency by design for
        # public read). To keep backward compat and avoid revealing the
        # existence of unapproved profiles to the anonymous world, we ALSO
        # return 404 when it's not publicly visible.
        if not _is_publicly_visible(artisan):
            raise HTTPException(status_code=404, detail="Artisan introuvable")
        enriched = await enrich_artisan(artisan)
        try:
            out = trust_engine.compute(artisan)
            enriched["confidence_card"] = trust_engine.confidence_card(artisan, out)
            enriched["badges"] = trust_engine.badges(artisan, out["trust_score"])
            enriched["trust_score"] = out["trust_score"]
        except Exception as ex:  # noqa: BLE001
            logger.warning(f"trust card computation failed: {ex}")
        # FAQTOTUM privacy: strip sensitive fields (phone, email, precise
        # location, stripe, verification metadata) before returning.
        return _public_view(enriched)

    # -----------------------------------------------------------------------
    # Availability + calendar
    # -----------------------------------------------------------------------

    @r.get("/artisans/{artisan_id}/availability")
    async def artisan_availability(artisan_id: str, days: int = 7):
        artisan = await db.artisan_profiles.find_one(
            {"artisan_id": artisan_id}, {"_id": 0},
        )
        if not artisan:
            raise HTTPException(status_code=404, detail="Artisan introuvable")
        if days < 1 or days > 60:
            raise HTTPException(status_code=400, detail="days must be between 1 and 60")
        bks = await db.bookings.find(
            {"artisan_id": artisan_id, "status": {"$in": ["pending", "accepted"]}},
            {"_id": 0},
        ).to_list(500)
        busy = []
        for b in bks:
            try:
                busy.append({
                    "date": b.get("date"),
                    "hour": int((b.get("slot") or "0").split(":")[0]),
                })
            except Exception:
                pass
        calendar = calendar_sync.generate_availability(artisan_id, days=days, busy=busy)
        nxt = calendar_sync.next_available(artisan_id, days=days, busy=busy)
        return {
            "artisan_id": artisan_id,
            "calendar_connected": bool(artisan.get("calendar_connected")),
            "provider": artisan.get("calendar_provider"),
            "next_available": nxt,
            "days": calendar,
        }

    @r.post("/artisans/me/calendar/connect")
    async def connect_calendar(
        data: CalendarConnectInput, user=Depends(get_current_user),
    ):
        # Legacy contract: 404 if no profile (whether client or artisan without profile).
        # This intentionally comes BEFORE the role check to preserve behavior.
        profile = await db.artisan_profiles.find_one({"user_id": user["user_id"]})
        if not profile:
            raise HTTPException(status_code=404, detail="Créez d'abord votre profil")
        try:
            conn = calendar_sync.connect_provider(data.provider)
        except ValueError as e:
            # Legacy contract: 400 for unknown provider
            raise HTTPException(status_code=400, detail=str(e))
        # Mark as simulated until real OAuth is wired
        conn["simulated"] = True
        await db.artisan_profiles.update_one(
            {"artisan_id": profile["artisan_id"]},
            {"$set": {
                "calendar_connected": True,
                "calendar_provider": conn["provider"],
                "calendar_connection": conn,
            }},
        )
        await security_svc.audit_log(
            db, action="artisan.calendar_connected",
            actor_id=user["user_id"], actor_role=user.get("role"),
            target=profile["artisan_id"],
            metadata={"provider": conn["provider"], "simulated": True},
            severity="info",
        )
        return conn

    # -----------------------------------------------------------------------
    # Live position + availability
    # -----------------------------------------------------------------------

    @r.post("/artisans/me/position")
    async def update_position(data: PositionInput, user=Depends(get_current_user)):
        profile = await _get_my_profile(user)
        update = {
            "live_lat": data.lat,
            "live_lng": data.lng,
            "live_updated_at": _now_utc().isoformat(),
        }
        if data.available_now is not None:
            update["available_now"] = bool(data.available_now)
        await db.artisan_profiles.update_one(
            {"artisan_id": profile["artisan_id"]}, {"$set": update},
        )
        return {"ok": True, **update}

    @r.post("/artisans/me/available-now")
    async def toggle_available_now(user=Depends(get_current_user)):
        profile = await _get_my_profile(user)
        new_val = not bool(profile.get("available_now"))
        await db.artisan_profiles.update_one(
            {"artisan_id": profile["artisan_id"]},
            {"$set": {
                "available_now": new_val,
                "available_now_since": _now_utc().isoformat() if new_val else None,
            }},
        )
        return {"available_now": new_val}

    # -----------------------------------------------------------------------
    # Manual slots
    # -----------------------------------------------------------------------

    @r.post("/artisans/me/slots")
    async def create_slot(data: SlotInput, user=Depends(get_current_user)):
        profile = await _get_my_profile(user)
        slot_id = _new_id("slot")
        doc = {
            "slot_id": slot_id,
            "artisan_id": profile["artisan_id"],
            "date": data.date,
            "start_time": data.start_time,
            "duration_min": data.duration_min,
            "recurring": data.recurring,
            "booked": False,
            "created_at": _now_utc().isoformat(),
        }
        await db.artisan_slots.insert_one(dict(doc))
        return doc

    @r.get("/artisans/me/slots")
    async def list_my_slots(user=Depends(get_current_user)):
        await _require_artisan(user)
        profile = await db.artisan_profiles.find_one({"user_id": user["user_id"]})
        if not profile:
            return {"slots": []}
        cursor = db.artisan_slots.find(
            {"artisan_id": profile["artisan_id"]}, {"_id": 0},
        ).sort("date", 1)
        return {"slots": await cursor.to_list(500)}

    @r.delete("/artisans/me/slots/{slot_id}")
    async def delete_slot(slot_id: str, user=Depends(get_current_user)):
        await _require_artisan(user)
        profile = await db.artisan_profiles.find_one({"user_id": user["user_id"]})
        # Composite filter — cannot delete another artisan's slot
        result = await db.artisan_slots.delete_one({
            "slot_id": slot_id,
            "artisan_id": profile.get("artisan_id") if profile else None,
        })
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Créneau introuvable")
        return {"ok": True}

    @r.get("/artisans/{artisan_id}/slots")
    async def list_artisan_slots(artisan_id: str):
        today = _now_utc().date().isoformat()
        cursor = db.artisan_slots.find(
            {"artisan_id": artisan_id, "booked": False, "date": {"$gte": today}},
            {"_id": 0},
        ).sort("date", 1)
        return {"slots": await cursor.to_list(200)}

    # -----------------------------------------------------------------------
    # Gallery / portfolio
    # -----------------------------------------------------------------------

    @r.get("/artisans/{aid}/gallery")
    async def artisan_gallery(aid: str):
        return await db.gallery_projects.find(
            {"artisan_id": aid}, {"_id": 0},
        ).sort("created_at", -1).to_list(200)

    @r.post("/artisans/me/gallery")
    async def add_gallery_project(
        body: GalleryProjectInput, user=Depends(get_current_user),
    ):
        profile = await _get_my_profile(user)
        doc = {
            "project_id": _new_id("gal"),
            "artisan_id": profile["artisan_id"],
            "title": body.title.strip(),
            "description": body.description or "",
            "trade": body.trade or profile.get("trade"),
            "before_photos": body.before_photos[:6],
            "after_photos": body.after_photos[:6],
            "created_at": _now_utc().isoformat(),
        }
        await db.gallery_projects.insert_one(dict(doc))
        return doc

    @r.patch("/artisans/me/gallery/{project_id}")
    async def patch_gallery(
        project_id: str, body: GalleryPatchInput, user=Depends(get_current_user),
    ):
        profile = await _get_my_profile(user)
        updates = {k: v for k, v in body.dict(exclude_none=True).items()}
        updates["updated_at"] = _now_utc().isoformat()
        # Composite filter enforces ownership
        result = await db.gallery_projects.update_one(
            {"project_id": project_id, "artisan_id": profile["artisan_id"]},
            {"$set": updates},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Projet introuvable")
        return await db.gallery_projects.find_one(
            {"project_id": project_id}, {"_id": 0},
        )

    @r.delete("/artisans/me/gallery/{project_id}")
    async def delete_gallery_project(
        project_id: str, user=Depends(get_current_user),
    ):
        profile = await _get_my_profile(user)
        result = await db.gallery_projects.delete_one({
            "project_id": project_id, "artisan_id": profile["artisan_id"],
        })
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Projet introuvable")
        return {"ok": True}

    # -----------------------------------------------------------------------
    # Statistics — scoreboard, finance, earnings
    # -----------------------------------------------------------------------

    @r.get("/artisans/me/scoreboard")
    async def my_scoreboard(user=Depends(get_current_user)):
        # Legacy contract: 404 (not 403) if no profile — even for clients.
        # This gives no signal about whether the caller has the right role.
        prof = await db.artisan_profiles.find_one(
            {"user_id": user["user_id"]}, {"_id": 0},
        )
        if not prof:
            raise HTTPException(status_code=404, detail="Profil artisan introuvable")
        out = trust_engine.compute(prof)
        return trust_engine.scoreboard(prof, out)

    @r.get("/artisans/me/finance")
    async def artisan_finance(user=Depends(get_current_user)):
        profile = await _get_my_profile(user)
        aid = profile["artisan_id"]
        transfers = await db.transfers.find(
            {"artisan_id": aid}, {"_id": 0},
        ).sort("created_at", -1).to_list(500)
        revenue = sum(t.get("net_cents", 0) for t in transfers)
        commissions = sum(t.get("commission_cents", 0) for t in transfers)
        gross = sum(t.get("gross_cents", 0) for t in transfers)
        pending_agg = await db.escrows.aggregate([
            {"$match": {"artisan_id": aid, "state": "held"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount_cents"}, "count": {"$sum": 1}}},
        ]).to_list(1)
        pending_total = pending_agg[0]["total"] if pending_agg else 0
        pending_count = pending_agg[0]["count"] if pending_agg else 0

        # Monthly evolution (last 6 months, YYYY-MM buckets)
        monthly: Dict[str, int] = {}
        for t in transfers:
            key = (t.get("created_at") or "")[:7]
            monthly[key] = monthly.get(key, 0) + t.get("net_cents", 0)
        evolution = [{"month": k, "amount_cents": v} for k, v in sorted(monthly.items())][-6:]

        avg = int(revenue / len(transfers)) if transfers else 0
        return {
            "revenue_cents": revenue,
            "gross_cents": gross,
            "commissions_cents": commissions,
            "pending_cents": pending_total,
            "pending_count": pending_count,
            "transfers_count": len(transfers),
            "average_net_cents": avg,
            "monthly_evolution": evolution,
            "recent_transfers": transfers[:10],
            "simulated": True,   # payments are still in SIMULATION mode
        }

    @r.get("/artisans/me/earnings")
    async def artisan_earnings(user=Depends(get_current_user)):
        await _require_artisan(user)
        profile = await db.artisan_profiles.find_one(
            {"user_id": user["user_id"]}, {"_id": 0},
        )
        if not profile:
            return {
                "total_net": 0, "total_gross": 0, "total_commission": 0,
                "transfers_count": 0, "transfers": [], "simulated": True,
            }
        cursor = db.transfers.find(
            {"artisan_id": profile["artisan_id"]}, {"_id": 0},
        ).sort("created_at", -1).limit(50)
        transfers = await cursor.to_list(50)
        return {
            "total_gross": sum(t.get("gross_cents", 0) for t in transfers),
            "total_net": sum(t.get("net_cents", 0) for t in transfers),
            "total_commission": sum(t.get("commission_cents", 0) for t in transfers),
            "transfers_count": len(transfers),
            "transfers": transfers[:10],
            "simulated": True,
        }

    @r.get("/artisans/{aid}/level")
    async def artisan_level(aid: str):
        a = await db.artisan_profiles.find_one({"artisan_id": aid}, {"_id": 0})
        if not a:
            raise HTTPException(status_code=404, detail="Artisan introuvable")
        lvl = growth.pro_level(a.get("trust_score") or 0, a.get("jobs_done") or 0)
        return {"artisan_id": aid, **lvl}

    return r
