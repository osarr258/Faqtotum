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

@api_router.post("/reviews")
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

@api_router.get("/reviews/artisan/{artisan_id}")
async def artisan_reviews(artisan_id: str):
    revs = await db.reviews.find({"artisan_id": artisan_id, "to_role": "artisan"}, {"_id": 0}).to_list(500)
    revs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return revs

# ----------------------------- Messaging -----------------------------

def conv_view(c: dict, user_id: str):
    c.pop("_id", None)
    is_client = c.get("client_id") == user_id
    c["other_name"] = c.get("artisan_name") if is_client else c.get("client_name")
    return c

@api_router.get("/conversations")
async def list_conversations(user=Depends(get_current_user)):
    uid = user["user_id"]
    convs = await db.conversations.find({"$or": [{"client_id": uid}, {"artisan_user_id": uid}]}, {"_id": 0}).to_list(500)
    convs.sort(key=lambda x: x.get("last_at", ""), reverse=True)
    return [conv_view(c, uid) for c in convs]

@api_router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, user=Depends(get_current_user)):
    uid = user["user_id"]
    conv = await db.conversations.find_one({"conversation_id": conversation_id}, {"_id": 0})
    if not conv or uid not in (conv.get("client_id"), conv.get("artisan_user_id")):
        raise HTTPException(status_code=403, detail="Conversation introuvable")
    msgs = await db.messages.find({"conversation_id": conversation_id}, {"_id": 0}).to_list(2000)
    msgs.sort(key=lambda x: x.get("created_at", ""))
    return {"conversation": conv_view(conv, uid), "messages": msgs}

@api_router.post("/conversations/{conversation_id}/messages")
async def send_message(conversation_id: str, data: MessageInput, user=Depends(get_current_user)):
    uid = user["user_id"]
    conv = await db.conversations.find_one({"conversation_id": conversation_id}, {"_id": 0})
    if not conv or uid not in (conv.get("client_id"), conv.get("artisan_user_id")):
        raise HTTPException(status_code=403, detail="Conversation introuvable")
    msg = {
        "message_id": new_id("msg"),
        "conversation_id": conversation_id,
        "sender_id": uid,
        "sender_name": user["name"],
        "text": data.text,
        "created_at": now_utc().isoformat(),
    }
    await db.messages.insert_one(msg)
    await db.conversations.update_one(
        {"conversation_id": conversation_id},
        {"$set": {"last_message": data.text, "last_at": msg["created_at"]}},
    )
    msg.pop("_id", None)
    return msg

# ----------------------------- AI: Diagnosis & Voice -----------------------------

@api_router.post("/ai/diagnose")
async def ai_diagnose(data: DiagnoseInput, user=Depends(get_current_user)):
    slugs = ", ".join(c["slug"] for c in CATEGORIES)
    system = (
        "Tu es l'IA de diagnostic de ProConnect, plateforme premium de services à domicile en France. "
        "Tu analyses la description et/ou les photos d'un problème domestique et tu produis un diagnostic clair. "
        "Réponds UNIQUEMENT avec un objet JSON valide (aucun texte autour), avec ces clés exactes: "
        "problem (string, résumé du problème en français), "
        f"trade (un slug parmi: {slugs}), "
        "trade_label (nom lisible du métier), "
        "urgency (un parmi: faible, moyenne, elevee, urgence), "
        "duration_min (number, heures), duration_max (number, heures), "
        "price_min (number, euros), price_max (number, euros), "
        "materials (array de strings), "
        "causes (array de 2 à 3 causes probables, strings), "
        "confidence (entier 0-100), "
        "advice (string, conseil de sécurité court en français)."
    )
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="Clé IA non configurée")
    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"diag-{uuid.uuid4().hex[:10]}", system_message=system).with_model("openai", "gpt-4o")
    files = []
    for img in (data.images or [])[:3]:
        b64 = img.split(",", 1)[1] if img.startswith("data:") else img
        files.append(ImageContent(image_base64=b64))
    text = data.text.strip() or "Analyse les photos fournies et établis le diagnostic."
    try:
        raw = await chat.send_message(UserMessage(text=text, file_contents=files or None))
    except Exception as e:
        logger.error(f"diagnose error: {e}")
        raise HTTPException(status_code=502, detail="Le diagnostic IA a échoué, réessayez.")
    txt = raw.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:]
        txt = txt.strip()
    try:
        result = json.loads(txt)
    except Exception:
        result = {
            "problem": text, "trade": "plombier", "trade_label": "Plombier",
            "urgency": "moyenne", "duration_min": 1, "duration_max": 2,
            "price_min": 80, "price_max": 200, "materials": [], "confidence": 50,
            "advice": "Coupez l'alimentation concernée et attendez le professionnel.",
        }
    if result.get("trade") not in CATEGORY_MAP:
        lbl = (result.get("trade_label") or "").lower()
        match = next((c["slug"] for c in CATEGORIES if c["name"].lower() in lbl or c["slug"] in lbl), "plombier")
        result["trade"] = match
    cat = CATEGORY_MAP.get(result["trade"])
    result["trade_label"] = cat["name"] if cat else result.get("trade_label")
    result["trade_icon"] = cat["icon"] if cat else "construct"
    return result

