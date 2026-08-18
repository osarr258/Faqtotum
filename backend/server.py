from fastapi import FastAPI, APIRouter, HTTPException, Header, Depends, Request
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import bcrypt
import httpx
import base64
import json
import tempfile
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
from emergentintegrations.llm.openai.speech_to_text import OpenAISpeechToText
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from services import matching, calendar_sync, trust_engine, payments, concierge, growth, security, paypal as paypal_svc, homes as homes_svc

# Sprint 14 Phase 1 — Strangler Pattern: import new modular routers.
# The new routers are mounted BEFORE the legacy inline endpoints so that
# FastAPI's first-match wins. Legacy blocks stay in place, commented as
# `# LEGACY (P1 migrated)`, and will be deleted once tests re-confirm parity.
from security.dependencies import get_db_dependency
from routes.auth import build_auth_router
from routes.security import build_security_router
from routes.users import build_users_router
from routes.artisans import build_artisans_router
from routes.bookings import build_bookings_router
from routes.missions import build_missions_router
from routes.interventions import build_interventions_router

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")


def _parse_allowed_origins() -> list[str]:
    """
    CORS allow-list — read from env `ALLOWED_ORIGINS` (comma-separated).

    Rules:
    - In development / preview: sensible defaults (localhost + Expo preview host).
    - In production: MUST be explicitly set via env var. If unset and the
      process runs with `APP_ENV=production`, we fail-closed (empty list),
      which blocks cross-origin requests until the operator configures it.
    - `ALLOWED_ORIGIN_REGEX` env var can additionally allow a regex pattern
      (useful for the ephemeral emergent preview subdomains).
    """
    raw = os.environ.get("ALLOWED_ORIGINS", "").strip()
    app_env = os.environ.get("APP_ENV", "development").lower()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    if app_env == "production":
        # Fail-closed in prod: no wildcard, no defaults.
        return []
    # Dev / preview defaults.
    return [
        "http://localhost:3000",
        "http://localhost:19006",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:19006",
    ]

# --- Sprint 14 Phase 1 — Shared auth dependencies (Strangler Pattern) ---------
# Single source of truth for `get_current_user` / `require_roles`.
# Legacy definitions below (search: `LEGACY (P1 migrated)`) are kept temporarily
# so unmigrated endpoints keep working. They will be deleted at end of Phase 1.
_get_current_user, _require_roles = get_db_dependency(db)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EMERGENT_SESSION_API = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

# ----------------------------- Helpers -----------------------------

def now_utc():
    return datetime.now(timezone.utc)

def new_id(prefix: str):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False

async def create_session(user_id: str, request: Optional[Request] = None) -> str:
    result = await security.create_secure_session(db, user_id, request=request, days=7)
    return result["token"]

async def get_current_user(authorization: Optional[str] = Header(None), request: Request = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Non authentifié")
    token = authorization.split(" ", 1)[1]
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Session invalide")
    if session.get("revoked"):
        raise HTTPException(status_code=401, detail="Session révoquée")
    expires = session["expires_at"]
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now_utc():
        raise HTTPException(status_code=401, detail="Session expirée")
    user = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0, "password": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")
    if user.get("deleted") or user.get("anonymized"):
        raise HTTPException(status_code=401, detail="Compte supprimé")
    # Touch session (fire and forget style)
    try:
        await security.touch_session(db, token)
    except Exception:
        pass
    # Expose current token for later use (revoke-others endpoint)
    user["_current_token"] = token
    return user


def require_roles(*allowed_roles: str):
    """FastAPI dependency factory for RBAC."""
    async def _dep(user=Depends(get_current_user)):
        if user.get("role") == "super_admin":
            return user
        if user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Accès refusé — rôle requis: {', '.join(allowed_roles)}",
            )
        return user
    return _dep

# ----------------------------- Models -----------------------------

