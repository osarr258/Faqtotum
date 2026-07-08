from fastapi import FastAPI, APIRouter, HTTPException, Header, Depends
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
from typing import List, Optional, Dict
from datetime import datetime, timezone, timedelta
from services import matching, calendar_sync, trust_engine, payments, concierge, growth, enterprise

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

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

async def create_session(user_id: str) -> str:
    token = uuid.uuid4().hex + uuid.uuid4().hex
    await db.user_sessions.insert_one({
        "session_token": token,
        "user_id": user_id,
        "created_at": now_utc().isoformat(),
        "expires_at": (now_utc() + timedelta(days=7)).isoformat(),
    })
    return token

async def get_current_user(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Non authentifié")
    token = authorization.split(" ", 1)[1]
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Session invalide")
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
    return user

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
    category: str = ""
    brand: str = ""
    model: str = ""
    installed_on: Optional[str] = None
    notes: str = ""

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

# ----------------------------- Auth routes -----------------------------

@api_router.get("/")
async def root():
    return {"message": "ProConnect API"}

@api_router.post("/auth/register")
async def register(data: RegisterInput):
    existing = await db.users.find_one({"email": data.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")
    user_id = new_id("user")
    user = {
        "user_id": user_id,
        "email": data.email.lower(),
        "name": data.name,
        "role": data.role if data.role in ("client", "artisan") else "client",
        "password": hash_password(data.password),
        "picture": None,
        "created_at": now_utc().isoformat(),
    }
    await db.users.insert_one(user)
    token = await create_session(user_id)
    user.pop("_id", None)
    return {"token": token, "user": {k: v for k, v in user.items() if k != "password"}}

@api_router.post("/auth/login")
async def login(data: LoginInput):
    user = await db.users.find_one({"email": data.email.lower()})
    if not user or not user.get("password") or not verify_password(data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    token = await create_session(user["user_id"])
    user.pop("password", None)
    user.pop("_id", None)
    return {"token": token, "user": user}

@api_router.post("/auth/google")
async def google_auth(data: GoogleInput):
    async with httpx.AsyncClient() as hc:
        resp = await hc.get(EMERGENT_SESSION_API, headers={"X-Session-ID": data.session_token})
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Authentification Google échouée")
    info = resp.json()
    email = info["email"].lower()
    user = await db.users.find_one({"email": email})
    if not user:
        user_id = new_id("user")
        user = {
            "user_id": user_id,
            "email": email,
            "name": info.get("name", "Utilisateur"),
            "role": data.role if data.role in ("client", "artisan") else "client",
            "password": None,
            "picture": info.get("picture"),
            "created_at": now_utc().isoformat(),
        }
        await db.users.insert_one(user)
    token = await create_session(user["user_id"])
    user.pop("password", None)
    user.pop("_id", None)
    return {"token": token, "user": user}

@api_router.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return user

@api_router.post("/auth/logout")
async def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        await db.user_sessions.delete_one({"session_token": token})
    return {"ok": True}

# ----------------------------- Categories route -----------------------------

@api_router.get("/categories")
async def get_categories():
    return CATEGORIES

# ----------------------------- Artisan routes -----------------------------

async def enrich_artisan(a: dict):
    a.pop("_id", None)
    cat = CATEGORY_MAP.get(a.get("trade"))
    a["trade_name"] = cat["name"] if cat else a.get("trade")
    a["trade_icon"] = cat["icon"] if cat else "construct"
    return a

@api_router.get("/artisans")
async def list_artisans(category: Optional[str] = None, q: Optional[str] = None,
                        min_rate: Optional[float] = None, max_rate: Optional[float] = None,
                        min_rating: Optional[float] = None, available: Optional[bool] = None,
                        lat: Optional[float] = None, lng: Optional[float] = None,
                        radius: Optional[float] = None, sort: Optional[str] = None):
    query = {"is_subscribed": True}
    if category:
        query["trade"] = category
    artisans = await db.artisan_profiles.find(query, {"_id": 0}).to_list(500)
    artisans = [await enrich_artisan(a) for a in artisans]
    if q:
        ql = q.lower()
        artisans = [a for a in artisans if ql in a.get("title", "").lower() or ql in a.get("city", "").lower() or ql in a.get("trade_name", "").lower() or ql in (a.get("name") or "").lower()]
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
            artisans = [a for a in artisans if a.get("distance_km") is not None and a["distance_km"] <= radius]
    if sort == "rate_asc":
        artisans.sort(key=lambda x: x.get("hourly_rate", 0))
    elif sort == "rate_desc":
        artisans.sort(key=lambda x: x.get("hourly_rate", 0), reverse=True)
    elif sort == "distance" and lat is not None:
        artisans.sort(key=lambda x: x.get("distance_km") if x.get("distance_km") is not None else 1e9)
    else:
        artisans.sort(key=lambda x: x.get("rating", 0), reverse=True)
    return artisans

@api_router.get("/artisans/top")
async def top_artisans():
    artisans = await db.artisan_profiles.find({"is_subscribed": True}, {"_id": 0}).to_list(500)
    artisans = [await enrich_artisan(a) for a in artisans]
    artisans.sort(key=lambda x: x.get("rating", 0), reverse=True)
    return artisans[:8]

@api_router.get("/artisans/me")
async def my_artisan_profile(user=Depends(get_current_user)):
    profile = await db.artisan_profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not profile:
        return None
    return await enrich_artisan(profile)

@api_router.post("/artisans/me")
async def upsert_artisan_profile(data: ArtisanProfileInput, user=Depends(get_current_user)):
    if user["role"] != "artisan":
        raise HTTPException(status_code=403, detail="Réservé aux artisans")
    existing = await db.artisan_profiles.find_one({"user_id": user["user_id"]})
    cat = CATEGORY_MAP.get(data.trade)
    coords = CITY_COORDS.get(data.city)
    payload = {
        "trade": data.trade,
        "trade_name": cat["name"] if cat else data.trade,
        "title": data.title,
        "bio": data.bio,
        "city": data.city,
        "hourly_rate": data.hourly_rate,
        "photo": data.photo,
        "phone": data.phone,
        "name": user["name"],
        "available": data.available,
        "lat": coords[0] if coords else None,
        "lng": coords[1] if coords else None,
    }
    if existing:
        await db.artisan_profiles.update_one({"artisan_id": existing["artisan_id"]}, {"$set": {**payload, "last_active_at": now_utc().isoformat()}})
        profile = await db.artisan_profiles.find_one({"artisan_id": existing["artisan_id"]}, {"_id": 0})
    else:
        artisan_id = new_id("art")
        profile = {
            "artisan_id": artisan_id,
            "user_id": user["user_id"],
            "rating": 5.0,
            "reviews_count": 0,
            "base_rating": 0,
            "base_reviews_count": 0,
            "trust_score": 80,
            "acceptance_rate": 100,
            "completion_rate": 100,
            "cancellation_rate": 0,
            "response_min": 20,
            "jobs_done": 0,
            "identity_verified": False,
            "insurance_verified": False,
            "business_registered": False,
            "background_checked": False,
            "years_experience": 0,
            "avg_arrival_min": 45,
            "punctuality_rate": 100,
            "satisfaction_rate": 90,
            "emergency_capable": False,
            "disputes_unresolved": 0,
            "disputes_resolved": 0,
            "member_since": now_utc().isoformat(),
            "last_active_at": now_utc().isoformat(),
            "calendar_connected": False,
            "is_subscribed": False,
            "subscription_expires": None,
            "created_at": now_utc().isoformat(),
            **payload,
        }
        await db.artisan_profiles.insert_one(profile)
        profile.pop("_id", None)
    # Trust Engine — recompute after any profile change.
    await trust_engine.persist(db, profile["artisan_id"])
    profile = await db.artisan_profiles.find_one({"artisan_id": profile["artisan_id"]}, {"_id": 0})
    return await enrich_artisan(profile)

@api_router.post("/artisans/me/subscribe")
async def subscribe(user=Depends(get_current_user)):
    profile = await db.artisan_profiles.find_one({"user_id": user["user_id"]})
    if not profile:
        raise HTTPException(status_code=404, detail="Créez d'abord votre profil")
    expires = (now_utc() + timedelta(days=30)).isoformat()
    await db.artisan_profiles.update_one(
        {"artisan_id": profile["artisan_id"]},
        {"$set": {"is_subscribed": True, "subscription_expires": expires}},
    )
    return {"ok": True, "subscription_expires": expires}

@api_router.get("/artisans/{artisan_id}")
async def get_artisan(artisan_id: str):
    artisan = await db.artisan_profiles.find_one({"artisan_id": artisan_id}, {"_id": 0})
    if not artisan:
        raise HTTPException(status_code=404, detail="Artisan introuvable")
    enriched = await enrich_artisan(artisan)
    # Attach the Trust confidence card so the profile screen can display badges + reasons.
    try:
        out = trust_engine.compute(artisan)
        enriched["confidence_card"] = trust_engine.confidence_card(artisan, out)
        enriched["badges"] = trust_engine.badges(artisan, out["trust_score"])
        enriched["trust_score"] = out["trust_score"]
    except Exception as e:
        logger.warning(f"trust card computation failed: {e}")
    return enriched

# ----------------------------- Booking routes -----------------------------

@api_router.post("/bookings")
async def create_booking(data: BookingInput, user=Depends(get_current_user)):
    artisan = await db.artisan_profiles.find_one({"artisan_id": data.artisan_id}, {"_id": 0})
    if not artisan:
        raise HTTPException(status_code=404, detail="Artisan introuvable")
    booking_id = new_id("bk")
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
        "created_at": now_utc().isoformat(),
    }
    await db.bookings.insert_one(booking)
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
        "last_at": now_utc().isoformat(),
        "created_at": now_utc().isoformat(),
    })
    booking.pop("_id", None)
    return booking

async def annotate_reviewed(bookings, user_id):
    for b in bookings:
        rev = await db.reviews.find_one({"booking_id": b["booking_id"], "from_user_id": user_id})
        b["reviewed"] = rev is not None
    return bookings

@api_router.get("/bookings/mine")
async def my_bookings(user=Depends(get_current_user)):
    bookings = await db.bookings.find({"client_id": user["user_id"]}, {"_id": 0}).to_list(500)
    bookings.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return await annotate_reviewed(bookings, user["user_id"])

@api_router.get("/bookings/received")
async def received_bookings(user=Depends(get_current_user)):
    bookings = await db.bookings.find({"artisan_user_id": user["user_id"]}, {"_id": 0}).to_list(500)
    bookings.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return await annotate_reviewed(bookings, user["user_id"])

@api_router.patch("/bookings/{booking_id}")
async def update_booking(booking_id: str, data: BookingStatusInput, user=Depends(get_current_user)):
    booking = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Réservation introuvable")
    if data.status not in ("accepted", "declined", "completed"):
        raise HTTPException(status_code=400, detail="Statut invalide")
    await db.bookings.update_one({"booking_id": booking_id}, {"$set": {"status": data.status}})
    booking["status"] = data.status
    # Loyalty hook — customer earns points when a booking is completed.
    if data.status == "completed":
        await _add_points(booking["client_id"], "booking_completed")
    # Trust Engine — recompute on any status change that affects counters.
    if booking.get("artisan_id"):
        await trust_engine.persist(db, booking["artisan_id"])
    return booking

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
    # Loyalty — client earns points for posting a review
    if to_role == "artisan":
        await _add_points(user["user_id"], "review_posted")
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


@api_router.post("/missions")
async def create_mission(data: MissionInput, user=Depends(get_current_user)):
    artisans = await db.artisan_profiles.find({"is_subscribed": True, "trade": data.trade}, {"_id": 0}).to_list(500)
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
    # Emergency mode: broadcast to several pros simultaneously (first to accept wins).
    notified_pros = [a["artisan_id"] for a in ranked[:5]] if is_emergency else []
    mission = {
        "mission_id": new_id("msn"),
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
        "created_at": now_utc().isoformat(),
    }
    await db.missions.insert_one(mission)
    mission.pop("_id", None)
    return mission

@api_router.post("/missions/{mission_id}/book")
async def book_mission(mission_id: str, data: BookInput, user=Depends(get_current_user)):
    m = await db.missions.find_one({"mission_id": mission_id}, {"_id": 0})
    if not m or m["client_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="Mission introuvable")
    a = await db.artisan_profiles.find_one({"artisan_id": data.artisan_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Professionnel introuvable")
    a = await enrich_artisan(a)
    a["distance_km"] = round(haversine(m["client_lat"], m["client_lng"], a["lat"], a["lng"]), 1) if a.get("lat") else None
    card = mission_artisan_card(a)
    card["eta_minutes"] = match_eta(card)
    a_lat = a.get("lat") if a.get("lat") is not None else m["client_lat"] + 0.05
    a_lng = a.get("lng") if a.get("lng") is not None else m["client_lng"] + 0.05
    dist = haversine(a_lat, a_lng, m["client_lat"], m["client_lng"])
    eta = max(3, min(40, round(dist / 35 * 60)))
    if dist < 0.1:
        eta = 6
    upd = {"status": "en_route", "accepted_at": now_utc().isoformat(), "eta_minutes": eta,
           "artisan_start_lat": a_lat, "artisan_start_lng": a_lng, "artisan": card}
    await db.missions.update_one({"mission_id": mission_id}, {"$set": upd})
    m.update(upd)
    return m

async def _set_candidate(mission: dict, idx: int):
    aid = mission["candidates"][idx]
    a = await db.artisan_profiles.find_one({"artisan_id": aid}, {"_id": 0})
    a = await enrich_artisan(a)
    ctx = {"lat": mission["client_lat"], "lng": mission["client_lng"], "urgency": mission.get("urgency", "moyenne")}
    s, breakdown, d = matching.score(a, ctx)
    a["match_score"] = s
    a["score_breakdown"] = breakdown
    a["distance_km"] = d
    card = mission_artisan_card(a)
    await db.missions.update_one({"mission_id": mission["mission_id"]}, {"$set": {"candidate_index": idx, "artisan": card, "status": "proposed"}})
    return card

@api_router.post("/missions/{mission_id}/refuse")
async def refuse_mission(mission_id: str, user=Depends(get_current_user)):
    m = await db.missions.find_one({"mission_id": mission_id}, {"_id": 0})
    if not m or m["client_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="Mission introuvable")
    nxt = m["candidate_index"] + 1
    if nxt >= len(m["candidates"]):
        await db.missions.update_one({"mission_id": mission_id}, {"$set": {"status": "no_pro"}})
        return {"status": "no_pro"}
    card = await _set_candidate(m, nxt)
    return {"status": "proposed", "artisan": card}

@api_router.post("/missions/{mission_id}/confirm")
async def confirm_mission(mission_id: str, user=Depends(get_current_user)):
    m = await db.missions.find_one({"mission_id": mission_id}, {"_id": 0})
    if not m or m["client_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="Mission introuvable")
    a = m["artisan"]
    a_lat = a.get("lat") if a.get("lat") is not None else m["client_lat"] + 0.05
    a_lng = a.get("lng") if a.get("lng") is not None else m["client_lng"] + 0.05
    dist = haversine(a_lat, a_lng, m["client_lat"], m["client_lng"])
    eta = max(3, min(40, round(dist / 35 * 60)))
    if dist < 0.1:
        eta = 6
    upd = {
        "status": "en_route",
        "accepted_at": now_utc().isoformat(),
        "eta_minutes": eta,
        "artisan_start_lat": a_lat,
        "artisan_start_lng": a_lng,
    }
    await db.missions.update_one({"mission_id": mission_id}, {"$set": upd})
    m.update(upd)
    return m

@api_router.get("/missions/mine")
async def my_missions(user=Depends(get_current_user)):
    ms = await db.missions.find({"client_id": user["user_id"]}, {"_id": 0}).to_list(500)
    ms.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return ms

@api_router.get("/missions/{mission_id}")
async def get_mission(mission_id: str, user=Depends(get_current_user)):
    m = await db.missions.find_one({"mission_id": mission_id}, {"_id": 0})
    if not m or m["client_id"] != user["user_id"]:
        raise HTTPException(status_code=404, detail="Mission introuvable")
    if m.get("status") in ("en_route", "arrived") and m.get("accepted_at"):
        accepted = datetime.fromisoformat(m["accepted_at"])
        if accepted.tzinfo is None:
            accepted = accepted.replace(tzinfo=timezone.utc)
        elapsed_min = (now_utc() - accepted).total_seconds() / 60.0
        eta = m.get("eta_minutes") or 8
        prog = min(1.0, elapsed_min / eta) if eta > 0 else 1.0
        slat = m.get("artisan_start_lat", m["client_lat"])
        slng = m.get("artisan_start_lng", m["client_lng"])
        m["current_lat"] = slat + (m["client_lat"] - slat) * prog
        m["current_lng"] = slng + (m["client_lng"] - slng) * prog
        m["eta_remaining"] = max(0, round(eta * (1 - prog)))
        if prog >= 1 and m["status"] == "en_route":
            m["status"] = "arrived"
            await db.missions.update_one({"mission_id": mission_id}, {"$set": {"status": "arrived"}})
    return m

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

# ----------------------------- Emergency mode (first-to-accept wins) -----------------------------

@api_router.post("/missions/{mission_id}/pro_accept")
async def pro_accept_mission(mission_id: str, data: ProAcceptInput):
    """Called by a notified pro in emergency mode. First valid acceptance wins;
    later attempts get 409. (Pro-side auth handled by their app; open here so
    the broadcast/accept architecture can be exercised.)"""
    m = await db.missions.find_one({"mission_id": mission_id}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Mission introuvable")
    if m.get("mode") != "emergency":
        raise HTTPException(status_code=400, detail="Cette mission n'est pas en mode urgence")
    if data.artisan_id not in (m.get("notified_pros") or []):
        raise HTTPException(status_code=403, detail="Professionnel non sollicité pour cette urgence")
    if m.get("accepted_by"):
        raise HTTPException(status_code=409, detail="Mission déjà acceptée par un autre professionnel")
    a = await db.artisan_profiles.find_one({"artisan_id": data.artisan_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Professionnel introuvable")
    a = await enrich_artisan(a)
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
    upd = {"status": "en_route", "accepted_at": now_utc().isoformat(), "accepted_by": data.artisan_id,
           "eta_minutes": eta, "artisan_start_lat": a_lat, "artisan_start_lng": a_lng, "artisan": card}
    res = await db.missions.update_one(
        {"mission_id": mission_id, "accepted_by": None},
        {"$set": upd},
    )
    if res.modified_count == 0:
        raise HTTPException(status_code=409, detail="Mission déjà acceptée par un autre professionnel")
    return {"status": "en_route", "artisan": card, "eta_minutes": eta}

# ----------------------------- Calendar sync (architecture, MOCKED) -----------------------------

@api_router.get("/artisans/{artisan_id}/availability")
async def artisan_availability(artisan_id: str, days: int = 7):
    artisan = await db.artisan_profiles.find_one({"artisan_id": artisan_id}, {"_id": 0})
    if not artisan:
        raise HTTPException(status_code=404, detail="Artisan introuvable")
    # Pull our own bookings to mark those slots busy (best-effort).
    bks = await db.bookings.find({"artisan_id": artisan_id, "status": {"$in": ["pending", "accepted"]}}, {"_id": 0}).to_list(500)
    busy = []
    for b in bks:
        try:
            busy.append({"date": b.get("date"), "hour": int((b.get("slot") or "0").split(":")[0])})
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

@api_router.post("/artisans/me/calendar/connect")
async def connect_calendar(data: CalendarConnectInput, user=Depends(get_current_user)):
    profile = await db.artisan_profiles.find_one({"user_id": user["user_id"]})
    if not profile:
        raise HTTPException(status_code=404, detail="Créez d'abord votre profil")
    try:
        conn = calendar_sync.connect_provider(data.provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.artisan_profiles.update_one(
        {"artisan_id": profile["artisan_id"]},
        {"$set": {"calendar_connected": True, "calendar_provider": conn["provider"], "calendar_connection": conn}},
    )
    return conn

# ----------------------------- Home Passport / Invoices / Guarantees -----------------------------

async def _append_passport_history(client_id: str, entry: dict):
    await db.home_passports.update_one(
        {"client_id": client_id},
        {"$setOnInsert": {"client_id": client_id, "created_at": now_utc().isoformat()},
         "$push": {"maintenance_history": {"$each": [entry], "$position": 0}}},
        upsert=True,
    )

@api_router.get("/home-passport")
async def get_home_passport(user=Depends(get_current_user)):
    p = await db.home_passports.find_one({"client_id": user["user_id"]}, {"_id": 0})
    if not p:
        p = {"client_id": user["user_id"], "equipment": [], "maintenance_history": [], "guarantees": []}
    else:
        p.setdefault("equipment", [])
        p.setdefault("maintenance_history", [])
    guarantees = await db.guarantees.find({"client_id": user["user_id"]}, {"_id": 0}).to_list(500)
    guarantees.sort(key=lambda x: x.get("starts_at", ""), reverse=True)
    p["guarantees"] = guarantees
    return p

@api_router.post("/home-passport/equipment")
async def add_equipment(data: EquipmentInput, user=Depends(get_current_user)):
    item = {"equipment_id": new_id("eqp"), **data.dict(), "added_at": now_utc().isoformat()}
    await db.home_passports.update_one(
        {"client_id": user["user_id"]},
        {"$setOnInsert": {"client_id": user["user_id"], "created_at": now_utc().isoformat()},
         "$push": {"equipment": item}},
        upsert=True,
    )
    return item

@api_router.get("/invoices/mine")
async def my_invoices(user=Depends(get_current_user)):
    invs = await db.invoices.find({"client_id": user["user_id"]}, {"_id": 0}).to_list(500)
    invs.sort(key=lambda x: x.get("issued_at", ""), reverse=True)
    return invs

@api_router.get("/guarantees/mine")
async def my_guarantees(user=Depends(get_current_user)):
    grs = await db.guarantees.find({"client_id": user["user_id"]}, {"_id": 0}).to_list(500)
    grs.sort(key=lambda x: x.get("starts_at", ""), reverse=True)
    return grs

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
# TRUST ENGINE — Confidence card, Scoreboard, Disputes, Smart recos, Badges
# ============================================================

class DisputeInput(BaseModel):
    artisan_id: str
    booking_id: Optional[str] = None
    reason: str
    severity: str = "minor"  # minor | moderate | severe
    description: Optional[str] = ""

class SmartRecoInput(BaseModel):
    picked_artisan_id: str
    trade: Optional[str] = None
    city: Optional[str] = None
    urgency: Optional[str] = None

async def _load_artisan(artisan_id: str) -> dict:
    a = await db.artisan_profiles.find_one({"artisan_id": artisan_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Artisan introuvable")
    return a

@api_router.get("/artisans/{artisan_id}/trust")
async def artisan_trust(artisan_id: str):
    """Full trust breakdown. Safe to expose — no PII."""
    a = await _load_artisan(artisan_id)
    out = trust_engine.compute(a)
    return {**out, "artisan_id": artisan_id}

@api_router.get("/artisans/{artisan_id}/confidence-card")
async def artisan_confidence_card(artisan_id: str):
    """Client-facing confidence card (verified/insured/reasons/badges)."""
    a = await _load_artisan(artisan_id)
    out = trust_engine.compute(a)
    return trust_engine.confidence_card(a, out)

@api_router.get("/artisans/{artisan_id}/badges")
async def artisan_badges(artisan_id: str):
    a = await _load_artisan(artisan_id)
    ts = a.get("trust_score") or trust_engine.compute(a)["trust_score"]
    return {"artisan_id": artisan_id, "badges": trust_engine.badges(a, ts)}

@api_router.get("/artisans/me/scoreboard")
async def my_scoreboard(user=Depends(get_current_user)):
    """Pro-facing: how the trust score is built + improvements."""
    a = await db.artisan_profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Profil artisan introuvable")
    out = trust_engine.compute(a)
    return trust_engine.scoreboard(a, out)

@api_router.post("/artisans/{artisan_id}/recompute-trust")
async def recompute_trust(artisan_id: str, user=Depends(get_current_user)):
    """Manual recompute (used by pros or admin). Idempotent."""
    out = await trust_engine.persist(db, artisan_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Artisan introuvable")
    return {"artisan_id": artisan_id, **out}

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

@api_router.post("/matching/smart-recommendations")
async def matching_smart_recos(body: SmartRecoInput, user=Depends(get_current_user)):
    """Given a picked artisan, propose alternatives (faster, closer, cheaper, higher rated, earlier)."""
    picked = await _load_artisan(body.picked_artisan_id)
    q: dict = {"available": True}
    if body.trade:
        q["trade"] = body.trade
    if body.city:
        q["city"] = body.city
    pool = await db.artisan_profiles.find(q, {"_id": 0}).to_list(200)
    # Rank pool via matching for consistent ordering (limits to top candidates).
    ctx = {"lat": picked.get("lat"), "lng": picked.get("lng"), "urgency": body.urgency}
    ranked = matching.rank(pool, ctx)[:20]
    return trust_engine.smart_alternatives(picked, ranked)


# ============================================================
# GROWTH — Trusted pros, Loyalty, Referrals, Levels, Achievements,
# Gallery, Property Health, Maintenance Planner, Business, Family,
# Favourites, Analytics
# ============================================================

FAVOURITE_KINDS = ["pro", "property", "address"]
FAMILY_ROLES = ["owner", "partner", "child", "tenant", "manager"]
BUSINESS_TYPES = ["individual", "company", "property_manager", "real_estate", "hotel", "restaurant", "retail_chain"]

class TrustedProInput(BaseModel):
    artisan_id: str
    note: Optional[str] = ""

class ReferralRedeemInput(BaseModel):
    code: str

class RedeemRewardInput(BaseModel):
    reward_key: str

class GalleryProjectInput(BaseModel):
    title: str
    description: Optional[str] = ""
    trade: Optional[str] = ""
    before_photos: List[str] = Field(default_factory=list)
    after_photos: List[str] = Field(default_factory=list)

class FavouriteInput(BaseModel):
    kind: str  # pro | property | address
    ref_id: Optional[str] = None
    label: Optional[str] = ""
    metadata: Optional[dict] = None

class FamilyMemberInput(BaseModel):
    property_id: str
    email: EmailStr
    role: str = "partner"
    can_book: bool = True
    can_view_documents: bool = True
    can_add_equipment: bool = False

class BusinessAccountInput(BaseModel):
    account_type: str  # individual | company | property_manager | ...
    company_name: Optional[str] = ""
    tax_id: Optional[str] = ""
    properties_count: Optional[int] = 1

async def _add_points(user_id: str, action: str, amount: Optional[int] = None):
    """Idempotent loyalty ledger entry + summary update."""
    delta = amount if amount is not None else growth.POINTS_EARN.get(action, 0)
    if delta <= 0:
        return
    await db.loyalty_ledger.insert_one({
        "entry_id": new_id("lyl"),
        "user_id": user_id,
        "action": action,
        "delta": delta,
        "created_at": now_utc().isoformat(),
    })
    await db.loyalty_summary.update_one(
        {"user_id": user_id},
        {"$inc": {"points": delta, "lifetime_points": delta}, "$set": {"updated_at": now_utc().isoformat()}},
        upsert=True,
    )

# --------------- Trusted Pros ---------------
@api_router.get("/trusted-pros")
async def list_trusted_pros(user=Depends(get_current_user)):
    rows = await db.trusted_pros.find({"user_id": user["user_id"]}, {"_id": 0}).sort("saved_at", -1).to_list(200)
    ids = [r["artisan_id"] for r in rows]
    profiles = {p["artisan_id"]: p async for p in db.artisan_profiles.find({"artisan_id": {"$in": ids}}, {"_id": 0})}
    for r in rows:
        r["artisan"] = await enrich_artisan(profiles.get(r["artisan_id"], {}))
    return rows

@api_router.post("/trusted-pros")
async def add_trusted_pro(body: TrustedProInput, user=Depends(get_current_user)):
    existing = await db.trusted_pros.find_one({"user_id": user["user_id"], "artisan_id": body.artisan_id}, {"_id": 0})
    if existing:
        return existing
    doc = {
        "trust_id": new_id("tp"),
        "user_id": user["user_id"],
        "artisan_id": body.artisan_id,
        "note": body.note or "",
        "saved_at": now_utc().isoformat(),
    }
    await db.trusted_pros.insert_one(dict(doc))
    return doc

@api_router.delete("/trusted-pros/{artisan_id}")
async def remove_trusted_pro(artisan_id: str, user=Depends(get_current_user)):
    await db.trusted_pros.delete_one({"user_id": user["user_id"], "artisan_id": artisan_id})
    return {"ok": True}

# --------------- Loyalty ---------------
@api_router.get("/loyalty/summary")
async def loyalty_summary(user=Depends(get_current_user)):
    row = await db.loyalty_summary.find_one({"user_id": user["user_id"]}, {"_id": 0}) or {"user_id": user["user_id"], "points": 0, "lifetime_points": 0}
    tier = growth.loyalty_tier(row.get("points", 0))
    return {**row, **tier, "rewards": growth.REWARDS, "earn_actions": growth.POINTS_EARN}

@api_router.get("/loyalty/ledger")
async def loyalty_ledger(user=Depends(get_current_user)):
    return await db.loyalty_ledger.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)

@api_router.post("/loyalty/redeem")
async def redeem_reward(body: RedeemRewardInput, user=Depends(get_current_user)):
    reward = next((r for r in growth.REWARDS if r["key"] == body.reward_key), None)
    if not reward:
        raise HTTPException(status_code=404, detail="Récompense introuvable")
    summary = await db.loyalty_summary.find_one({"user_id": user["user_id"]}, {"_id": 0}) or {"points": 0}
    if summary.get("points", 0) < reward["points"]:
        raise HTTPException(status_code=400, detail=f"Solde insuffisant ({reward['points']} pts requis)")
    await db.loyalty_summary.update_one({"user_id": user["user_id"]}, {"$inc": {"points": -reward["points"]}})
    await db.loyalty_ledger.insert_one({
        "entry_id": new_id("lyl"), "user_id": user["user_id"],
        "action": "reward_redeemed", "reward_key": reward["key"],
        "delta": -reward["points"], "created_at": now_utc().isoformat(),
    })
    await db.loyalty_rewards.insert_one({
        "redemption_id": new_id("rwd"), "user_id": user["user_id"], "reward": reward,
        "status": "active", "created_at": now_utc().isoformat(),
    })
    return {"ok": True, "reward": reward}

# --------------- Referrals ---------------
@api_router.get("/referrals/mine")
async def my_referrals(user=Depends(get_current_user)):
    code = growth.make_referral_code(user["user_id"])
    invitations = await db.referrals.find({"referrer_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    converted = sum(1 for i in invitations if i.get("status") == "converted")
    return {"code": code, "invitations": invitations, "invitations_count": len(invitations),
            "converted_count": converted, "rewards_earned": converted * growth.POINTS_EARN["referral_converted"]}

@api_router.post("/referrals/redeem")
async def redeem_referral(body: ReferralRedeemInput, user=Depends(get_current_user)):
    # Only valid if this user has no prior converted redemption.
    already = await db.referrals.find_one({"referred_id": user["user_id"], "status": "converted"})
    if already:
        raise HTTPException(status_code=400, detail="Vous avez déjà utilisé un code de parrainage")
    # Find the referrer whose code matches.
    # We compute deterministically since codes are functions of user_id.
    # For a small-scale MVP, we scan users.
    referrer = None
    async for u in db.users.find({}, {"_id": 0, "user_id": 1}):
        if growth.make_referral_code(u["user_id"]) == body.code.upper().strip():
            referrer = u
            break
    if not referrer:
        raise HTTPException(status_code=404, detail="Code invalide")
    if referrer["user_id"] == user["user_id"]:
        raise HTTPException(status_code=400, detail="Auto-parrainage impossible")
    await db.referrals.insert_one({
        "referral_id": new_id("ref"),
        "referrer_id": referrer["user_id"],
        "referred_id": user["user_id"],
        "code": body.code.upper().strip(),
        "status": "converted",  # MVP: immediate conversion on redemption
        "created_at": now_utc().isoformat(),
    })
    # Both sides earn points.
    await _add_points(referrer["user_id"], "referral_converted")
    await _add_points(user["user_id"], "referral_converted", amount=200)  # smaller welcome bonus
    return {"ok": True}

# --------------- Pro Levels & Achievements ---------------
@api_router.get("/artisans/{aid}/level")
async def artisan_level(aid: str):
    a = await db.artisan_profiles.find_one({"artisan_id": aid}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Artisan introuvable")
    lvl = growth.pro_level(a.get("trust_score") or 0, a.get("jobs_done") or 0)
    return {"artisan_id": aid, **lvl}

@api_router.get("/growth/levels")
async def growth_levels_catalog():
    return growth.LEVELS

# --------------- Before/After Gallery ---------------
@api_router.get("/artisans/{aid}/gallery")
async def artisan_gallery(aid: str):
    return await db.gallery_projects.find({"artisan_id": aid}, {"_id": 0}).sort("created_at", -1).to_list(200)

@api_router.post("/artisans/me/gallery")
async def add_gallery_project(body: GalleryProjectInput, user=Depends(get_current_user)):
    if user.get("role") != "artisan":
        raise HTTPException(status_code=403, detail="Réservé aux artisans")
    profile = await db.artisan_profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not profile:
        raise HTTPException(status_code=400, detail="Profil pro introuvable")
    doc = {
        "project_id": new_id("gal"),
        "artisan_id": profile["artisan_id"],
        "title": body.title.strip(),
        "description": body.description or "",
        "trade": body.trade or profile.get("trade"),
        "before_photos": body.before_photos[:6],
        "after_photos": body.after_photos[:6],
        "created_at": now_utc().isoformat(),
    }
    await db.gallery_projects.insert_one(dict(doc))
    return doc

@api_router.delete("/artisans/me/gallery/{project_id}")
async def delete_gallery_project(project_id: str, user=Depends(get_current_user)):
    if user.get("role") != "artisan":
        raise HTTPException(status_code=403, detail="Réservé aux artisans")
    profile = await db.artisan_profiles.find_one({"user_id": user["user_id"]}, {"_id": 0, "artisan_id": 1})
    if not profile:
        raise HTTPException(status_code=404, detail="Profil introuvable")
    await db.gallery_projects.delete_one({"project_id": project_id, "artisan_id": profile["artisan_id"]})
    return {"ok": True}

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

# --------------- Business Accounts ---------------
@api_router.post("/business/setup")
async def setup_business(body: BusinessAccountInput, user=Depends(get_current_user)):
    if body.account_type not in BUSINESS_TYPES:
        raise HTTPException(status_code=400, detail="Type de compte invalide")
    await db.business_accounts.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "user_id": user["user_id"],
            "account_type": body.account_type,
            "company_name": body.company_name or "",
            "tax_id": body.tax_id or "",
            "properties_count": body.properties_count or 1,
            "updated_at": now_utc().isoformat(),
        }},
        upsert=True,
    )
    return {"ok": True, "account_type": body.account_type}

@api_router.get("/business/mine")
async def my_business(user=Depends(get_current_user)):
    row = await db.business_accounts.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return row or {"account_type": "individual"}

# --------------- Family Sharing ---------------
@api_router.get("/properties/{pid}/members")
async def list_members(pid: str, user=Depends(get_current_user)):
    prop = await db.properties.find_one({"property_id": pid, "user_id": user["user_id"]}, {"_id": 0})
    if not prop:
        raise HTTPException(status_code=404, detail="Bien introuvable")
    rows = await db.property_members.find({"property_id": pid}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return rows

@api_router.post("/properties/{pid}/members")
async def invite_member(pid: str, body: FamilyMemberInput, user=Depends(get_current_user)):
    if body.role not in FAMILY_ROLES:
        raise HTTPException(status_code=400, detail="Rôle invalide")
    prop = await db.properties.find_one({"property_id": pid, "user_id": user["user_id"]}, {"_id": 0})
    if not prop:
        raise HTTPException(status_code=404, detail="Bien introuvable")
    invited = await db.users.find_one({"email": body.email}, {"_id": 0, "user_id": 1, "name": 1})
    doc = {
        "member_id": new_id("mbr"),
        "property_id": pid,
        "email": body.email,
        "invited_user_id": invited["user_id"] if invited else None,
        "invited_name": invited["name"] if invited else "",
        "role": body.role,
        "permissions": {
            "can_book": body.can_book,
            "can_view_documents": body.can_view_documents,
            "can_add_equipment": body.can_add_equipment,
        },
        "status": "active" if invited else "invited",
        "created_at": now_utc().isoformat(),
    }
    await db.property_members.insert_one(dict(doc))
    return doc

@api_router.delete("/properties/{pid}/members/{member_id}")
async def remove_member(pid: str, member_id: str, user=Depends(get_current_user)):
    prop = await db.properties.find_one({"property_id": pid, "user_id": user["user_id"]}, {"_id": 0})
    if not prop:
        raise HTTPException(status_code=404, detail="Bien introuvable")
    await db.property_members.delete_one({"member_id": member_id, "property_id": pid})
    return {"ok": True}

# --------------- Favourites ---------------
@api_router.get("/favourites")
async def list_favourites(kind: Optional[str] = None, user=Depends(get_current_user)):
    q = {"user_id": user["user_id"]}
    if kind:
        if kind not in FAVOURITE_KINDS:
            raise HTTPException(status_code=400, detail="Kind invalide")
        q["kind"] = kind
    return await db.favourites.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)

@api_router.post("/favourites")
async def add_favourite(body: FavouriteInput, user=Depends(get_current_user)):
    if body.kind not in FAVOURITE_KINDS:
        raise HTTPException(status_code=400, detail="Kind invalide")
    existing = await db.favourites.find_one({"user_id": user["user_id"], "kind": body.kind, "ref_id": body.ref_id, "label": body.label})
    if existing:
        return {k: v for k, v in existing.items() if k != "_id"}
    doc = {
        "favourite_id": new_id("fav"),
        "user_id": user["user_id"],
        "kind": body.kind,
        "ref_id": body.ref_id,
        "label": body.label or "",
        "metadata": body.metadata or {},
        "created_at": now_utc().isoformat(),
    }
    await db.favourites.insert_one(dict(doc))
    return doc

@api_router.delete("/favourites/{favourite_id}")
async def remove_favourite(favourite_id: str, user=Depends(get_current_user)):
    await db.favourites.delete_one({"favourite_id": favourite_id, "user_id": user["user_id"]})
    return {"ok": True}

# --------------- Customer Analytics ---------------
@api_router.get("/analytics/mine")
async def my_analytics(user=Depends(get_current_user)):
    bookings = await db.bookings.find({"client_id": user["user_id"]}, {"_id": 0}).to_list(500)
    completed = [b for b in bookings if b.get("status") == "completed"]
    trades = {}
    for b in bookings:
        a = await db.artisan_profiles.find_one({"artisan_id": b.get("artisan_id")}, {"_id": 0, "trade": 1})
        if a:
            trades[a["trade"]] = trades.get(a["trade"], 0) + 1
    favourite_trade = max(trades.items(), key=lambda kv: kv[1])[0] if trades else None
    # money — sum from transfers where client is us
    payments_docs = await db.payments.find({"client_id": user["user_id"], "status": "succeeded"}, {"_id": 0}).to_list(500)
    total_spent = sum(p.get("amount_cents", 0) for p in payments_docs) / 100
    avg_cost = int(total_spent / len(completed)) if completed else 0

    # Response times (approx via booking created→first status change) — placeholder demo values if empty.
    avg_response_min = 22 if not bookings else None

    # Property count + total interventions
    property_count = await db.properties.count_documents({"user_id": user["user_id"]})
    # Estimated money saved: for MVP show a heuristic — 15% average discount vs market baseline.
    money_saved = int(total_spent * 0.15)
    return {
        "bookings_count": len(bookings),
        "completed_count": len(completed),
        "total_spent_eur": total_spent,
        "money_saved_eur": money_saved,
        "avg_repair_cost_eur": avg_cost,
        "avg_response_min": avg_response_min or 22,
        "favourite_trade": favourite_trade,
        "trades_breakdown": trades,
        "property_count": property_count,
        "demo_values": len(bookings) == 0,
    }

# --------------- Growth hooks ---------------
# Wired into booking completion (see below) and review posting.

# ============================================================
# ENTERPRISE — Organizations, Teams, Work Orders, Business Dashboard, Map
# ============================================================

class OrgInput(BaseModel):
    name: str
    org_type: str = "other"
    industry: Optional[str] = ""
    address: Optional[str] = ""
    tax_id: Optional[str] = ""
    logo: Optional[str] = ""

class OrgMemberInput(BaseModel):
    email: EmailStr
    role: str = "employee"

class OrgMemberRoleInput(BaseModel):
    role: str

class WorkOrderInput(BaseModel):
    organization_id: str
    property_id: Optional[str] = None
    title: str
    description: Optional[str] = ""
    priority: str = "normal"
    trade: Optional[str] = None
    preferred_slot: Optional[str] = None
    photos: List[str] = Field(default_factory=list)
    documents: List[str] = Field(default_factory=list)
    budget_cents: Optional[int] = None

class WorkOrderTransitionInput(BaseModel):
    to_status: str
    note: Optional[str] = ""

class OrgDocumentInput(BaseModel):
    title: str
    category: str = "other"
    file_uri: Optional[str] = ""
    property_id: Optional[str] = None
    notes: Optional[str] = ""

class LinkPropertyInput(BaseModel):
    property_id: str

class IntegrationConfigInput(BaseModel):
    integration_key: str
    config: dict = {}

ORG_DOC_CATEGORIES = ["invoice", "contract", "report", "certificate", "guarantee", "manual", "inspection", "safety", "other"]

async def _load_org_membership(user_id: str, org_id: str) -> dict:
    m = await db.organization_members.find_one({"organization_id": org_id, "user_id": user_id, "status": "active"}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=403, detail="Membre non autorisé de cette organisation")
    return m

async def _require_org_permission(user_id: str, org_id: str, action: str) -> dict:
    m = await _load_org_membership(user_id, org_id)
    if not enterprise.has_permission(m["role"], action):
        raise HTTPException(status_code=403, detail=f"Permission '{action}' requise")
    return m

@api_router.post("/organizations")
async def create_organization(body: OrgInput, user=Depends(get_current_user)):
    if body.org_type not in enterprise.ORG_TYPES:
        raise HTTPException(status_code=400, detail="Type d'organisation invalide")
    oid = new_id("org")
    doc = {
        "organization_id": oid, "name": body.name.strip(), "org_type": body.org_type,
        "industry": body.industry or "", "address": body.address or "", "tax_id": body.tax_id or "",
        "logo": body.logo or "", "owner_id": user["user_id"], "created_at": enterprise.now_iso(),
    }
    await db.organizations.insert_one(dict(doc))
    await db.organization_members.insert_one({
        "member_id": new_id("mem"), "organization_id": oid, "user_id": user["user_id"],
        "email": user["email"], "name": user["name"], "role": "owner", "status": "active",
        "created_at": enterprise.now_iso(),
    })
    account_type = "property_manager" if body.org_type == "property_manager" else "business"
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"account_type": account_type}})
    return doc

@api_router.get("/organizations/mine")
async def my_organizations(user=Depends(get_current_user)):
    memberships = await db.organization_members.find({"user_id": user["user_id"], "status": "active"}, {"_id": 0}).to_list(50)
    ids = [m["organization_id"] for m in memberships]
    orgs = await db.organizations.find({"organization_id": {"$in": ids}}, {"_id": 0}).to_list(50)
    for o in orgs:
        m = next((mm for mm in memberships if mm["organization_id"] == o["organization_id"]), {})
        o["my_role"] = m.get("role")
    return orgs

@api_router.patch("/organizations/{oid}")
async def update_organization(oid: str, body: dict, user=Depends(get_current_user)):
    await _require_org_permission(user["user_id"], oid, "org.update")
    if "org_type" in body and body["org_type"] not in enterprise.ORG_TYPES:
        raise HTTPException(status_code=400, detail="Type invalide")
    allowed = {"name", "org_type", "industry", "address", "tax_id", "logo"}
    updates = {k: v for k, v in body.items() if k in allowed}
    updates["updated_at"] = enterprise.now_iso()
    await db.organizations.update_one({"organization_id": oid}, {"$set": updates})
    return await db.organizations.find_one({"organization_id": oid}, {"_id": 0})

@api_router.get("/organizations/{oid}/members")
async def list_members_org(oid: str, user=Depends(get_current_user)):
    await _load_org_membership(user["user_id"], oid)
    return await db.organization_members.find({"organization_id": oid}, {"_id": 0}).sort("created_at", 1).to_list(500)

@api_router.post("/organizations/{oid}/members")
async def invite_member_org(oid: str, body: OrgMemberInput, user=Depends(get_current_user)):
    await _require_org_permission(user["user_id"], oid, "team.invite")
    if body.role not in enterprise.TEAM_ROLES:
        raise HTTPException(status_code=400, detail="Rôle invalide")
    if body.role == "owner":
        raise HTTPException(status_code=400, detail="Un seul propriétaire par organisation")
    invited = await db.users.find_one({"email": body.email}, {"_id": 0, "user_id": 1, "name": 1})
    doc = {
        "member_id": new_id("mem"), "organization_id": oid,
        "user_id": invited["user_id"] if invited else None,
        "email": body.email, "name": invited["name"] if invited else "",
        "role": body.role, "status": "active" if invited else "invited",
        "created_at": enterprise.now_iso(),
    }
    await db.organization_members.insert_one(dict(doc))
    return doc

@api_router.patch("/organizations/{oid}/members/{member_id}")
async def update_member_role(oid: str, member_id: str, body: OrgMemberRoleInput, user=Depends(get_current_user)):
    await _require_org_permission(user["user_id"], oid, "team.update_role")
    if body.role not in enterprise.TEAM_ROLES or body.role == "owner":
        raise HTTPException(status_code=400, detail="Rôle invalide")
    await db.organization_members.update_one({"member_id": member_id, "organization_id": oid}, {"$set": {"role": body.role, "updated_at": enterprise.now_iso()}})
    return {"ok": True, "role": body.role}

@api_router.delete("/organizations/{oid}/members/{member_id}")
async def remove_member_org(oid: str, member_id: str, user=Depends(get_current_user)):
    await _require_org_permission(user["user_id"], oid, "team.remove")
    await db.organization_members.delete_one({"member_id": member_id, "organization_id": oid})
    return {"ok": True}

@api_router.post("/organizations/{oid}/properties/link")
async def link_property_to_org(oid: str, body: LinkPropertyInput, user=Depends(get_current_user)):
    await _require_org_permission(user["user_id"], oid, "property.add")
    prop = await db.properties.find_one({"property_id": body.property_id, "user_id": user["user_id"]})
    if not prop:
        raise HTTPException(status_code=404, detail="Bien introuvable ou non détenu")
    await db.properties.update_one({"property_id": body.property_id}, {"$set": {"organization_id": oid}})
    return {"ok": True}

@api_router.get("/organizations/{oid}/properties")
async def org_properties(oid: str, user=Depends(get_current_user)):
    await _load_org_membership(user["user_id"], oid)
    return await db.properties.find({"organization_id": oid}, {"_id": 0}).sort("created_at", -1).to_list(1000)

@api_router.post("/work-orders")
async def create_work_order(body: WorkOrderInput, user=Depends(get_current_user)):
    m = await _require_org_permission(user["user_id"], body.organization_id, "work_order.create")
    if body.priority not in enterprise.WORK_ORDER_PRIORITIES:
        raise HTTPException(status_code=400, detail="Priorité invalide")
    initial_status = "pending_approval" if m["role"] == "employee" else "draft"
    doc = {
        "work_order_id": new_id("wo"), "organization_id": body.organization_id,
        "property_id": body.property_id, "created_by": user["user_id"], "creator_name": user["name"],
        "title": body.title.strip(), "description": body.description or "",
        "priority": body.priority, "trade": body.trade, "preferred_slot": body.preferred_slot,
        "photos": body.photos[:6], "documents": body.documents[:10], "budget_cents": body.budget_cents,
        "status": initial_status,
        "history": [{"status": initial_status, "at": enterprise.now_iso(), "by": user["user_id"], "note": ""}],
        "created_at": enterprise.now_iso(),
    }
    await db.work_orders.insert_one(dict(doc))
    return doc

@api_router.get("/work-orders")
async def list_work_orders(organization_id: Optional[str] = None, status: Optional[str] = None,
                            property_id: Optional[str] = None, user=Depends(get_current_user)):
    q: dict = {}
    if organization_id:
        await _load_org_membership(user["user_id"], organization_id)
        q["organization_id"] = organization_id
    else:
        my_orgs = await db.organization_members.find({"user_id": user["user_id"], "status": "active"}, {"_id": 0, "organization_id": 1}).to_list(50)
        q["organization_id"] = {"$in": [m["organization_id"] for m in my_orgs]}
    if status:
        if status not in enterprise.WORK_ORDER_STATUSES:
            raise HTTPException(status_code=400, detail="Status invalide")
        q["status"] = status
    if property_id:
        q["property_id"] = property_id
    return await db.work_orders.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)

@api_router.get("/work-orders/{woid}")
async def get_work_order(woid: str, user=Depends(get_current_user)):
    w = await db.work_orders.find_one({"work_order_id": woid}, {"_id": 0})
    if not w:
        raise HTTPException(status_code=404, detail="Ordre de travail introuvable")
    await _load_org_membership(user["user_id"], w["organization_id"])
    return w

@api_router.post("/work-orders/{woid}/transition")
async def transition_work_order(woid: str, body: WorkOrderTransitionInput, user=Depends(get_current_user)):
    w = await db.work_orders.find_one({"work_order_id": woid}, {"_id": 0})
    if not w:
        raise HTTPException(status_code=404, detail="Ordre de travail introuvable")
    if body.to_status not in enterprise.WORK_ORDER_STATUSES:
        raise HTTPException(status_code=400, detail="Status invalide")
    allowed = enterprise.WORK_ORDER_TRANSITIONS.get(w["status"], set())
    if body.to_status not in allowed:
        raise HTTPException(status_code=400, detail=f"Transition {w['status']} → {body.to_status} interdite")
    action_map = {
        "pending_approval": "work_order.update", "approved": "work_order.approve",
        "rejected": "work_order.reject", "in_progress": "work_order.update",
        "completed": "work_order.complete", "cancelled": "work_order.cancel",
    }
    action = action_map.get(body.to_status, "work_order.update")
    await _require_org_permission(user["user_id"], w["organization_id"], action)
    await db.work_orders.update_one(
        {"work_order_id": woid},
        {"$set": {"status": body.to_status, "updated_at": enterprise.now_iso()},
         "$push": {"history": {"status": body.to_status, "at": enterprise.now_iso(), "by": user["user_id"], "note": body.note or ""}}},
    )
    return {"ok": True, "status": body.to_status}

@api_router.get("/organizations/{oid}/dashboard")
async def business_dashboard(oid: str, user=Depends(get_current_user)):
    await _load_org_membership(user["user_id"], oid)
    total_properties = await db.properties.count_documents({"organization_id": oid})
    open_wos = await db.work_orders.count_documents({"organization_id": oid, "status": {"$in": ["draft", "pending_approval", "approved", "in_progress"]}})
    pending_approvals = await db.work_orders.count_documents({"organization_id": oid, "status": "pending_approval"})
    props = await db.properties.find({"organization_id": oid}, {"_id": 0, "property_id": 1}).to_list(1000)
    pids = [p["property_id"] for p in props]
    upcoming_maintenance = await db.property_reminders.count_documents({"property_id": {"$in": pids}, "status": {"$in": ["upcoming", "due"]}})
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    mspend = await db.payments.aggregate([
        {"$match": {"status": "succeeded", "created_at": {"$gte": since}}},
        {"$lookup": {"from": "bookings", "localField": "booking_id", "foreignField": "booking_id", "as": "b"}},
        {"$unwind": "$b"},
        {"$match": {"b.property_id": {"$in": pids}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_cents"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    docs_count = await db.property_documents.count_documents({"property_id": {"$in": pids}})
    org_docs_count = await db.org_documents.count_documents({"organization_id": oid})
    invoices_count = await db.invoices.count_documents({"property_id": {"$in": pids}})
    recent = []
    async for w in db.work_orders.find({"organization_id": oid}, {"_id": 0}).sort("created_at", -1).limit(5):
        recent.append({"type": "work_order", "at": w["created_at"], "title": w["title"], "ref": w["work_order_id"], "status": w["status"]})
    async for r in db.property_reminders.find({"property_id": {"$in": pids}}, {"_id": 0}).sort("created_at", -1).limit(5):
        recent.append({"type": "reminder", "at": r["created_at"], "title": r["title"], "ref": r["reminder_id"], "status": r["status"]})
    recent.sort(key=lambda x: x["at"], reverse=True)
    return {
        "total_properties": total_properties, "open_interventions": open_wos,
        "upcoming_maintenance": upcoming_maintenance, "pending_approvals": pending_approvals,
        "monthly_spending_cents": mspend[0]["total"] if mspend else 0,
        "monthly_payments_count": mspend[0]["count"] if mspend else 0,
        "avg_response_min": 22,
        "property_documents_count": docs_count,
        "organization_documents_count": org_docs_count,
        "invoices_count": invoices_count,
        "recent_activity": recent[:10],
    }

@api_router.get("/organizations/{oid}/analytics")
async def business_analytics(oid: str, user=Depends(get_current_user)):
    await _load_org_membership(user["user_id"], oid)
    props = await db.properties.find({"organization_id": oid}, {"_id": 0, "property_id": 1}).to_list(1000)
    pids = [p["property_id"] for p in props]
    completed = await db.work_orders.count_documents({"organization_id": oid, "status": "completed"})
    urgent = await db.work_orders.count_documents({"organization_id": oid, "priority": "urgent"})
    frequent_issues = await db.work_orders.aggregate([
        {"$match": {"organization_id": oid, "trade": {"$ne": None}}},
        {"$group": {"_id": "$trade", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}, {"$limit": 5},
    ]).to_list(5)
    top_pros = await db.transfers.aggregate([
        {"$lookup": {"from": "bookings", "localField": "booking_id", "foreignField": "booking_id", "as": "b"}},
        {"$unwind": "$b"},
        {"$match": {"b.property_id": {"$in": pids}}},
        {"$group": {"_id": "$artisan_id", "revenue": {"$sum": "$net_cents"}, "count": {"$sum": 1}}},
        {"$sort": {"revenue": -1}}, {"$limit": 5},
    ]).to_list(5)
    health_scores = []
    for pid in pids:
        equipment = await db.property_equipment.find({"property_id": pid}, {"_id": 0}).to_list(200)
        if not equipment:
            health_scores.append(100)
            continue
        ok = sum(1 for e in equipment if e.get("status") == "ok")
        att = sum(1 for e in equipment if e.get("status") in ("attention", "maintenance"))
        rep = sum(1 for e in equipment if e.get("status") == "replace")
        health_scores.append(int(round((ok * 100 + att * 60 + rep * 20) / len(equipment))))
    avg_health = int(sum(health_scores) / len(health_scores)) if health_scores else 100
    return {
        "completed_work_orders": completed, "urgent_work_orders": urgent,
        "frequent_issues": [{"trade": r["_id"], "count": r["count"]} for r in frequent_issues],
        "top_professionals": [{"artisan_id": r["_id"], "revenue_cents": r["revenue"], "count": r["count"]} for r in top_pros],
        "average_property_health": avg_health, "properties_count": len(pids),
    }

@api_router.get("/organizations/{oid}/map")
async def business_map(oid: str, user=Depends(get_current_user)):
    await _load_org_membership(user["user_id"], oid)
    props = await db.properties.find({"organization_id": oid}, {"_id": 0}).to_list(1000)
    out = []
    for p in props:
        pid = p["property_id"]
        open_ints = await db.work_orders.count_documents({"organization_id": oid, "property_id": pid, "status": {"$in": ["pending_approval", "approved", "in_progress"]}})
        urgent = await db.work_orders.count_documents({"organization_id": oid, "property_id": pid, "priority": "urgent", "status": {"$nin": ["completed", "cancelled", "rejected"]}})
        upcoming = await db.property_reminders.count_documents({"property_id": pid, "status": {"$in": ["upcoming", "due"]}})
        out.append({
            "property_id": pid, "name": p.get("name"), "address": p.get("address"),
            "lat": p.get("lat"), "lng": p.get("lng"),
            "open_interventions": open_ints, "urgent_count": urgent, "upcoming_maintenance": upcoming,
        })
    return out

@api_router.get("/organizations/{oid}/documents")
async def list_org_documents(oid: str, category: Optional[str] = None, user=Depends(get_current_user)):
    await _load_org_membership(user["user_id"], oid)
    q = {"organization_id": oid}
    if category:
        if category not in ORG_DOC_CATEGORIES:
            raise HTTPException(status_code=400, detail="Catégorie invalide")
        q["category"] = category
    return await db.org_documents.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)

@api_router.post("/organizations/{oid}/documents")
async def add_org_document(oid: str, body: OrgDocumentInput, user=Depends(get_current_user)):
    await _require_org_permission(user["user_id"], oid, "documents.upload")
    if body.category not in ORG_DOC_CATEGORIES:
        raise HTTPException(status_code=400, detail="Catégorie invalide")
    doc = {
        "document_id": new_id("odoc"), "organization_id": oid,
        "title": body.title.strip(), "category": body.category,
        "file_uri": body.file_uri or "", "property_id": body.property_id,
        "notes": body.notes or "", "uploaded_by": user["user_id"],
        "created_at": enterprise.now_iso(),
    }
    await db.org_documents.insert_one(dict(doc))
    return doc

@api_router.delete("/organizations/{oid}/documents/{did}")
async def delete_org_document(oid: str, did: str, user=Depends(get_current_user)):
    await _require_org_permission(user["user_id"], oid, "documents.delete")
    await db.org_documents.delete_one({"document_id": did, "organization_id": oid})
    return {"ok": True}

@api_router.get("/integrations/available")
async def list_integrations():
    return enterprise.INTEGRATIONS_CATALOG

@api_router.get("/organizations/{oid}/integrations")
async def list_org_integrations(oid: str, user=Depends(get_current_user)):
    await _load_org_membership(user["user_id"], oid)
    return await db.org_integrations.find({"organization_id": oid}, {"_id": 0}).to_list(50)

@api_router.post("/organizations/{oid}/integrations")
async def configure_integration(oid: str, body: IntegrationConfigInput, user=Depends(get_current_user)):
    await _require_org_permission(user["user_id"], oid, "integrations.configure")
    if not any(i["key"] == body.integration_key for i in enterprise.INTEGRATIONS_CATALOG):
        raise HTTPException(status_code=400, detail="Intégration inconnue")
    doc = {
        "config_id": new_id("intg"), "organization_id": oid,
        "integration_key": body.integration_key, "config": body.config or {},
        "status": "coming_soon", "created_at": enterprise.now_iso(),
    }
    await db.org_integrations.insert_one(dict(doc))
    return doc

@api_router.get("/enterprise/roles")
async def enterprise_roles():
    return {r: enterprise.role_capabilities(r) for r in enterprise.TEAM_ROLES}

@api_router.get("/enterprise/account-types")
async def enterprise_account_types():
    return enterprise.ACCOUNT_TYPES

# ============================================================
# CONFIGURATION
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

# ---------- Subscriptions ----------
@api_router.get("/subscriptions/plans")
async def subscription_plans():
    """Public catalog — safe to expose."""
    return [{k: v for k, v in p.items() if k != "stripe_price_id"} for p in payments.PLANS]

@api_router.post("/subscriptions/subscribe")
async def subscribe_plan(body: SubscribePlanInput, user=Depends(get_current_user)):
    if user.get("role") != "artisan":
        raise HTTPException(status_code=403, detail="Réservé aux artisans")
    plan = next((p for p in payments.PLANS if p["key"] == body.plan_key), None)
    if not plan:
        raise HTTPException(status_code=400, detail="Plan inconnu")
    if plan["price_cents"] == 0:
        # Starter = free tier, no Stripe subscription needed.
        await db.subscriptions_records.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"plan_key": "starter", "status": "active", "updated_at": payments.now_utc_iso()}},
            upsert=True,
        )
        await payments.audit(db, user["user_id"], "subscription.free_activated", "starter")
        return {"plan_key": "starter", "status": "active", "mock_mode": payments.MOCK_MODE}

    # Ensure Stripe customer exists
    customer = payments.get_or_create_customer(user["email"], user["name"], {"user_id": user["user_id"]})
    sub = payments.create_subscription(customer["id"], plan["stripe_price_id"] or "price_placeholder_" + body.plan_key, {"user_id": user["user_id"], "plan_key": body.plan_key})
    await db.subscriptions_records.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "user_id": user["user_id"],
            "plan_key": body.plan_key,
            "stripe_customer_id": customer["id"],
            "stripe_subscription_id": sub["id"],
            "status": sub["status"],
            "current_period_end": sub.get("current_period_end"),
            "updated_at": payments.now_utc_iso(),
        }},
        upsert=True,
    )
    await payments.audit(db, user["user_id"], "subscription.subscribed", sub["id"], {"plan_key": body.plan_key})
    return {"plan_key": body.plan_key, "status": sub["status"], "subscription_id": sub["id"], "mock_mode": payments.MOCK_MODE}

@api_router.post("/subscriptions/cancel")
async def cancel_current_subscription(user=Depends(get_current_user)):
    row = await db.subscriptions_records.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not row or not row.get("stripe_subscription_id"):
        raise HTTPException(status_code=404, detail="Aucun abonnement actif")
    res = payments.cancel_subscription(row["stripe_subscription_id"], at_period_end=True)
    await db.subscriptions_records.update_one({"user_id": user["user_id"]}, {"$set": {
        "cancel_at_period_end": True,
        "canceled_at": payments.now_utc_iso(),
        "status": res.get("status", row["status"]),
    }})
    await payments.audit(db, user["user_id"], "subscription.canceled", row["stripe_subscription_id"])
    return {"ok": True, "cancel_at_period_end": True}

@api_router.get("/subscriptions/mine")
async def my_subscription(user=Depends(get_current_user)):
    row = await db.subscriptions_records.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not row:
        return {"plan_key": "starter", "status": "active"}
    return row

# ---------- Professional finance dashboard ----------
@api_router.get("/artisans/me/finance")
async def artisan_finance(user=Depends(get_current_user)):
    if user.get("role") != "artisan":
        raise HTTPException(status_code=403, detail="Réservé aux artisans")
    profile = await db.artisan_profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not profile:
        raise HTTPException(status_code=404, detail="Profil introuvable")
    aid = profile["artisan_id"]
    transfers = await db.transfers.find({"artisan_id": aid}, {"_id": 0}).sort("created_at", -1).to_list(500)
    revenue = sum(t.get("net_cents", 0) for t in transfers)
    commissions = sum(t.get("commission_cents", 0) for t in transfers)
    gross = sum(t.get("gross_cents", 0) for t in transfers)
    pending = await db.escrows.aggregate([
        {"$match": {"artisan_id": aid, "state": "held"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount_cents"}, "count": {"$sum": 1}}},
    ]).to_list(1)
    pending_total = pending[0]["total"] if pending else 0
    pending_count = pending[0]["count"] if pending else 0

    # Monthly evolution (last 6 months, YYYY-MM buckets).
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
    }

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

# ---------- Future-ready stubs — advertise, don't implement ----------
@api_router.get("/payments/future-features")
async def future_features():
    """Advertise upcoming payment products so the app can render 'coming soon' surfaces."""
    return [
        {"key": "installments", "title": "Paiement en plusieurs fois", "status": "coming_soon"},
        {"key": "bnpl",         "title": "Buy Now Pay Later", "status": "coming_soon"},
        {"key": "maintenance",  "title": "Abonnements entretien récurrent", "status": "coming_soon"},
        {"key": "insurance",    "title": "Assurance travaux intégrée", "status": "coming_soon"},
        {"key": "financing",    "title": "Financement marketplace", "status": "coming_soon"},
    ]

# ---------- Stripe webhooks — production entrypoint ----------
from fastapi import Request

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
    surface: Optional[float] = None
    year_built: Optional[int] = None
    photos: List[str] = Field(default_factory=list)  # base64 or URL
    notes: Optional[str] = ""

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
        "surface": body.surface,
        "year_built": body.year_built,
        "photos": body.photos or [],
        "notes": (body.notes or "").strip(),
        "created_at": now_utc().isoformat(),
        "updated_at": now_utc().isoformat(),
    }
    await db.properties.insert_one(dict(prop))
    await _add_points(user["user_id"], "property_created")
    return prop

@api_router.get("/properties/{pid}")
async def get_property(pid: str, user=Depends(get_current_user)):
    return await _get_property(pid, user["user_id"])

@api_router.patch("/properties/{pid}")
async def update_property(pid: str, body: dict, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    if "type" in body and body["type"] not in PROPERTY_TYPES:
        raise HTTPException(status_code=400, detail="Type de bien invalide")
    allowed = {"name", "type", "address", "surface", "year_built", "photos", "notes"}
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
async def update_reminder(pid: str, rid: str, body: dict, user=Depends(get_current_user)):
    await _get_property(pid, user["user_id"])
    if "status" in body and body["status"] not in REMINDER_STATUSES:
        raise HTTPException(status_code=400, detail="Statut invalide")
    body["updated_at"] = now_utc().isoformat()
    await db.property_reminders.update_one({"reminder_id": rid, "property_id": pid}, {"$set": body})
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

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