@api_router.post("/ai/transcribe")
async def ai_transcribe(data: TranscribeInput, user=Depends(get_current_user)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=500, detail="Clé IA non configurée")
    payload = data.audio_base64.split(",", 1)[-1]
    try:
        raw = base64.b64decode(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Audio invalide")
    suffix = "." + (data.ext or "m4a").lstrip(".")
    path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            f.write(raw)
            path = f.name
        stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
        res = await stt.transcribe(file=path, model="whisper-1", response_format="json", language="fr")
        text = getattr(res, "text", None)
        if text is None and isinstance(res, dict):
            text = res.get("text", "")
        if text is None:
            text = str(res)
        return {"text": text}
    except Exception as e:
        logger.error(f"transcribe error: {e}")
        raise HTTPException(status_code=502, detail="La transcription a échoué.")
    finally:
        if path and os.path.exists(path):
            os.remove(path)

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

@api_router.post("/concierge/start")
async def concierge_start(body: ConciergeStartInput, user=Depends(get_current_user)):
    sid = concierge.new_session_id()
    initial = concierge.initial_greeting()
    doc = {
        "session_id": sid,
        "user_id": user["user_id"],
        "property_id": body.property_id,
        "status": "active",
        "turns": [{"role": "assistant", "text": initial["ai_message"], "ai_state": initial, "created_at": concierge.now_iso()}],
        "detected_trade": None,
        "urgency": "faible",
        "confidence": 0,
        "final_summary": None,
        "video_pending": False,
        "created_at": concierge.now_iso(),
        "updated_at": concierge.now_iso(),
    }
    await db.concierge_sessions.insert_one(dict(doc))
    return {"session_id": sid, "state": initial}

@api_router.post("/concierge/{sid}/message")
async def concierge_message(sid: str, body: ConciergeMessageInput, user=Depends(get_current_user)):
    session = await _load_conv(sid, user["user_id"])
    if session["status"] != "active":
        raise HTTPException(status_code=400, detail="Session déjà terminée")

    user_text = (body.text or "").strip()
    if body.voice_base64:
        try:
            payload_v = body.voice_base64.split(",", 1)[-1]
            raw = base64.b64decode(payload_v)
            suffix = "." + (body.voice_ext or "m4a").lstrip(".")
            path = None
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
                f.write(raw)
                path = f.name
            stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
            res = await stt.transcribe(file=path, model="whisper-1", response_format="json", language="fr")
            transcript = getattr(res, "text", None) or (res.get("text") if isinstance(res, dict) else "") or ""
            user_text = f"{user_text} {transcript}".strip() if user_text else transcript
            if path and os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.warning(f"concierge voice transcribe: {e}")

    turn_user = {
        "role": "user",
        "text": user_text,
        "attachments": {"photos_count": len(body.photos_base64 or []), "voice": bool(body.voice_base64)},
        "created_at": concierge.now_iso(),
    }
    try:
        state = await concierge.next_turn(sid, user_text, body.photos_base64)
    except Exception as e:
        logger.error(f"concierge next_turn failed: {e}")
        raise HTTPException(status_code=502, detail="AURA n'a pas pu répondre, réessayez dans un instant.")

    turn_ai = {"role": "assistant", "text": state["ai_message"], "ai_state": state, "created_at": concierge.now_iso()}
    updates = {
        "detected_trade": state.get("detected_trade") or session.get("detected_trade"),
        "urgency": (state.get("live_diagnosis") or {}).get("urgency") or session.get("urgency"),
        "confidence": (state.get("live_diagnosis") or {}).get("confidence") or session.get("confidence"),
        "updated_at": concierge.now_iso(),
    }
    if state.get("next_action") == "finish" and state.get("summary"):
        updates["status"] = "completed"
        updates["final_summary"] = state["summary"]
    await db.concierge_sessions.update_one(
        {"session_id": sid},
        {"$push": {"turns": {"$each": [turn_user, turn_ai]}}, "$set": updates},
    )
    return {"state": state, "user_text": user_text}

@api_router.post("/concierge/{sid}/finish")
async def concierge_finish(sid: str, user=Depends(get_current_user)):
    session = await _load_conv(sid, user["user_id"])
    if session["status"] != "active":
        return {"state": {"summary": session.get("final_summary")}, "already_finished": True}
    try:
        state = await concierge.next_turn(sid, "Fais-moi le résumé final maintenant, avec la recommandation.", None, force_finish=True)
    except Exception as e:
        logger.error(f"concierge force finish: {e}")
        raise HTTPException(status_code=502, detail="Résumé impossible pour le moment, réessayez.")
    updates = {
        "status": "completed",
        "final_summary": state.get("summary"),
        "detected_trade": state.get("detected_trade") or session.get("detected_trade"),
        "updated_at": concierge.now_iso(),
    }
    await db.concierge_sessions.update_one(
        {"session_id": sid},
        {"$push": {"turns": {"role": "assistant", "text": state["ai_message"], "ai_state": state, "created_at": concierge.now_iso()}},
         "$set": updates},
    )
    return {"state": state}

@api_router.post("/concierge/{sid}/video")
async def concierge_attach_video(sid: str, body: ConciergeVideoInput, user=Depends(get_current_user)):
    await _load_conv(sid, user["user_id"])
    note = {
        "role": "system",
        "text": f"Vidéo reçue ({body.filename}, {body.size_bytes} octets). L'analyse vidéo IA sera bientôt disponible.",
        "created_at": concierge.now_iso(),
        "video_placeholder": True,
    }
    await db.concierge_sessions.update_one(
        {"session_id": sid},
        {"$push": {"turns": note}, "$set": {"video_pending": True, "updated_at": concierge.now_iso()}},
    )
    return {"attached": True, "message": "L'analyse vidéo IA arrive bientôt. En attendant, décrivez ce que vous voyez ou envoyez une photo."}

@api_router.get("/concierge/sessions")
async def concierge_list_sessions(user=Depends(get_current_user)):
    rows = await db.concierge_sessions.find(
        {"user_id": user["user_id"]},
        {"_id": 0, "session_id": 1, "status": 1, "detected_trade": 1, "urgency": 1, "confidence": 1,
         "final_summary": 1, "created_at": 1, "updated_at": 1, "turns": {"$slice": -1}},
    ).sort("updated_at", -1).to_list(100)
    for r in rows:
        last = r.get("turns") or []
        r["last_message"] = last[-1]["text"] if last else ""
        r.pop("turns", None)
    return rows

@api_router.get("/concierge/{sid}")
async def concierge_get_session(sid: str, user=Depends(get_current_user)):
    return await _load_conv(sid, user["user_id"])

@api_router.delete("/concierge/{sid}")
async def concierge_delete_session(sid: str, user=Depends(get_current_user)):
    await _load_conv(sid, user["user_id"])
    await db.concierge_sessions.delete_one({"session_id": sid, "user_id": user["user_id"]})
    return {"ok": True}

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
@api_router.post("/connect/onboard")
async def connect_onboard(body: ConnectOnboardInput, user=Depends(get_current_user)):
    if user.get("role") != "artisan":
        raise HTTPException(status_code=403, detail="Réservé aux artisans")
    profile = await db.artisan_profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not profile:
        raise HTTPException(status_code=400, detail="Créez d'abord votre profil artisan")

    existing = await db.stripe_accounts.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if existing:
        acct_id = existing["stripe_account_id"]
    else:
        acct = payments.create_connect_account(user["email"], body.country)
        acct_id = acct["id"]
        await db.stripe_accounts.insert_one({
            "user_id": user["user_id"],
            "artisan_id": profile["artisan_id"],
            "stripe_account_id": acct_id,
            "country": body.country,
            "charges_enabled": False,
            "payouts_enabled": False,
            "details_submitted": False,
            "created_at": payments.now_utc_iso(),
        })
        await payments.audit(db, user["user_id"], "connect.account_created", acct_id, {"artisan_id": profile["artisan_id"]})

    link = payments.create_account_link(
        acct_id,
        return_url=f"{payments.PLATFORM_URL}/connect/return",
        refresh_url=f"{payments.PLATFORM_URL}/connect/refresh",
    )
    return {"onboarding_url": link["url"], "expires_at": link.get("expires_at"), "stripe_account_id": acct_id, "mock_mode": payments.MOCK_MODE}

@api_router.get("/connect/status")
async def connect_status(user=Depends(get_current_user)):
    row = await db.stripe_accounts.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not row:
        return {"connected": False}
    fresh = payments.retrieve_account(row["stripe_account_id"])
    await db.stripe_accounts.update_one(
        {"stripe_account_id": row["stripe_account_id"]},
        {"$set": {
            "charges_enabled": fresh.get("charges_enabled", False),
            "payouts_enabled": fresh.get("payouts_enabled", False),
            "details_submitted": fresh.get("details_submitted", False),
            "requirements": fresh.get("requirements", {}),
            "updated_at": payments.now_utc_iso(),
        }},
    )
    return {
        "connected": True,
        "stripe_account_id": row["stripe_account_id"],
        "charges_enabled": fresh.get("charges_enabled", False),
        "payouts_enabled": fresh.get("payouts_enabled", False),
        "details_submitted": fresh.get("details_submitted", False),
        "requirements": fresh.get("requirements", {}),
        "mock_mode": payments.MOCK_MODE,
    }

# ---------- Customer payment (creates escrow) ----------
@api_router.post("/payments/create-intent")
async def create_payment_intent(body: PaymentIntentInput, user=Depends(get_current_user)):
    booking = await db.bookings.find_one({"booking_id": body.booking_id, "client_id": user["user_id"]}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Réservation introuvable")
    existing = await db.payments.find_one({"booking_id": body.booking_id, "status": {"$in": ["requires_confirmation", "succeeded"]}}, {"_id": 0})
    if existing:
        return {"payment_id": existing["payment_id"], "client_secret": existing.get("client_secret"), "amount_cents": existing["amount_cents"]}

    artisan = await db.artisan_profiles.find_one({"artisan_id": booking["artisan_id"]}, {"_id": 0}) or {}
    hourly = int(round((artisan.get("hourly_rate") or 60) * 100))  # gross cents
    amount = max(hourly, 2000)  # min 20€
    intent = payments.create_payment_intent(
        amount_cents=amount,
        currency="eur",
        metadata={"booking_id": body.booking_id, "client_id": user["user_id"], "artisan_id": booking["artisan_id"]},
        customer_email=user["email"],
    )
    payment_id = payments._mock_id("pay") if payments.MOCK_MODE else new_id("pay")
    doc = {
        "payment_id": payment_id,
        "booking_id": body.booking_id,
        "client_id": user["user_id"],
        "artisan_id": booking["artisan_id"],
        "stripe_payment_intent_id": intent["id"],
        "client_secret": intent.get("client_secret"),
        "amount_cents": amount,
        "currency": "eur",
        "status": intent.get("status", "requires_confirmation"),
        "created_at": payments.now_utc_iso(),
    }
    await db.payments.insert_one(dict(doc))
    # Create escrow envelope (state=pending; becomes 'held' once webhook confirms).
    await db.escrows.insert_one({
        "escrow_id": new_id("esc"),
        "payment_id": payment_id,
        "booking_id": body.booking_id,
        "artisan_id": booking["artisan_id"],
        "amount_cents": amount,
        "state": "pending",
        "created_at": payments.now_utc_iso(),
    })
    await payments.audit(db, user["user_id"], "payment.intent_created", payment_id, {"amount_cents": amount, "booking_id": body.booking_id})
    return {"payment_id": payment_id, "client_secret": intent.get("client_secret"), "amount_cents": amount, "mock_mode": payments.MOCK_MODE}

@api_router.post("/payments/{payment_id}/mock-confirm")
async def mock_confirm_payment(payment_id: str, user=Depends(get_current_user)):
    """DEV ONLY — simulates a successful Stripe webhook when running in MOCK_MODE.
    In production, Stripe hits /stripe/webhooks and moves the state forward."""
    if not payments.MOCK_MODE:
        raise HTTPException(status_code=400, detail="Endpoint disponible uniquement en MOCK_MODE")
    p = await db.payments.find_one({"payment_id": payment_id}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Paiement introuvable")
    await db.payments.update_one({"payment_id": payment_id}, {"$set": {"status": "succeeded", "confirmed_at": payments.now_utc_iso()}})
    await db.escrows.update_one({"payment_id": payment_id}, {"$set": {"state": "held", "held_at": payments.now_utc_iso()}})
    await payments.audit(db, user["user_id"], "payment.succeeded", payment_id, {"mock": True})
    return {"ok": True, "status": "succeeded"}

# ---------- Escrow ----------
@api_router.get("/escrows/mine")
async def my_escrows(user=Depends(get_current_user)):
    if user.get("role") == "artisan":
        prof = await db.artisan_profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
        if not prof:
            return []
        rows = await db.escrows.find({"artisan_id": prof["artisan_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    else:
        rows = await db.escrows.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
        # filter to those on this client's bookings
        booking_ids = [r["booking_id"] for r in rows]
        clients = {b["booking_id"]: b["client_id"] async for b in db.bookings.find({"booking_id": {"$in": booking_ids}}, {"_id": 0, "booking_id": 1, "client_id": 1})}
        rows = [r for r in rows if clients.get(r["booking_id"]) == user["user_id"]]
    return rows

@api_router.post("/escrow/{booking_id}/release")
async def escrow_release(booking_id: str, user=Depends(get_current_user)):
    booking = await db.bookings.find_one({"booking_id": booking_id, "client_id": user["user_id"]}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Réservation introuvable")
    escrow = await db.escrows.find_one({"booking_id": booking_id}, {"_id": 0})
    if not escrow:
        raise HTTPException(status_code=404, detail="Escrow introuvable")
    if escrow["state"] != "held":
        raise HTTPException(status_code=400, detail=f"Escrow en état '{escrow['state']}', ne peut pas être libéré")

    artisan = await db.artisan_profiles.find_one({"artisan_id": booking["artisan_id"]}, {"_id": 0}) or {}
    connected = await db.stripe_accounts.find_one({"artisan_id": booking["artisan_id"]}, {"_id": 0})
    if not connected:
        raise HTTPException(status_code=400, detail="L'artisan n'a pas encore configuré Stripe Connect")

    bps = await payments.resolve_commission_bps(db, artisan)
    fee = payments.commission_amount(escrow["amount_cents"], bps)
    net = escrow["amount_cents"] - fee

    transfer = payments.create_transfer(
        amount_cents=net,
        currency=escrow.get("currency", "eur"),
        destination=connected["stripe_account_id"],
        transfer_group=booking_id,
        metadata={"booking_id": booking_id, "artisan_id": booking["artisan_id"]},
    )
    await db.transfers.insert_one({
        "transfer_id": new_id("tr"),
        "stripe_transfer_id": transfer["id"],
        "booking_id": booking_id,
        "escrow_id": escrow["escrow_id"],
        "artisan_id": booking["artisan_id"],
        "gross_cents": escrow["amount_cents"],
        "commission_bps": bps,
        "commission_cents": fee,
        "net_cents": net,
        "created_at": payments.now_utc_iso(),
    })
    await db.escrows.update_one({"escrow_id": escrow["escrow_id"]}, {"$set": {
        "state": "released",
        "released_at": payments.now_utc_iso(),
        "commission_bps": bps,
        "commission_cents": fee,
        "net_cents": net,
        "stripe_transfer_id": transfer["id"],
    }})
    await payments.audit(db, user["user_id"], "escrow.released", escrow["escrow_id"], {
        "gross_cents": escrow["amount_cents"], "commission_cents": fee, "net_cents": net,
    })
    return {"ok": True, "gross_cents": escrow["amount_cents"], "commission_cents": fee, "net_cents": net, "transfer_id": transfer["id"]}

@api_router.post("/escrow/{booking_id}/refund")
async def escrow_refund(booking_id: str, body: RefundInput, user=Depends(get_current_user)):
    booking = await db.bookings.find_one({"booking_id": booking_id, "client_id": user["user_id"]}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Réservation introuvable")
    escrow = await db.escrows.find_one({"booking_id": booking_id}, {"_id": 0})
    payment = await db.payments.find_one({"booking_id": booking_id, "status": "succeeded"}, {"_id": 0})
    if not escrow or not payment:
        raise HTTPException(status_code=404, detail="Paiement introuvable")
    if escrow["state"] not in ("held", "frozen"):
        raise HTTPException(status_code=400, detail=f"Escrow en état '{escrow['state']}', non remboursable")
    refund_amount = body.amount_cents or escrow["amount_cents"]
    refund = payments.refund_payment(payment["stripe_payment_intent_id"], refund_amount, body.reason)
    await db.refunds.insert_one({
        "refund_id": new_id("ref"),
        "stripe_refund_id": refund["id"],
        "payment_id": payment["payment_id"],
        "booking_id": booking_id,
        "amount_cents": refund_amount,
        "reason": body.reason,
        "created_at": payments.now_utc_iso(),
    })
    await db.escrows.update_one({"escrow_id": escrow["escrow_id"]}, {"$set": {"state": "refunded", "refunded_at": payments.now_utc_iso()}})
    await payments.audit(db, user["user_id"], "escrow.refunded", escrow["escrow_id"], {"amount_cents": refund_amount, "reason": body.reason})
    return {"ok": True, "refund_id": refund["id"], "amount_cents": refund_amount}

@api_router.post("/escrow/freeze")
async def escrow_freeze(body: DisputeFreezeInput, user=Depends(get_current_user)):
    """Freeze an escrow when a dispute is opened. Only admins or the funds owner can freeze.
    The Trust Engine's POST /disputes should also call this internally for severe cases."""
    escrow = await db.escrows.find_one({"booking_id": body.booking_id}, {"_id": 0})
    if not escrow:
        raise HTTPException(status_code=404, detail="Escrow introuvable")
    booking = await db.bookings.find_one({"booking_id": body.booking_id}, {"_id": 0})
    is_admin = user.get("email", "").lower() in ADMIN_EMAILS
    is_owner = booking and booking.get("client_id") == user["user_id"]
    if not (is_admin or is_owner):
        raise HTTPException(status_code=403, detail="Non autorisé")
    if escrow["state"] != "held":
        raise HTTPException(status_code=400, detail="Seuls les escrows 'held' peuvent être gelés")
    await db.escrows.update_one({"escrow_id": escrow["escrow_id"]}, {"$set": {
        "state": "frozen", "frozen_at": payments.now_utc_iso(), "freeze_reason": body.reason,
    }})
    await payments.audit(db, user["user_id"], "escrow.frozen", escrow["escrow_id"], {"reason": body.reason})
    return {"ok": True, "state": "frozen"}

# ---------- Admin: commissions ----------
@api_router.get("/admin/finance/overview")
async def admin_finance_overview(user=Depends(require_admin)):
    total_gross = await db.payments.aggregate([
        {"$match": {"status": "succeeded"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_cents"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    total_commissions = await db.transfers.aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$commission_cents"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    total_refunds = await db.refunds.aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$amount_cents"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    subs = await db.subscriptions_records.aggregate([
        {"$match": {"status": "active"}}, {"$group": {"_id": "$plan_key", "count": {"$sum": 1}}},
    ]).to_list(20)
    plan_price = {p["key"]: p["price_cents"] for p in payments.PLANS}
    mrr = sum(row["count"] * plan_price.get(row["_id"], 0) for row in subs)

    pending_payouts = await db.escrows.aggregate([
        {"$match": {"state": "held"}}, {"$group": {"_id": None, "total": {"$sum": "$amount_cents"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    failed_payments = await db.payments.count_documents({"status": "payment_failed"})
    top_trades = await db.transfers.aggregate([
        {"$lookup": {"from": "artisan_profiles", "localField": "artisan_id", "foreignField": "artisan_id", "as": "a"}},
        {"$unwind": "$a"},
        {"$group": {"_id": "$a.trade", "revenue": {"$sum": "$gross_cents"}, "count": {"$sum": 1}}},
        {"$sort": {"revenue": -1}},
        {"$limit": 5},
    ]).to_list(5)
    return {
        "gross_cents": total_gross[0]["total"] if total_gross else 0,
        "payments_count": total_gross[0]["count"] if total_gross else 0,
        "commission_cents": total_commissions[0]["total"] if total_commissions else 0,
        "transfers_count": total_commissions[0]["count"] if total_commissions else 0,
        "refunds_cents": total_refunds[0]["total"] if total_refunds else 0,
        "refunds_count": total_refunds[0]["count"] if total_refunds else 0,
        "active_subscriptions": [{"plan": r["_id"], "count": r["count"]} for r in subs],
        "mrr_cents": mrr,
        "pending_payouts_cents": pending_payouts[0]["total"] if pending_payouts else 0,
        "pending_payouts_count": pending_payouts[0]["count"] if pending_payouts else 0,
        "failed_payments": failed_payments,
        "top_trades": [{"trade": r["_id"], "revenue_cents": r["revenue"], "count": r["count"]} for r in top_trades],
        "mock_mode": payments.MOCK_MODE,
    }

@api_router.get("/admin/commissions")
async def get_commission_config(user=Depends(require_admin)):
    cfg = await db.platform_config.find_one({"key": "commission"}, {"_id": 0}) or {}
    rules = await db.commission_rules.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {
        "global_bps": cfg.get("global_bps", payments.DEFAULT_COMMISSION_BPS),
        "min_cents": cfg.get("min_cents", payments.DEFAULT_COMMISSION_MIN_CENTS),
        "rules": rules,
    }

@api_router.put("/admin/commissions")
async def set_commission_config(body: CommissionConfigInput, user=Depends(require_admin)):
    await db.platform_config.update_one(
        {"key": "commission"},
        {"$set": {"key": "commission", "global_bps": int(body.global_bps), "min_cents": int(body.min_cents), "updated_by": user["user_id"], "updated_at": payments.now_utc_iso()}},
        upsert=True,
    )
    await payments.audit(db, user["user_id"], "commission.global_updated", "commission", {"global_bps": body.global_bps, "min_cents": body.min_cents})
    return {"ok": True, "global_bps": body.global_bps, "min_cents": body.min_cents}

@api_router.post("/admin/commission-rules")
async def create_commission_rule(body: CommissionRuleInput, user=Depends(require_admin)):
    if body.kind not in ("trade", "promo", "exemption"):
        raise HTTPException(status_code=400, detail="kind invalide")
    doc = {
        "rule_id": new_id("crule"),
        "kind": body.kind,
        "bps": int(body.bps),
        "trade": body.trade,
        "artisan_id": body.artisan_id,
        "start_at": body.start_at,
        "end_at": body.end_at,
        "label": body.label or "",
        "active": True,
        "created_by": user["user_id"],
        "created_at": payments.now_utc_iso(),
    }
    await db.commission_rules.insert_one(dict(doc))
    await payments.audit(db, user["user_id"], "commission.rule_created", doc["rule_id"], {"kind": body.kind, "bps": body.bps})
    return doc

@api_router.delete("/admin/commission-rules/{rule_id}")
async def delete_commission_rule(rule_id: str, user=Depends(require_admin)):
    await db.commission_rules.update_one({"rule_id": rule_id}, {"$set": {"active": False, "deactivated_at": payments.now_utc_iso()}})
    await payments.audit(db, user["user_id"], "commission.rule_deactivated", rule_id)
    return {"ok": True}

@api_router.get("/admin/audit-logs")
async def admin_audit_logs(limit: int = 100, user=Depends(require_admin)):
    limit = max(1, min(500, limit))
    rows = await db.audit_logs.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return rows

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
@api_router.get("/properties")
async def list_properties(user=Depends(get_current_user)):
    props = await db.properties.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    # attach quick counts
    out = []
    for p in props:
        pid = p["property_id"]
        equip_count = await db.property_equipment.count_documents({"property_id": pid})
        doc_count = await db.property_documents.count_documents({"property_id": pid})
        reminder_count = await db.property_reminders.count_documents({"property_id": pid, "status": {"$in": ["upcoming", "due"]}})
        p["equipment_count"] = equip_count
        p["document_count"] = doc_count
        p["reminder_count"] = reminder_count
        out.append(p)
    return out

@api_router.post("/properties")
async def create_property(body: PropertyInput, user=Depends(get_current_user)):
    if body.type not in PROPERTY_TYPES:
        raise HTTPException(status_code=400, detail="Type de bien invalide")
    prop = {
        "property_id": new_id("prop"),
        "user_id": user["user_id"],
        "name": body.name.strip(),
        "type": body.type,
        "address": (body.address or "").strip(),
        "city": (body.city or "").strip(),
        "postal_code": (body.postal_code or "").strip(),
        "surface": body.surface,
        "year_built": body.year_built,
        "rooms": body.rooms,
        "dpe_grade": body.dpe_grade,
        "cover_color": body.cover_color or "#0EA5E9",
        "photos": body.photos or [],
        "notes": (body.notes or "").strip(),
        "health_score": 100,
        "share_token": None,
        "created_at": now_utc().isoformat(),
        "updated_at": now_utc().isoformat(),
    }
    await db.properties.insert_one(dict(prop))
    return prop

@api_router.get("/properties/{pid}")
async def get_property(pid: str, user=Depends(get_current_user)):
    return await _get_property(pid, user["user_id"])

@api_router.patch("/properties/{pid}")
async def update_property(pid: str, body: dict, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    if "type" in body and body["type"] not in PROPERTY_TYPES:
        raise HTTPException(status_code=400, detail="Type de bien invalide")
    allowed = {"name", "type", "address", "city", "postal_code", "surface", "year_built", "rooms", "dpe_grade", "cover_color", "photos", "notes"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if "name" in updates and isinstance(updates["name"], str):
        updates["name"] = updates["name"].strip()
    if "address" in updates and isinstance(updates["address"], str):
        updates["address"] = updates["address"].strip()
    if "notes" in updates and isinstance(updates["notes"], str):
        updates["notes"] = updates["notes"].strip()
    updates["updated_at"] = now_utc().isoformat()
    await db.properties.update_one({"property_id": pid}, {"$set": updates})
    return await db.properties.find_one({"property_id": pid}, {"_id": 0})

@api_router.delete("/properties/{pid}")
async def delete_property(pid: str, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    await db.properties.delete_one({"property_id": pid})
    await db.property_equipment.delete_many({"property_id": pid})
    await db.property_documents.delete_many({"property_id": pid})
    await db.property_reminders.delete_many({"property_id": pid})
    return {"ok": True}

# ----- Equipment -----
@api_router.get("/properties/{pid}/equipment")
async def list_equipment(pid: str, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    items = await db.property_equipment.find({"property_id": pid}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items

@api_router.post("/properties/{pid}/equipment")
async def create_equipment(pid: str, body: EquipmentInput, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    if body.status not in EQUIPMENT_STATUSES:
        raise HTTPException(status_code=400, detail="Statut invalide")
    doc = {
        "equipment_id": new_id("eq"),
        "property_id": pid,
        "user_id": user["user_id"],
        "name": body.name.strip(),
        "category": body.category or "other",
        "brand": body.brand or "",
        "model": body.model or "",
        "serial_number": body.serial_number or "",
        "installed_on": body.installed_on,
        "installer": body.installer or "",
        "warranty_until": body.warranty_until,
        "photos": body.photos or [],
        "documents": body.documents or [],
        "status": body.status or "ok",
        "notes": body.notes or "",
        "created_at": now_utc().isoformat(),
        "updated_at": now_utc().isoformat(),
    }
    await db.property_equipment.insert_one(dict(doc))
    # Auto-generate maintenance + warranty reminders (idempotent)
    eq_for_svc = {
        "equipment_id": doc["equipment_id"],
        "property_id": doc["property_id"],
        "user_id": doc["user_id"],
        "category": doc["category"],
        "installed_at": doc.get("installed_on"),
        "last_maintenance_at": None,
        "warranty_until": doc.get("warranty_until"),
    }
    try:
        reminders_created = await homes_svc.generate_reminders_for_equipment(db, eq_for_svc)
        doc["_auto_reminders_created"] = len(reminders_created)
    except Exception as ex:
        logger.warning(f"auto-reminder generation failed: {ex}")
        doc["_auto_reminders_created"] = 0
    return doc

@api_router.get("/properties/{pid}/equipment/{eid}")
async def get_equipment(pid: str, eid: str, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    e = await db.property_equipment.find_one({"equipment_id": eid, "property_id": pid}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Équipement introuvable")
    return e

@api_router.patch("/properties/{pid}/equipment/{eid}")
async def update_equipment(pid: str, eid: str, body: dict, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    e = await db.property_equipment.find_one({"equipment_id": eid, "property_id": pid})
    if not e:
        raise HTTPException(status_code=404, detail="Équipement introuvable")
    if "status" in body and body["status"] not in EQUIPMENT_STATUSES:
        raise HTTPException(status_code=400, detail="Statut invalide")
    allowed = {"name", "category", "brand", "model", "serial_number", "installed_on", "installer", "warranty_until", "photos", "documents", "status", "notes"}
    updates = {k: v for k, v in body.items() if k in allowed}
    updates["updated_at"] = now_utc().isoformat()
    await db.property_equipment.update_one({"equipment_id": eid}, {"$set": updates})
    return await db.property_equipment.find_one({"equipment_id": eid}, {"_id": 0})

@api_router.delete("/properties/{pid}/equipment/{eid}")
async def delete_equipment(pid: str, eid: str, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    await db.property_equipment.delete_one({"equipment_id": eid, "property_id": pid})
    return {"ok": True}

# ----- Documents -----
@api_router.get("/properties/{pid}/documents")
async def list_documents(pid: str, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    return await db.property_documents.find({"property_id": pid}, {"_id": 0}).sort("created_at", -1).to_list(500)

@api_router.post("/properties/{pid}/documents")
async def create_document(pid: str, body: DocumentInput, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    if body.category not in DOC_CATEGORIES:
        raise HTTPException(status_code=400, detail="Catégorie invalide")
    d = {
        "document_id": new_id("doc"),
        "property_id": pid,
        "user_id": user["user_id"],
        "title": body.title.strip(),
        "category": body.category,
        "file_uri": body.file_uri or "",
        "equipment_id": body.equipment_id,
        "notes": body.notes or "",
        "created_at": now_utc().isoformat(),
    }
    await db.property_documents.insert_one(dict(d))
    return d

@api_router.delete("/properties/{pid}/documents/{doc_id}")
async def delete_document(pid: str, doc_id: str, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    await db.property_documents.delete_one({"document_id": doc_id, "property_id": pid})
    return {"ok": True}

# ----- Reminders -----
@api_router.get("/properties/{pid}/reminders")
async def list_reminders(pid: str, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    items = await db.property_reminders.find({"property_id": pid}, {"_id": 0}).sort("due_on", 1).to_list(500)
    # Auto-flag due
    today = now_utc().date().isoformat()
    for r in items:
        if r.get("status") == "upcoming" and r.get("due_on") and r["due_on"] <= today:
            r["status"] = "due"
    return items

@api_router.post("/properties/{pid}/reminders")
async def create_reminder(pid: str, body: ReminderInput, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    r = {
        "reminder_id": new_id("rem"),
        "property_id": pid,
        "user_id": user["user_id"],
        "title": body.title.strip(),
        "due_on": body.due_on,
        "frequency": body.frequency,
        "equipment_id": body.equipment_id,
        "notes": body.notes or "",
        "status": "upcoming",
        "created_at": now_utc().isoformat(),
    }
    await db.property_reminders.insert_one(dict(r))
    return r

@api_router.patch("/properties/{pid}/reminders/{rid}")
async def update_reminder(pid: str, rid: str, body: ReminderPatchInput, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    # `exclude_unset` → only fields explicitly sent by the client are updated.
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Aucun champ à modifier")
    if "status" in updates and updates["status"] not in REMINDER_STATUSES:
        raise HTTPException(status_code=400, detail="Statut invalide")
    updates["updated_at"] = now_utc().isoformat()
    await db.property_reminders.update_one(
        {"reminder_id": rid, "property_id": pid}, {"$set": updates}
    )
    return await db.property_reminders.find_one({"reminder_id": rid}, {"_id": 0})

@api_router.delete("/properties/{pid}/reminders/{rid}")
async def delete_reminder(pid: str, rid: str, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    await db.property_reminders.delete_one({"reminder_id": rid, "property_id": pid})
    return {"ok": True}

# ----- Timeline (aggregated) -----
@api_router.get("/properties/{pid}/timeline")
async def property_timeline(pid: str, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    events = []
    # equipment install events
    async for e in db.property_equipment.find({"property_id": pid}, {"_id": 0}):
        if e.get("installed_on"):
            events.append({
                "id": e["equipment_id"],
                "type": "equipment_installed",
                "title": f"{e['name']} installé",
                "subtitle": e.get("brand") or "",
                "date": e["installed_on"],
                "icon": "cog",
                "ref": {"equipment_id": e["equipment_id"]},
            })
    # documents added
    async for d in db.property_documents.find({"property_id": pid}, {"_id": 0}):
        events.append({
            "id": d["document_id"],
            "type": "document",
            "title": d["title"],
            "subtitle": d["category"],
            "date": d["created_at"][:10],
            "icon": "document-text",
            "ref": {"document_id": d["document_id"]},
        })
    # linked bookings (interventions completed on this property)
    async for b in db.bookings.find({"client_id": user["user_id"], "property_id": pid}, {"_id": 0}):
        events.append({
            "id": b["booking_id"],
            "type": "intervention",
            "title": b.get("description", "Intervention"),
            "subtitle": f"Statut: {b.get('status', 'pending')}",
            "date": (b.get("scheduled_at") or b.get("created_at", ""))[:10],
            "icon": "briefcase",
            "ref": {"booking_id": b["booking_id"]},
        })
    # reminders completed
    async for r in db.property_reminders.find({"property_id": pid, "status": "done"}, {"_id": 0}):
        events.append({
            "id": r["reminder_id"],
            "type": "reminder_done",
            "title": r["title"],
            "subtitle": "Rappel terminé",
            "date": r.get("updated_at", r.get("due_on", ""))[:10],
            "icon": "checkmark-circle",
            "ref": {"reminder_id": r["reminder_id"]},
        })
    # sort desc by date
    events.sort(key=lambda x: x["date"] or "", reverse=True)
    # group by year
    grouped: dict = {}
    for ev in events:
        y = (ev["date"] or "")[:4] or "—"
        grouped.setdefault(y, []).append(ev)
    return {"events": events, "grouped": grouped}

# ----- Insights -----
@api_router.get("/properties/{pid}/insights")
async def property_insights(pid: str, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    equipment_count = await db.property_equipment.count_documents({"property_id": pid})
    ok_count = await db.property_equipment.count_documents({"property_id": pid, "status": "ok"})
    attention_count = await db.property_equipment.count_documents({"property_id": pid, "status": {"$in": ["attention", "maintenance", "replace"]}})
    document_count = await db.property_documents.count_documents({"property_id": pid})
    upcoming = await db.property_reminders.count_documents({"property_id": pid, "status": {"$in": ["upcoming", "due"]}})
    # Interventions linked
    interventions = await db.bookings.count_documents({"client_id": user["user_id"], "property_id": pid})
    # Money invested = sum of intervention amounts if any
    money = 0
    async for b in db.bookings.find({"client_id": user["user_id"], "property_id": pid}, {"_id": 0, "amount": 1}):
        try:
            money += float(b.get("amount") or 0)
        except Exception:
            pass
    # Realistic demo values when empty so the UI feels alive from day 1
    if equipment_count == 0 and interventions == 0 and money == 0:
        demo = True
        money = 3240
        interventions = 6
    else:
        demo = False
    health = 100 if equipment_count == 0 else int(round((ok_count / max(equipment_count, 1)) * 100))
    return {
        "equipment_count": equipment_count,
        "equipment_ok": ok_count,
        "equipment_attention": attention_count,
        "document_count": document_count,
        "upcoming_maintenance": upcoming,
        "interventions": interventions,
        "money_invested": money,
        "average_health": health,
        "demo_values": demo,
    }

# ----- AI Cards (Coming Soon placeholders) -----
@api_router.get("/properties/{pid}/ai-cards")
async def property_ai_cards(pid: str, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    cards = [
        {"key": "equipment_health", "title": "Santé des équipements", "subtitle": "IA analysera l'état et la longévité de vos équipements.", "icon": "pulse"},
        {"key": "maintenance_prediction", "title": "Maintenance prédictive", "subtitle": "L'IA anticipera les entretiens critiques avant les pannes.", "icon": "calendar"},
        {"key": "risk_detection", "title": "Détection de risques", "subtitle": "Identifiera les risques (fuite, incendie, humidité) automatiquement.", "icon": "shield-checkmark"},
        {"key": "energy_optimization", "title": "Optimisation énergétique", "subtitle": "Recommandations pour baisser vos factures et l'empreinte carbone.", "icon": "flash"},
        {"key": "warranty_expiration", "title": "Expiration garanties", "subtitle": "Vous préviendra avant chaque fin de garantie.", "icon": "ribbon"},
        {"key": "recommended_inspection", "title": "Inspection recommandée", "subtitle": "Suggérera les diagnostics à réaliser selon votre bien.", "icon": "sparkles"},
    ]
    return [{**c, "status": "coming_soon"} for c in cards]


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


@api_router.post("/interventions/{iv_id}/deposit/create")
async def create_deposit_intent(iv_id: str, data: DepositIntentInput, user=Depends(get_current_user)):
    iv = await db.interventions.find_one({"intervention_id": iv_id})
    if not iv:
        raise HTTPException(status_code=404, detail="Intervention introuvable")
    if iv.get("client_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Réservé au client")
    if iv.get("status") not in ("accepted",):
        raise HTTPException(status_code=400, detail="L'artisan doit d'abord accepter la demande")
    if iv.get("deposit_status") == "paid":
        return {"already_paid": True, "amount_cents": iv.get("deposit_amount_cents")}

    amount_cents = _compute_deposit_cents(iv)
    pi = payments.create_payment_intent(
        amount_cents=amount_cents,
        currency="eur",
        metadata={"intervention_id": iv_id, "client_id": user["user_id"], "artisan_id": iv.get("artisan_id", "")},
        customer_email=user.get("email"),
    )
    await db.interventions.update_one(
        {"intervention_id": iv_id},
        {"$set": {
            "deposit_status": "pending",
            "deposit_amount_cents": amount_cents,
            "deposit_currency": "eur",
            "deposit_payment_intent_id": pi["id"],
            "deposit_created_at": now_utc().isoformat(),
        }},
    )
    await security.audit_log(
        db, action="intervention.deposit_created",
        actor_id=user["user_id"], actor_role=user.get("role"),
        target=iv_id, metadata={"amount_cents": amount_cents}, severity="info",
    )
    return {
        "client_secret": pi.get("client_secret"),
        "payment_intent_id": pi["id"],
        "amount_cents": amount_cents,
        "currency": "eur",
        "mock": pi.get("client_secret", "").endswith("_secret_mock"),
    }


@api_router.post("/interventions/{iv_id}/deposit/confirm")
async def confirm_deposit(iv_id: str, data: DepositConfirmInput, user=Depends(get_current_user)):
    """Frontend calls this after Stripe Payment Sheet returns success.
    In mock mode, this is called directly since the fake PI never confirms via webhook.
    """
    iv = await db.interventions.find_one({"intervention_id": iv_id})
    if not iv:
        raise HTTPException(status_code=404, detail="Intervention introuvable")
    if iv.get("client_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Réservé au client")
    if iv.get("deposit_status") == "paid":
        return {"ok": True, "already_paid": True}

    await db.interventions.update_one(
        {"intervention_id": iv_id},
        {"$set": {
            "deposit_status": "paid",
            "deposit_paid_at": now_utc().isoformat(),
            "status": "confirmed",
            "escrow_deposit_state": "held",
        }},
    )
    await security.audit_log(
        db, action="intervention.deposit_paid",
        actor_id=user["user_id"], actor_role=user.get("role"),
        target=iv_id, metadata={"amount_cents": iv.get("deposit_amount_cents")}, severity="critical",
    )
    return {"ok": True, "status": "confirmed"}


# ---------- Intervention lifecycle & final payment (Stripe Connect flow) ----------
class InterventionFinalInput(BaseModel):
    total_amount_cents: int


@api_router.post("/interventions/{iv_id}/start")
async def start_intervention(iv_id: str, user=Depends(get_current_user)):
    """Artisan marks intervention as in progress (arrived on site)."""
    iv = await db.interventions.find_one({"intervention_id": iv_id})
    if not iv:
        raise HTTPException(status_code=404, detail="Introuvable")
    if iv.get("artisan_user_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Réservé à l'artisan")
    if iv.get("status") != "confirmed":
        raise HTTPException(status_code=400, detail="Le paiement d'acompte doit être effectué avant")
    await db.interventions.update_one(
        {"intervention_id": iv_id},
        {"$set": {"status": "in_progress", "started_at": now_utc().isoformat()}},
    )
    await security.audit_log(db, action="intervention.started", actor_id=user["user_id"], target=iv_id, severity="info")
    return {"ok": True, "status": "in_progress"}


@api_router.post("/interventions/{iv_id}/finish")
async def finish_intervention(iv_id: str, data: InterventionFinalInput, user=Depends(get_current_user)):
    """Artisan marks intervention as finished with the final total amount.
    Client will then be prompted to pay the balance (final - deposit).
    """
    iv = await db.interventions.find_one({"intervention_id": iv_id})
    if not iv:
        raise HTTPException(status_code=404, detail="Introuvable")
    if iv.get("artisan_user_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Réservé à l'artisan")
    if iv.get("status") not in ("in_progress", "confirmed"):
        raise HTTPException(status_code=400, detail="État invalide")
    deposit = iv.get("deposit_amount_cents", 0)
    if data.total_amount_cents < deposit:
        raise HTTPException(status_code=400, detail="Le total doit couvrir au moins l'acompte")
    balance = data.total_amount_cents - deposit
    await db.interventions.update_one(
        {"intervention_id": iv_id},
        {"$set": {
            "status": "awaiting_final_payment" if balance > 0 else "awaiting_validation",
            "total_amount_cents": data.total_amount_cents,
            "balance_cents": balance,
            "finished_at": now_utc().isoformat(),
        }},
    )
    await security.audit_log(
        db, action="intervention.finished",
        actor_id=user["user_id"], target=iv_id,
        metadata={"total_cents": data.total_amount_cents, "balance_cents": balance}, severity="info",
    )
    return {"ok": True, "total_cents": data.total_amount_cents, "balance_cents": balance}


@api_router.post("/interventions/{iv_id}/final/create")
async def create_final_payment(iv_id: str, user=Depends(get_current_user)):
    """Create a PaymentIntent for the balance (total - deposit)."""
    iv = await db.interventions.find_one({"intervention_id": iv_id})
    if not iv:
        raise HTTPException(status_code=404, detail="Introuvable")
    if iv.get("client_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Réservé au client")
    if iv.get("status") != "awaiting_final_payment":
        raise HTTPException(status_code=400, detail="État invalide")
    balance = iv.get("balance_cents", 0)
    if balance <= 0:
        return {"already_paid": True}
    pi = payments.create_payment_intent(
        amount_cents=balance,
        currency="eur",
        metadata={"intervention_id": iv_id, "type": "final", "artisan_id": iv.get("artisan_id", "")},
        customer_email=user.get("email"),
    )
    await db.interventions.update_one(
        {"intervention_id": iv_id},
        {"$set": {"final_payment_intent_id": pi["id"], "final_status": "pending"}},
    )
    return {
        "client_secret": pi.get("client_secret"),
        "payment_intent_id": pi["id"],
        "amount_cents": balance,
        "currency": "eur",
        "mock": pi.get("client_secret", "").endswith("_secret_mock"),
    }


@api_router.post("/interventions/{iv_id}/final/confirm")
async def confirm_final_payment(iv_id: str, user=Depends(get_current_user)):
    iv = await db.interventions.find_one({"intervention_id": iv_id})
    if not iv:
        raise HTTPException(status_code=404, detail="Introuvable")
    if iv.get("client_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Réservé au client")
    await db.interventions.update_one(
        {"intervention_id": iv_id},
        {"$set": {
            "final_status": "paid",
            "final_paid_at": now_utc().isoformat(),
            "status": "awaiting_validation",
        }},
    )
    await security.audit_log(
        db, action="intervention.final_paid",
        actor_id=user["user_id"], target=iv_id,
        metadata={"amount_cents": iv.get("balance_cents")}, severity="critical",
    )
    return {"ok": True, "status": "awaiting_validation"}


@api_router.post("/interventions/{iv_id}/validate")
async def validate_intervention(iv_id: str, user=Depends(get_current_user)):
    """Client validates the completed work → escrow is released to artisan via Stripe Connect Transfer."""
    iv = await db.interventions.find_one({"intervention_id": iv_id})
    if not iv:
        raise HTTPException(status_code=404, detail="Introuvable")
    if iv.get("client_id") != user["user_id"]:
        raise HTTPException(status_code=403, detail="Réservé au client")
    if iv.get("status") not in ("awaiting_validation", "awaiting_final_payment"):
        raise HTTPException(status_code=400, detail="État invalide")

    artisan_profile = await db.artisan_profiles.find_one({"artisan_id": iv.get("artisan_id")}, {"_id": 0}) or {}
    connected = await db.stripe_accounts.find_one({"artisan_id": iv.get("artisan_id")}, {"_id": 0})
    total = iv.get("total_amount_cents") or iv.get("deposit_amount_cents") or 0

    result: Dict[str, Any] = {"ok": True, "status": "completed", "total_cents": total}

    if connected and total > 0:
        bps = await payments.resolve_commission_bps(db, artisan_profile)
        fee = payments.commission_amount(total, bps)
        net = total - fee
        transfer = payments.create_transfer(
            amount_cents=net,
            currency="eur",
            destination=connected["stripe_account_id"],
            transfer_group=iv_id,
            metadata={"intervention_id": iv_id, "artisan_id": iv.get("artisan_id", "")},
        )
        await db.transfers.insert_one({
            "transfer_id": new_id("tr"),
            "stripe_transfer_id": transfer["id"],
            "intervention_id": iv_id,
            "artisan_id": iv.get("artisan_id"),
            "gross_cents": total,
            "commission_bps": bps,
            "commission_cents": fee,
            "net_cents": net,
            "created_at": now_utc().isoformat(),
        })
        result.update({"commission_cents": fee, "net_cents": net, "transfer_id": transfer["id"], "commission_bps": bps})
    else:
        result.update({"note": "Aucun transfert Stripe Connect (artisan non connecté ou montant nul)"})

    await db.interventions.update_one(
        {"intervention_id": iv_id},
        {"$set": {
            "status": "completed",
            "completed_at": now_utc().isoformat(),
            "escrow_deposit_state": "released",
            **({"commission_cents": result.get("commission_cents"), "net_paid_cents": result.get("net_cents")} if "net_cents" in result else {}),
        }},
    )
    await security.audit_log(
        db, action="intervention.validated_and_transferred",
        actor_id=user["user_id"], target=iv_id,
        metadata={k: v for k, v in result.items() if k != "ok"}, severity="critical",
    )
    return result


@api_router.get("/interventions/{iv_id}/payment-summary")
async def intervention_payment_summary(iv_id: str, user=Depends(get_current_user)):
    iv = await db.interventions.find_one({"intervention_id": iv_id}, {"_id": 0})
    if not iv:
        raise HTTPException(status_code=404, detail="Introuvable")
    if user["user_id"] not in (iv.get("client_id"), iv.get("artisan_user_id")):
        raise HTTPException(status_code=403, detail="Accès refusé")
    deposit = iv.get("deposit_amount_cents", 0)
    total = iv.get("total_amount_cents", 0)
    balance = iv.get("balance_cents", 0)
    return {
        "deposit_cents": deposit,
        "total_cents": total,
        "balance_cents": balance,
        "deposit_status": iv.get("deposit_status"),
        "final_status": iv.get("final_status"),
        "status": iv.get("status"),
        "commission_cents": iv.get("commission_cents"),
        "net_paid_cents": iv.get("net_paid_cents"),
    }


    event_date: str = Field(..., description="ISO date YYYY-MM-DD")


class PropertyEventInput(BaseModel):
    event_type: str = Field(..., description="installation|entretien|reparation|controle|nettoyage|sinistre|autre")
    title: str = Field(..., min_length=1, max_length=140)
    description: Optional[str] = None
    artisan_name: Optional[str] = None
    cost_cents: Optional[int] = None
    event_date: str = Field(..., description="ISO date YYYY-MM-DD")


@api_router.get("/properties/{pid}/events")
async def list_property_events(pid: str, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    rows = await db.property_events.find({"property_id": pid}, {"_id": 0}).sort("event_date", -1).to_list(500)
    return {"items": rows, "count": len(rows)}


@api_router.post("/properties/{pid}/events")
async def create_property_event(pid: str, body: PropertyEventInput, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    if body.event_type not in homes_svc.EVENT_TYPES:
        raise HTTPException(status_code=400, detail="Type d'événement invalide")
    ev = {
        "event_id": homes_svc.new_id("evt"),
        "property_id": pid,
        "user_id": user["user_id"],
        "event_type": body.event_type,
        "title": body.title.strip(),
        "description": body.description,
        "artisan_name": body.artisan_name,
        "cost_cents": body.cost_cents,
        "event_date": body.event_date,
        "created_at": now_utc().isoformat(),
    }
    await db.property_events.insert_one(dict(ev))
    return ev


@api_router.delete("/properties/{pid}/events/{event_id}")
async def delete_property_event(pid: str, event_id: str, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    r = await db.property_events.delete_one({"event_id": event_id, "property_id": pid})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Événement introuvable")
    return {"ok": True}


@api_router.post("/properties/{pid}/equipment/{eid}/auto-reminders")
async def generate_equipment_reminders(pid: str, eid: str, user=Depends(get_current_user)):
    """Idempotent: (re)generate maintenance + warranty reminders for an equipment.
    Called automatically after equipment creation, but exposed to the client to
    let users re-trigger it if they update dates on an existing equipment.
    """
    await _get_property(pid, user["user_id"])
    eq = await db.property_equipment.find_one({"equipment_id": eid, "property_id": pid}, {"_id": 0})
    if not eq:
        raise HTTPException(status_code=404, detail="Équipement introuvable")
    # Normalize equipment for homes_svc helper (it expects a slightly different shape)
    eq_for_svc = {
        "equipment_id": eq["equipment_id"],
        "property_id": eq["property_id"],
        "user_id": eq["user_id"],
        "category": eq.get("category", "autre"),
        "installed_at": eq.get("installed_on"),
        "last_maintenance_at": eq.get("last_maintenance_at"),
        "warranty_until": eq.get("warranty_until"),
    }
    reminders = await homes_svc.generate_reminders_for_equipment(db, eq_for_svc)
    return {"reminders_created": len(reminders), "reminders": reminders}


@api_router.get("/properties/{pid}/budget")
async def property_budget(pid: str, user=Depends(get_current_user)):
    """Return aggregated budget stats (total, by month, by type, top artisans).
    Sources:
      - `property_events` collection (manual entries with cost_cents)
      - `bookings` collection (interventions attached to this property)
    """
    await _get_property(pid, user["user_id"])

    events = await db.property_events.find(
        {"property_id": pid, "cost_cents": {"$ne": None}}, {"_id": 0}
    ).to_list(1000)

    # Also pull bookings that had a completed payment
    async for b in db.bookings.find(
        {"client_id": user["user_id"], "property_id": pid, "status": {"$in": ["completed", "in_progress"]}},
        {"_id": 0, "amount": 1, "created_at": 1, "trade": 1, "artisan_name": 1},
    ):
        try:
            events.append({
                "event_type": "intervention",
                "event_date": (b.get("created_at") or "")[:10],
                "cost_cents": int(float(b.get("amount") or 0) * 100),
                "artisan_name": b.get("artisan_name"),
            })
        except Exception:
            pass

    total_cents = 0
    by_month: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    by_artisan: Dict[str, int] = {}
    for e in events:
        cents = int(e.get("cost_cents") or 0)
        total_cents += cents
        month_key = str(e.get("event_date", ""))[:7]
        by_month[month_key] = by_month.get(month_key, 0) + cents
        et = e.get("event_type", "autre")
        by_type[et] = by_type.get(et, 0) + cents
        a = e.get("artisan_name")
        if a:
            by_artisan[a] = by_artisan.get(a, 0) + cents

    keys = sorted(by_month.keys())[-12:]
    return {
        "total_cents": total_cents,
        "events_count": len(events),
        "by_month": [{"month": k, "cents": by_month[k]} for k in keys],
        "by_type": [
            {"type": t, "cents": c}
            for t, c in sorted(by_type.items(), key=lambda x: -x[1])
        ],
        "top_artisans": [
            {"name": n, "cents": c}
            for n, c in sorted(by_artisan.items(), key=lambda x: -x[1])[:5]
        ],
    }


@api_router.post("/properties/{pid}/share")
async def enable_property_share(pid: str, user=Depends(get_current_user)):
    """Enable a public read-only passport link for this property."""
    await _get_property(pid, user["user_id"])
    token = uuid.uuid4().hex
    await db.properties.update_one(
        {"property_id": pid},
        {"$set": {"share_token": token, "updated_at": now_utc().isoformat()}},
    )
    platform = os.environ.get("PLATFORM_URL", "https://reviens-app.preview.emergentagent.com")
    await security.audit_log(db, action="property.share_enabled", actor_id=user["user_id"], target=pid, severity="info")
    return {"token": token, "url": f"{platform}/passport/{token}"}


@api_router.delete("/properties/{pid}/share")
async def disable_property_share(pid: str, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    await db.properties.update_one(
        {"property_id": pid},
        {"$set": {"share_token": None, "updated_at": now_utc().isoformat()}},
    )
    await security.audit_log(db, action="property.share_disabled", actor_id=user["user_id"], target=pid, severity="info")
    return {"ok": True}


@api_router.get("/passport/{token}")
async def passport_public(token: str):
    """Public read-only endpoint — no authentication required."""
    prop = await db.properties.find_one({"share_token": token}, {"_id": 0})
    if not prop:
        raise HTTPException(status_code=404, detail="Passeport introuvable ou révoqué")
    eqs = await db.property_equipment.find(
        {"property_id": prop["property_id"]},
        {"_id": 0, "user_id": 0, "serial_number": 0, "notes": 0, "documents": 0},
    ).to_list(200)
    events: List[Dict[str, Any]] = []
    async for e in db.property_events.find(
        {"property_id": prop["property_id"]},
        {"_id": 0, "user_id": 0, "description": 0, "cost_cents": 0},
    ).sort("event_date", -1):
        events.append(e)
    return {
        "property": {
            "name": prop.get("name") or prop.get("label"),
            "property_type": prop.get("type") or prop.get("property_type"),
            "city": prop.get("city"),
            "postal_code": prop.get("postal_code"),
            "address": prop.get("address"),
            "surface": prop.get("surface"),
            "year_built": prop.get("year_built"),
            "rooms": prop.get("rooms"),
            "dpe_grade": prop.get("dpe_grade"),
            "cover_color": prop.get("cover_color") or "#0EA5E9",
            "health_score": prop.get("health_score", 100),
        },
        "equipments": eqs,
        "events": events,
    }


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