class RegisterInput(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "client"

class LoginInput(BaseModel):
    email: EmailStr
    password: str

class GoogleInput(BaseModel):
    session_token: str
    role: str = "client"

class ArtisanProfileInput(BaseModel):
    trade: str
    title: str
    bio: str = ""
    city: str = ""
    hourly_rate: float = 0
    photo: Optional[str] = None
    phone: Optional[str] = None
    available: bool = True

class BookingInput(BaseModel):
    artisan_id: str
    date: str
    slot: str
    description: str = ""

class BookingStatusInput(BaseModel):
    status: str

class ReviewInput(BaseModel):
    booking_id: str
    rating: int
    comment: str = ""

class MessageInput(BaseModel):
    text: str

class DiagnoseInput(BaseModel):
    text: str = ""
    images: List[str] = []
    lat: Optional[float] = None
    lng: Optional[float] = None

class TranscribeInput(BaseModel):
    audio_base64: str
    ext: str = "m4a"

class MissionInput(BaseModel):
    trade: str
    urgency: str = "moyenne"
    diagnosis: dict = {}
    lat: Optional[float] = None
    lng: Optional[float] = None
    price_min: float = 0
    price_max: float = 0

class BookInput(BaseModel):
    artisan_id: str

class ProAcceptInput(BaseModel):
    artisan_id: str

class CalendarConnectInput(BaseModel):
    provider: str

class EquipmentInput(BaseModel):
    name: str
    category: Optional[str] = "other"  # water_heater, boiler, heat_pump, panel, ac, vmc, roof, windows, doors, smoke_detector, solar, ev_charger, water_softener, other
    brand: Optional[str] = ""
    model: Optional[str] = ""
    serial_number: Optional[str] = ""
    installed_on: Optional[str] = None  # ISO date
    installer: Optional[str] = ""
    warranty_until: Optional[str] = None
    photos: List[str] = Field(default_factory=list)
    documents: List[str] = Field(default_factory=list)  # document ids
    status: str = "ok"
    notes: Optional[str] = ""

# ----------------------------- Categories -----------------------------

CATEGORIES = [
    {"slug": "plombier", "name": "Plombier", "icon": "water"},
    {"slug": "electricien", "name": "Électricien", "icon": "flash"},
    {"slug": "chauffagiste", "name": "Chauffagiste", "icon": "flame"},
    {"slug": "climaticien", "name": "Climaticien", "icon": "snow"},
    {"slug": "peintre", "name": "Peintre", "icon": "color-palette"},
    {"slug": "serrurier", "name": "Serrurier", "icon": "key"},
    {"slug": "menuisier", "name": "Menuisier", "icon": "hammer"},
    {"slug": "macon", "name": "Maçon", "icon": "cube"},
    {"slug": "carreleur", "name": "Carreleur", "icon": "grid"},
    {"slug": "jardinier", "name": "Jardinier", "icon": "leaf"},
    {"slug": "vitrier", "name": "Vitrier", "icon": "browsers"},
    {"slug": "couvreur", "name": "Couvreur", "icon": "home"},
]
CATEGORY_MAP = {c["slug"]: c for c in CATEGORIES}

import math

CITY_COORDS = {
    "Paris 11e": (48.8594, 2.3765),
    "Paris 15e": (48.8417, 2.3003),
    "Lyon 3e": (45.7597, 4.8554),
    "Lyon 7e": (45.7333, 4.8425),
    "Bordeaux": (44.8378, -0.5792),
    "Marseille": (43.2965, 5.3698),
    "Lille": (50.6292, 3.0573),
    "Nice": (43.7102, 7.2620),
    "Nantes": (47.2184, -1.5536),
    "Toulouse": (43.6047, 1.4442),
    "Rennes": (48.1173, -1.6778),
    "Strasbourg": (48.5734, 7.7521),
}

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ----------------------------- Categories route -----------------------------

@api_router.get("/categories")
async def get_categories():
    return CATEGORIES


# --- Shared helper still used by many legacy endpoints (bookings, missions,
# --- disputes, matching). Kept alive until those blocs are migrated too.
async def enrich_artisan(a: dict):
    a.pop("_id", None)
    cat = CATEGORY_MAP.get(a.get("trade"))
    a["trade_name"] = cat["name"] if cat else a.get("trade")
    a["trade_icon"] = cat["icon"] if cat else "construct"
    return a


# Literal route defined BEFORE the parameterized /artisans/{artisan_id}
@api_router.get("/artisans/nearby")
async def artisans_nearby_early(
    lat: float,
    lng: float,
    radius: float = 10.0,
    category: Optional[str] = None,
    only_available_now: bool = False,
    limit: int = 30,
):
    return await _artisans_nearby_impl(lat, lng, radius, category, only_available_now, limit)



# ----------------------------- Reviews -----------------------------

async def recompute_artisan_rating(artisan_id: str):
    profile = await db.artisan_profiles.find_one({"artisan_id": artisan_id}, {"_id": 0})
    if not profile:
        return
    revs = await db.reviews.find({"artisan_id": artisan_id, "to_role": "artisan"}, {"_id": 0}).to_list(2000)
    base_rating = profile.get("base_rating", 0) or 0
    base_count = profile.get("base_reviews_count", 0) or 0
    total = base_count + len(revs)
    if total == 0:
        rating = 5.0
    else:
        rating = (base_rating * base_count + sum(r["rating"] for r in revs)) / total
    await db.artisan_profiles.update_one(
        {"artisan_id": artisan_id},
        {"$set": {"rating": round(rating, 2), "reviews_count": total}},
    )

# ----------------------------- Messaging -----------------------------

def conv_view(c: dict, user_id: str):
    c.pop("_id", None)
    is_client = c.get("client_id") == user_id
    c["other_name"] = c.get("artisan_name") if is_client else c.get("client_name")
    return c

# ----------------------------- AI: Diagnosis & Voice -----------------------------

# ============================================================
# AI CONCIERGE — Multi-turn conversational diagnosis
# ============================================================

class ConciergeMessageInput(BaseModel):
    text: Optional[str] = ""
    photos_base64: Optional[List[str]] = None
    voice_ext: Optional[str] = None
    voice_base64: Optional[str] = None

class ConciergeStartInput(BaseModel):
    property_id: Optional[str] = None

class ConciergeVideoInput(BaseModel):
    filename: Optional[str] = "video.mp4"
    size_bytes: Optional[int] = 0

async def _load_conv(sid: str, user_id: str) -> dict:
    s = await db.concierge_sessions.find_one({"session_id": sid, "user_id": user_id}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session introuvable")
    return s

# ----------------------------- Matching & Missions -----------------------------

URGENCY_LABELS = {"faible": "Faible", "moyenne": "Modérée", "elevee": "Élevée", "urgence": "Urgence"}


def _match_ctx(artisans: list, urgency: str, lat, lng) -> dict:
    rates = [a.get("hourly_rate") for a in artisans if a.get("hourly_rate")]
    return {
        "lat": lat, "lng": lng,
        "urgency": urgency,
        "rate_min": min(rates) if rates else 30.0,
        "rate_max": max(rates) if rates else 70.0,
    }


def match_eta(c: dict):
    d = c.get("distance_km")
    return max(3, min(40, round((d if d is not None else 5) / 35 * 60)))


def mission_artisan_card(a: dict):
    """Build a customer-facing pro card from an artisan enriched & scored by
    the matching engine. Includes the AI explanation (FR) but NEVER the raw
    score weights — only a friendly confidence label."""
    card = {
        "artisan_id": a["artisan_id"],
        "name": a.get("name") or a.get("title"),
        "title": a.get("title"),
        "photo": a.get("photo"),
        "trade_name": a.get("trade_name"),
        "rating": a.get("rating", 5.0),
        "reviews_count": a.get("reviews_count", 0),
        "trust_score": a.get("trust_score", 90),
        "acceptance_rate": a.get("acceptance_rate", 90),
        "response_min": a.get("response_min", 15),
        "distance_km": a.get("distance_km"),
        "city": a.get("city"),
        "phone": a.get("phone"),
        "lat": a.get("lat"),
        "lng": a.get("lng"),
    }
    card["eta_minutes"] = match_eta(card)
    ms = a.get("match_score")
    if ms is not None:
        card["match_score"] = ms
        card["match_label"] = matching.confidence_label(ms)
    card["match_reasons"] = matching.explain(a, card["eta_minutes"])
    return card


# ---------------------------------------------------------------------------
# Helpers restored after Bloc 4 sed cleanup — still referenced by non-migrated
# code (deposit endpoints, mission complete, /reviews, home-passport).
# ---------------------------------------------------------------------------

DEPOSIT_MIN_CENTS = 3000        # 30€
DEPOSIT_MAX_CENTS = 30000       # 300€
DEPOSIT_PERCENT = 30            # 30%


def _compute_deposit_cents(avg_cents: int) -> int:
    """Deposit = 30% of the average estimated price, clamped 30€..300€."""
    if not avg_cents or avg_cents <= 0:
        return DEPOSIT_MIN_CENTS
    d = int(round(avg_cents * DEPOSIT_PERCENT / 100.0))
    return max(DEPOSIT_MIN_CENTS, min(DEPOSIT_MAX_CENTS, d))


class DepositIntentInput(BaseModel):
    """Kept in server.py — deposit endpoints are OUT OF Bloc 4 scope."""
    payment_method: str = "card"
    save_card: bool = False


class DepositConfirmInput(BaseModel):
    payment_intent_id: str


async def annotate_reviewed(rows: list, user_id: str) -> list:
    """Attach `reviewed=True` on each row where the caller already left a review."""
    if not rows:
        return rows
    booking_ids = [r["booking_id"] for r in rows if r.get("booking_id")]
    reviews = await db.reviews.find(
        {"booking_id": {"$in": booking_ids}, "from_user_id": user_id},
        {"_id": 0, "booking_id": 1},
    ).to_list(len(booking_ids) or 1)
    reviewed = {r["booking_id"] for r in reviews}
    for row in rows:
        row["reviewed"] = row.get("booking_id") in reviewed
    return rows


async def _append_passport_history(user_id: str, entry: dict) -> None:
    await db.home_passports.update_one(
        {"client_id": user_id},
        {"$push": {"maintenance_history": entry}},
        upsert=True,
    )


async def _set_candidate(mission: dict, index: int) -> dict:
    """Advance the mission to the artisan at position `index` in the candidates list."""
    if index >= len(mission["candidates"]):
        return None
    aid = mission["candidates"][index]
    a = await db.artisan_profiles.find_one({"artisan_id": aid}, {"_id": 0})
    a = await enrich_artisan(a) if a else None
    if not a:
        return None
    card = mission_artisan_card(a)
    await db.missions.update_one(
        {"mission_id": mission["mission_id"]},
        {"$set": {"candidate_index": index, "artisan": card, "status": "proposed"}},
    )
    return card


@api_router.post("/missions/{mission_id}/complete")
async def complete_mission(mission_id: str, user=Depends(get_current_user)):
    m = await db.missions.find_one({"mission_id": mission_id}, {"_id": 0})
    if not m or m["client_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="Mission introuvable")
    await db.missions.update_one({"mission_id": mission_id}, {"$set": {"status": "completed", "completed_at": now_utc().isoformat()}})
    artisan = m.get("artisan", {}) or {}
    pmin = m.get("price_min") or 0
    pmax = m.get("price_max") or 0
    amount = round((pmin + pmax) / 2) if (pmin or pmax) else None
    # --- Future-ready records: invoice + guarantee + home passport history ---
    invoice = {
        "invoice_id": new_id("inv"),
        "client_id": user["user_id"],
        "mission_id": mission_id,
        "artisan_id": artisan.get("artisan_id"),
        "artisan_name": artisan.get("name"),
        "trade_name": m.get("trade_name"),
        "amount": amount,
        "currency": "EUR",
        "status": "issued",
        "issued_at": now_utc().isoformat(),
    }
    await db.invoices.insert_one(invoice)
    guarantee = {
        "guarantee_id": new_id("grt"),
        "client_id": user["user_id"],
        "mission_id": mission_id,
        "artisan_id": artisan.get("artisan_id"),
        "artisan_name": artisan.get("name"),
        "trade_name": m.get("trade_name"),
        "label": "Garantie satisfaction 12 mois",
        "starts_at": now_utc().isoformat(),
        "expires_at": (now_utc() + timedelta(days=365)).isoformat(),
        "status": "active",
    }
    await db.guarantees.insert_one(guarantee)
    await _append_passport_history(user["user_id"], {
        "type": "intervention",
        "mission_id": mission_id,
        "trade_name": m.get("trade_name"),
        "artisan_name": artisan.get("name"),
        "summary": (m.get("diagnosis") or {}).get("problem", m.get("trade_name")),
        "amount": amount,
        "invoice_id": invoice["invoice_id"],
        "guarantee_id": guarantee["guarantee_id"],
        "date": now_utc().isoformat(),
    })
    invoice.pop("_id", None)
    return {"status": "completed", "invoice_id": invoice["invoice_id"], "guarantee_id": guarantee["guarantee_id"]}


# ----------------------------- Seed -----------------------------

SEED_ARTISANS = [
    {"trade": "plombier", "name": "Lucas Moreau", "title": "Plombier chauffagiste certifié", "city": "Paris 11e", "hourly_rate": 55, "rating": 4.9, "reviews_count": 128, "bio": "15 ans d'expérience. Dépannage rapide, installation et rénovation de salle de bain.", "photo": "https://images.pexels.com/photos/8005397/pexels-photo-8005397.jpeg"},
    {"trade": "electricien", "name": "Sofiane Benali", "title": "Électricien général & domotique", "city": "Lyon 3e", "hourly_rate": 50, "rating": 4.8, "reviews_count": 94, "bio": "Mise aux normes, tableaux électriques, installation domotique connectée.", "photo": "https://images.pexels.com/photos/8961065/pexels-photo-8961065.jpeg"},
    {"trade": "peintre", "name": "Marie Dubois", "title": "Peintre en bâtiment & décoration", "city": "Bordeaux", "hourly_rate": 42, "rating": 4.9, "reviews_count": 156, "bio": "Finitions soignées, peinture décorative, conseils couleurs personnalisés.", "photo": "https://images.pexels.com/photos/7218525/pexels-photo-7218525.jpeg"},
    {"trade": "serrurier", "name": "Karim Haddad", "title": "Serrurier dépannage 24/7", "city": "Marseille", "hourly_rate": 60, "rating": 4.7, "reviews_count": 73, "bio": "Ouverture de porte, blindage, changement de serrure toutes marques.", "photo": "https://images.pexels.com/photos/8005368/pexels-photo-8005368.jpeg"},
    {"trade": "chauffagiste", "name": "Antoine Leroy", "title": "Chauffagiste — chaudières & PAC", "city": "Lille", "hourly_rate": 58, "rating": 4.8, "reviews_count": 61, "bio": "Entretien chaudière, installation pompe à chaleur, dépannage urgent.", "photo": "https://images.pexels.com/photos/8961251/pexels-photo-8961251.jpeg"},
    {"trade": "climaticien", "name": "Julien Faure", "title": "Installateur climatisation", "city": "Nice", "hourly_rate": 54, "rating": 4.6, "reviews_count": 48, "bio": "Pose et entretien de climatisation réversible, devis gratuit.", "photo": "https://images.pexels.com/photos/5691660/pexels-photo-5691660.jpeg"},
    {"trade": "menuisier", "name": "Paul Girard", "title": "Menuisier ébéniste sur mesure", "city": "Nantes", "hourly_rate": 52, "rating": 4.9, "reviews_count": 87, "bio": "Meubles sur mesure, pose de parquet, agencement intérieur bois.", "photo": "https://images.pexels.com/photos/5089178/pexels-photo-5089178.jpeg"},
    {"trade": "carreleur", "name": "Thomas Petit", "title": "Carreleur — sols & murs", "city": "Toulouse", "hourly_rate": 45, "rating": 4.7, "reviews_count": 52, "bio": "Pose de carrelage, faïence, mosaïque. Travail propre et rapide.", "photo": "https://images.pexels.com/photos/8092430/pexels-photo-8092430.jpeg"},
    {"trade": "jardinier", "name": "Nicolas Roux", "title": "Paysagiste & entretien jardin", "city": "Rennes", "hourly_rate": 38, "rating": 4.8, "reviews_count": 64, "bio": "Création d'espaces verts, taille, tonte et entretien régulier.", "photo": "https://images.pexels.com/photos/589/garden-grass-meadow-green.jpg"},
    {"trade": "macon", "name": "David Fontaine", "title": "Maçon gros œuvre", "city": "Strasbourg", "hourly_rate": 48, "rating": 4.6, "reviews_count": 39, "bio": "Construction, extension, dalles béton et murs porteurs.", "photo": "https://images.pexels.com/photos/1216589/pexels-photo-1216589.jpeg"},
    {"trade": "plombier", "name": "Émilie Garnier", "title": "Plombière dépannage express", "city": "Paris 15e", "hourly_rate": 52, "rating": 4.9, "reviews_count": 102, "bio": "Fuites, débouchage, remplacement de chauffe-eau en urgence.", "photo": "https://images.pexels.com/photos/9462191/pexels-photo-9462191.jpeg"},
    {"trade": "electricien", "name": "Hugo Mercier", "title": "Électricien certifié IRVE", "city": "Lyon 7e", "hourly_rate": 56, "rating": 4.7, "reviews_count": 58, "bio": "Bornes de recharge véhicule, rénovation électrique complète.", "photo": "https://images.pexels.com/photos/5691659/pexels-photo-5691659.jpeg"},
]

@app.on_event("startup")
async def seed_data():
    try:
        await db.users.create_index("email", unique=True)
        await db.users.create_index("user_id", unique=True)
        await db.user_sessions.create_index("session_token", unique=True)
        await db.artisan_profiles.create_index("artisan_id", unique=True)
    except Exception as e:
        logger.warning(f"Index creation: {e}")

    count = await db.artisan_profiles.count_documents({"seed": True})
    if count == 0:
        for i, s in enumerate(SEED_ARTISANS):
            cat = CATEGORY_MAP.get(s["trade"])
            coords = CITY_COORDS.get(s["city"])
            doc = {
                "artisan_id": new_id("art"),
                "user_id": None,
                "seed": True,
                "is_subscribed": True,
                "available": True,
                "lat": coords[0] if coords else None,
                "lng": coords[1] if coords else None,
                "base_rating": s["rating"],
                "base_reviews_count": s["reviews_count"],
                "trust_score": min(99, round(s["rating"] * 19 + 4)),
                "acceptance_rate": 88 + (i % 6) * 2,           # 88..98
                "completion_rate": 95 + (i % 5),               # 95..99
                "cancellation_rate": (i % 4),                  # 0..3 %
                "response_min": 8 + (i % 5) * 4,               # 8..24 min
                # Trust Engine — extended, deterministic signals.
                "identity_verified": True,
                "insurance_verified": True,
                "business_registered": True,
                "background_checked": (i % 3 != 0),
                "years_experience": 3 + (i % 8),               # 3..10
                "avg_arrival_min": 20 + (i % 6) * 5,           # 20..45
                "punctuality_rate": 92 + (i % 8),              # 92..99
                "satisfaction_rate": 88 + (i % 12),            # 88..99
                "emergency_capable": (i % 2 == 0),
                "disputes_unresolved": 0,
                "disputes_resolved": (i % 5 == 0),             # ~20% pros have 1 resolved dispute
                "member_since": (now_utc() - timedelta(days=180 + (i * 47) % 900)).isoformat(),
                "last_active_at": now_utc().isoformat(),
                "calendar_connected": False,
                "jobs_done": s["reviews_count"],
                "subscription_expires": (now_utc() + timedelta(days=365)).isoformat(),
                "trade_name": cat["name"] if cat else s["trade"],
                "phone": "+33 6 12 34 56 78",
                "created_at": now_utc().isoformat(),
                **s,
            }
            await db.artisan_profiles.insert_one(doc)
        logger.info("Seeded artisans")

    # Backfill extended stats on pre-existing seeds (idempotent migration).
    missing = await db.artisan_profiles.find({"seed": True, "cancellation_rate": {"$exists": False}}, {"_id": 0, "artisan_id": 1}).to_list(500)
    for i, a in enumerate(missing):
        await db.artisan_profiles.update_one(
            {"artisan_id": a["artisan_id"]},
            {"$set": {
                "cancellation_rate": (i % 4),
                "acceptance_rate": 88 + (i % 6) * 2,
                "response_min": 8 + (i % 5) * 4,
                "calendar_connected": False,
            }},
        )
    if missing:
        logger.info(f"Backfilled stats on {len(missing)} seeds")

    # Trust Engine — backfill new signals on artisans that predate the engine.
    trust_missing = await db.artisan_profiles.find(
        {"identity_verified": {"$exists": False}}, {"_id": 0, "artisan_id": 1}
    ).to_list(500)
    for i, a in enumerate(trust_missing):
        await db.artisan_profiles.update_one(
            {"artisan_id": a["artisan_id"]},
            {"$set": {
                "identity_verified": True,
                "insurance_verified": True,
                "business_registered": True,
                "background_checked": (i % 3 != 0),
                "years_experience": 3 + (i % 8),
                "avg_arrival_min": 20 + (i % 6) * 5,
                "punctuality_rate": 92 + (i % 8),
                "satisfaction_rate": 88 + (i % 12),
                "emergency_capable": (i % 2 == 0),
                "disputes_unresolved": 0,
                "disputes_resolved": 1 if (i % 5 == 0) else 0,
                "member_since": (now_utc() - timedelta(days=180 + (i * 47) % 900)).isoformat(),
                "last_active_at": now_utc().isoformat(),
            }},
        )
    if trust_missing:
        logger.info(f"Backfilled trust signals on {len(trust_missing)} artisans")

    # Trust Engine — recompute all artisans on startup (idempotent, cheap).
    all_ids = await db.artisan_profiles.find({}, {"_id": 0, "artisan_id": 1}).to_list(500)
    for row in all_ids:
        try:
            await trust_engine.persist(db, row["artisan_id"])
        except Exception as e:
            logger.warning(f"trust recompute {row['artisan_id']}: {e}")
    if all_ids:
        logger.info(f"Recomputed trust scores for {len(all_ids)} artisans")

# ============================================================
# DISPUTES — trust engine helper endpoints
# ============================================================

class DisputeInput(BaseModel):
    artisan_id: str
    booking_id: Optional[str] = None
    reason: str
    severity: str = "minor"  # minor | moderate | severe
    description: Optional[str] = ""

async def _load_artisan(artisan_id: str) -> dict:
    a = await db.artisan_profiles.find_one({"artisan_id": artisan_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Artisan introuvable")
    return a

@api_router.post("/disputes")
async def create_dispute(body: DisputeInput, user=Depends(get_current_user)):
    if body.severity not in trust_engine.DISPUTE_SEVERITY:
        raise HTTPException(status_code=400, detail="Sévérité invalide")
    a = await _load_artisan(body.artisan_id)
    penalty = trust_engine.dispute_penalty(body.severity)
    dispute = {
        "dispute_id": new_id("disp"),
        "artisan_id": body.artisan_id,
        "booking_id": body.booking_id,
        "opened_by": user["user_id"],
        "reason": body.reason,
        "description": body.description or "",
        "severity": body.severity,
        "status": "open" if penalty.get("requires_manual_review") else "auto_penalized",
        "requires_manual_review": bool(penalty.get("requires_manual_review")),
        "score_delta": penalty["score_delta"],
        "created_at": now_utc().isoformat(),
    }
    await db.disputes.insert_one(dict(dispute))
    # Bump counters. Severe disputes NEVER auto-ban; require manual review.
    inc = {
        "disputes_unresolved": penalty["unresolved_bump"],
        "disputes_resolved": penalty["resolved_bump"],
    }
    inc = {k: v for k, v in inc.items() if v > 0}
    if inc:
        await db.artisan_profiles.update_one(
            {"artisan_id": body.artisan_id},
            {"$inc": inc},
        )
    trust_out = await trust_engine.persist(db, body.artisan_id)
    return {"dispute": dispute, "new_trust_score": trust_out["trust_score"] if trust_out else a.get("trust_score")}

@api_router.get("/disputes/mine")
async def my_disputes(user=Depends(get_current_user)):
    """A pro sees the disputes filed against them; a client sees the ones they opened."""
    if user.get("role") == "artisan":
        profile = await db.artisan_profiles.find_one({"user_id": user["user_id"]}, {"_id": 0, "artisan_id": 1})
        if not profile:
            return []
        rows = await db.disputes.find({"artisan_id": profile["artisan_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    else:
        rows = await db.disputes.find({"opened_by": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return rows

# --------------- Property Health & Maintenance Planner ---------------
@api_router.get("/properties/{pid}/health")
async def property_health(pid: str, user=Depends(get_current_user)):
    prop = await db.properties.find_one({"property_id": pid, "user_id": user["user_id"]}, {"_id": 0})
    if not prop:
        raise HTTPException(status_code=404, detail="Bien introuvable")
    equipment = await db.property_equipment.find({"property_id": pid}, {"_id": 0}).to_list(500)
    if not equipment:
        return {"score": 100, **growth.health_label(100), "equipment_count": 0, "demo": True}
    ok = sum(1 for e in equipment if e.get("status") == "ok")
    attention = sum(1 for e in equipment if e.get("status") in ("attention", "maintenance"))
    replace = sum(1 for e in equipment if e.get("status") == "replace")
    score = int(round((ok * 100 + attention * 60 + replace * 20) / len(equipment)))
    return {"score": score, **growth.health_label(score), "equipment_count": len(equipment),
            "ok_count": ok, "attention_count": attention, "replace_count": replace, "demo": False}

@api_router.get("/properties/{pid}/maintenance-plan")
async def maintenance_plan(pid: str, user=Depends(get_current_user)):
    prop = await db.properties.find_one({"property_id": pid, "user_id": user["user_id"]}, {"_id": 0})
    if not prop:
        raise HTTPException(status_code=404, detail="Bien introuvable")
    equipment = await db.property_equipment.find({"property_id": pid}, {"_id": 0}).to_list(500)
    plans = [p for p in (growth.suggest_maintenance(e) for e in equipment) if p]
    plans.sort(key=lambda p: p["due_on"])
    return {"plans": plans, "count": len(plans)}

@api_router.post("/properties/{pid}/maintenance-plan/generate-reminders")
async def generate_maintenance_reminders(pid: str, user=Depends(get_current_user)):
    prop = await db.properties.find_one({"property_id": pid, "user_id": user["user_id"]}, {"_id": 0})
    if not prop:
        raise HTTPException(status_code=404, detail="Bien introuvable")
    equipment = await db.property_equipment.find({"property_id": pid}, {"_id": 0}).to_list(500)
    created = 0
    for e in equipment:
        plan = growth.suggest_maintenance(e)
        if not plan:
            continue
        exists = await db.property_reminders.find_one({"property_id": pid, "equipment_id": plan["equipment_id"], "title": plan["title"], "status": {"$in": ["upcoming", "due"]}})
        if exists:
            continue
        await db.property_reminders.insert_one({
            "reminder_id": new_id("rem"),
            "property_id": pid,
            "user_id": user["user_id"],
            "title": plan["title"],
            "due_on": plan["due_on"],
            "frequency": "yearly" if plan["interval_months"] == 12 else None,
            "equipment_id": plan["equipment_id"],
            "notes": f"Généré automatiquement (intervalle {plan['interval_months']} mois)",
            "status": "upcoming",
            "created_at": now_utc().isoformat(),
        })
        created += 1
    return {"created": created}

# --------------- Growth hooks ---------------
# Wired into booking completion (see below) and review posting.

# ============================================================
ADMIN_EMAILS = {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}
ESCROW_STATES = ["pending", "held", "released", "refunded", "frozen"]

# ============================================================
# PAYMENTS & ESCROW — Stripe Connect, Commissions, Subscriptions
# ============================================================

async def require_admin(user=Depends(get_current_user)):
    if user.get("role") == "admin" or user.get("email", "").lower() in ADMIN_EMAILS:
        return user
    raise HTTPException(status_code=403, detail="Réservé aux administrateurs")

class ConnectOnboardInput(BaseModel):
    country: str = "FR"

class PaymentIntentInput(BaseModel):
    booking_id: str

class RefundInput(BaseModel):
    reason: Optional[str] = "requested_by_customer"
    amount_cents: Optional[int] = None

class SubscribePlanInput(BaseModel):
    plan_key: str  # starter | professional | enterprise

class CommissionConfigInput(BaseModel):
    global_bps: int
    min_cents: int = payments.DEFAULT_COMMISSION_MIN_CENTS

class CommissionRuleInput(BaseModel):
    kind: str  # trade | promo | exemption
    bps: int
    trade: Optional[str] = None
    artisan_id: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    label: Optional[str] = ""

class DisputeFreezeInput(BaseModel):
    booking_id: str
    reason: str

# ---------- Connect onboarding (pros) ----------
# ---------- Customer payment (creates escrow) ----------
# ---------- Escrow ----------
# ---------- Admin: commissions ----------
# ---------- Stripe webhooks — production entrypoint ----------

@app.post("/api/stripe/webhooks")
async def stripe_webhooks(request: Request):
    raw = await request.body()
    sig = request.headers.get("stripe-signature", "")
    event = payments.verify_webhook(raw, sig)
    if not event:
        raise HTTPException(status_code=400, detail="Signature invalide")
    event_id = event.get("id") or payments._mock_id("evt")
    # Idempotency guard
    seen = await db.stripe_events.find_one({"event_id": event_id})
    if seen:
        return {"received": True, "duplicate": True}
    await db.stripe_events.insert_one({"event_id": event_id, "type": event.get("type"), "created_at": payments.now_utc_iso()})

    et = event.get("type", "")
    data = (event.get("data") or {}).get("object", {})
    if et == "payment_intent.succeeded":
        await db.payments.update_one({"stripe_payment_intent_id": data.get("id")}, {"$set": {"status": "succeeded", "confirmed_at": payments.now_utc_iso()}})
        await db.escrows.update_one({"payment_id": {"$in": [p["payment_id"] async for p in db.payments.find({"stripe_payment_intent_id": data.get("id")}, {"_id": 0, "payment_id": 1})]}},
                                     {"$set": {"state": "held", "held_at": payments.now_utc_iso()}})
    elif et == "payment_intent.payment_failed":
        await db.payments.update_one({"stripe_payment_intent_id": data.get("id")}, {"$set": {"status": "payment_failed", "failed_at": payments.now_utc_iso()}})
    elif et == "charge.refunded":
        await payments.audit(db, None, "stripe.charge_refunded", data.get("id", ""), {})
    elif et in ("customer.subscription.updated", "customer.subscription.deleted"):
        await db.subscriptions_records.update_one({"stripe_subscription_id": data.get("id")}, {"$set": {"status": data.get("status"), "updated_at": payments.now_utc_iso()}})
    elif et == "account.updated":
        await db.stripe_accounts.update_one({"stripe_account_id": data.get("id")}, {"$set": {
            "charges_enabled": data.get("charges_enabled", False),
            "payouts_enabled": data.get("payouts_enabled", False),
            "details_submitted": data.get("details_submitted", False),
            "updated_at": payments.now_utc_iso(),
        }})
    return {"received": True, "type": et}


# ============================================================
# MY HOME — Property / Equipment / Documents / Reminders / Timeline / Insights
# ============================================================

PROPERTY_TYPES = ["apartment", "house", "office", "commercial", "vacation"]
EQUIPMENT_STATUSES = ["ok", "attention", "maintenance", "replace"]
DOC_CATEGORIES = ["invoice", "guarantee", "manual", "certificate", "plan", "photo", "report", "other"]
REMINDER_STATUSES = ["upcoming", "due", "done", "snoozed"]

class PropertyInput(BaseModel):
    name: str
    type: str = "apartment"
    address: Optional[str] = ""
    city: Optional[str] = ""
    postal_code: Optional[str] = ""
    surface: Optional[float] = None
    year_built: Optional[int] = None
    rooms: Optional[int] = None
    dpe_grade: Optional[str] = None
    cover_color: Optional[str] = "#0EA5E9"
    photos: List[str] = Field(default_factory=list)  # base64 or URL
    notes: Optional[str] = ""

class DocumentInput(BaseModel):
    title: str
    category: str = "other"
    file_uri: Optional[str] = ""  # base64 or URL
    equipment_id: Optional[str] = None
    notes: Optional[str] = ""

class ReminderInput(BaseModel):
    title: str
    due_on: str  # ISO date
    frequency: Optional[str] = None  # once | monthly | yearly | ...
    equipment_id: Optional[str] = None
    notes: Optional[str] = ""


class ReminderPatchInput(BaseModel):
    """
    Strict allow-list for PATCH /properties/{pid}/reminders/{rid}.

    Extra fields are REJECTED (`extra="forbid"`) so a malicious client cannot
    inject fields like `user_id`, `property_id`, `reminder_id`, `created_at`
    or arbitrary keys via mass-assignment.
    """
    title: Optional[str] = None
    due_on: Optional[str] = None
    frequency: Optional[str] = None
    equipment_id: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None

    model_config = {"extra": "forbid"}

async def _get_property(pid: str, user_id: str) -> dict:
    prop = await db.properties.find_one({"property_id": pid, "user_id": user_id}, {"_id": 0})
    if not prop:
        raise HTTPException(status_code=404, detail="Bien introuvable")
    return prop

# ----- Properties CRUD -----
# ----- Equipment -----
# ----- Documents -----
# ----- Reminders -----
# ----- Timeline (aggregated) -----
# ----- Insights -----
# ----- AI Cards (Coming Soon placeholders) -----
# ==================================================================
# Sprint 12 — Live Map (Uber-style) + Instant Intervention + Manual Slots
# ==================================================================
import math as _math

class PositionInput(BaseModel):
    lat: float
    lng: float
    available_now: Optional[bool] = None

class InterventionRequestInput(BaseModel):
    artisan_id: str
    description: str
    lat: float
    lng: float
    trade: Optional[str] = None
    urgency: Optional[str] = None
    price_estimate_min: Optional[float] = None
    price_estimate_max: Optional[float] = None

class InterventionActionInput(BaseModel):
    reason: Optional[str] = None

class SlotInput(BaseModel):
    date: str  # YYYY-MM-DD
    start_time: str  # HH:MM
    duration_min: int = 60
    recurring: Optional[str] = None  # "weekly" | None


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = _math.radians(lat2 - lat1)
    dlng = _math.radians(lng2 - lng1)
    a = _math.sin(dlat / 2) ** 2 + _math.cos(_math.radians(lat1)) * _math.cos(_math.radians(lat2)) * _math.sin(dlng / 2) ** 2
    return R * 2 * _math.atan2(_math.sqrt(a), _math.sqrt(1 - a))




# ----- Client: nearby artisans with live positions -----
async def _artisans_nearby_impl(lat, lng, radius, category, only_available_now, limit):
    query: Dict[str, Any] = {"is_subscribed": True}
    if category:
        query["trade"] = category
    artisans = await db.artisan_profiles.find(query, {"_id": 0}).to_list(300)
    enriched: List[Dict[str, Any]] = []
    for a in artisans:
        alat = a.get("live_lat") or a.get("lat")
        alng = a.get("live_lng") or a.get("lng")
        if alat is None or alng is None:
            seed = sum(ord(c) for c in a.get("artisan_id", "x")) % 100
            alat = lat + (seed - 50) * 0.0004
            alng = lng + ((seed * 7) % 100 - 50) * 0.0004
            a["_position_source"] = "simulated"
        else:
            a["_position_source"] = "live" if a.get("live_lat") else "base"
        dist = _haversine_km(lat, lng, alat, alng)
        if dist > radius:
            continue
        a2 = await enrich_artisan(a)
        a2["current_lat"] = alat
        a2["current_lng"] = alng
        a2["distance_km"] = round(dist, 2)
        a2["eta_min"] = int(min(120, max(5, dist * 3 + 5)))
        a2["available_now"] = bool(a.get("available_now"))
        a2["position_source"] = a["_position_source"]
        a2["live_updated_at"] = a.get("live_updated_at")
        if only_available_now and not a2["available_now"]:
            continue
        enriched.append(a2)
    enriched.sort(key=lambda x: x["distance_km"])
    return {"artisans": enriched[:limit], "radius_km": radius, "total": len(enriched)}


# ---------- Intervention lifecycle & final payment (Stripe Connect flow) ----------
class InterventionFinalInput(BaseModel):
    total_amount_cents: int


class PropertyEventInput(BaseModel):
    event_type: str = Field(..., description="installation|entretien|reparation|controle|nettoyage|sinistre|autre")
    title: str = Field(..., min_length=1, max_length=140)
    description: Optional[str] = None
    artisan_name: Optional[str] = None
    cost_cents: Optional[int] = None
    event_date: str = Field(..., description="ISO date YYYY-MM-DD")


app.include_router(api_router)

# --- Sprint 14 Phase 1 — Mount new modular routers ---------------------------
# These are attached AFTER the legacy `api_router` so that during migration the
# legacy inline endpoints keep serving traffic. As each domain is migrated, its
# legacy block is deleted from server.py and only the new router remains.
#
# Wait — FastAPI matches the FIRST registered path. To force the strangler to
# take precedence, we mount the new routers with the same `/api` prefix BEFORE
# include_router(api_router). We do that below by creating a "new" api_router
# and then merging both.
#
# Simpler approach chosen: since include_router uses the order of registration,
# we register the modular routers on `api_router` right here (which is added
# to `app` above). FastAPI does first-match, so as long as the legacy routes
# below have been REMOVED for a domain, the modular router takes over.
_modular_auth = build_auth_router(db, _get_current_user)
_modular_security = build_security_router(db, _get_current_user, _require_roles)
_modular_users = build_users_router(db, _get_current_user)
_modular_artisans = build_artisans_router(
    db, _get_current_user,
    enrich_artisan=enrich_artisan,
    trust_engine=trust_engine,
    calendar_sync=calendar_sync,
    growth=growth,
    category_map=CATEGORY_MAP,
    city_coords=CITY_COORDS,
    haversine=haversine,
    artisans_nearby_impl=_artisans_nearby_impl,
)
app.include_router(_modular_auth, prefix="/api")
app.include_router(_modular_security, prefix="/api")
app.include_router(_modular_users, prefix="/api")
app.include_router(_modular_artisans, prefix="/api")

# Bloc 4 — bookings, missions, interventions
_modular_bookings = build_bookings_router(
    db, _get_current_user,
    enrich_artisan=enrich_artisan,
    annotate_reviewed=annotate_reviewed,
    trust_engine=trust_engine,
)
_modular_missions = build_missions_router(
    db, _get_current_user,
    enrich_artisan=enrich_artisan,
    matching=matching,
    haversine=haversine,
    match_eta=match_eta,
    mission_artisan_card=mission_artisan_card,
    set_candidate_impl=_set_candidate,
)
_modular_interventions = build_interventions_router(db, _get_current_user)
app.include_router(_modular_bookings, prefix="/api")
app.include_router(_modular_missions, prefix="/api")
app.include_router(_modular_interventions, prefix="/api")

# ------------------------------------------------------------
# V1 migration (Option B) — mount the 6 partition modules.
# Each module receives every db handle / helper / Pydantic model / service
# it needs via keyword arguments. The factories populate their own module
# globals via `globals().update(deps)` at construction time, so the
# extracted route bodies find every referenced name at closure time.
# ------------------------------------------------------------
from routes.properties import build_properties_router
from routes.payments import build_payments_router
from routes.ai import build_ai_router
from routes.admin import build_admin_router
from routes.messaging import build_messaging_router
from routes.reviews import build_reviews_router

_modular_properties = build_properties_router(
    db=db, get_current_user=get_current_user,
    now_utc=now_utc, new_id=new_id,
    _get_property=_get_property,
    _append_passport_history=_append_passport_history,
    PROPERTY_TYPES=PROPERTY_TYPES,
    REMINDER_STATUSES=REMINDER_STATUSES,
    DOC_CATEGORIES=DOC_CATEGORIES,
    EQUIPMENT_STATUSES=EQUIPMENT_STATUSES,
    PropertyInput=PropertyInput,
    EquipmentInput=EquipmentInput,
    DocumentInput=DocumentInput,
    ReminderInput=ReminderInput,
    ReminderPatchInput=ReminderPatchInput,
    PropertyEventInput=PropertyEventInput,
)
_modular_payments = build_payments_router(
    db=db, get_current_user=get_current_user,
    now_utc=now_utc, new_id=new_id,
    require_admin=require_admin,
    _append_passport_history=_append_passport_history,
    _compute_deposit_cents=_compute_deposit_cents,
    ADMIN_EMAILS=ADMIN_EMAILS,
    ESCROW_STATES=ESCROW_STATES,
    PaymentIntentInput=PaymentIntentInput,
    ConnectOnboardInput=ConnectOnboardInput,
    RefundInput=RefundInput,
    DisputeFreezeInput=DisputeFreezeInput,
    DepositIntentInput=DepositIntentInput,
    DepositConfirmInput=DepositConfirmInput,
    InterventionFinalInput=InterventionFinalInput,
)
_modular_ai = build_ai_router(
    db=db, get_current_user=get_current_user,
    now_utc=now_utc, new_id=new_id,
    _load_conv=_load_conv,
    CATEGORIES=CATEGORIES,
    CATEGORY_MAP=CATEGORY_MAP,
    EMERGENT_LLM_KEY=EMERGENT_LLM_KEY,
    DiagnoseInput=DiagnoseInput,
    TranscribeInput=TranscribeInput,
    ConciergeStartInput=ConciergeStartInput,
    ConciergeMessageInput=ConciergeMessageInput,
    ConciergeVideoInput=ConciergeVideoInput,
)
_modular_admin = build_admin_router(
    db=db, get_current_user=get_current_user,
    now_utc=now_utc, new_id=new_id,
    require_admin=require_admin,
    CommissionConfigInput=CommissionConfigInput,
    CommissionRuleInput=CommissionRuleInput,
)
_modular_messaging = build_messaging_router(
    db=db, get_current_user=get_current_user,
    now_utc=now_utc, new_id=new_id,
    conv_view=conv_view,
    MessageInput=MessageInput,
)
_modular_reviews = build_reviews_router(
    db=db, get_current_user=get_current_user,
    now_utc=now_utc, new_id=new_id,
    recompute_artisan_rating=recompute_artisan_rating,
    ReviewInput=ReviewInput,
)
app.include_router(_modular_properties, prefix="/api")
app.include_router(_modular_payments, prefix="/api")
app.include_router(_modular_ai, prefix="/api")
app.include_router(_modular_admin, prefix="/api")
app.include_router(_modular_messaging, prefix="/api")
app.include_router(_modular_reviews, prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_parse_allowed_origins(),
    allow_origin_regex=os.environ.get("ALLOWED_ORIGIN_REGEX") or None,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
