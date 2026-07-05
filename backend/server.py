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
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from services import matching, calendar_sync

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
        await db.artisan_profiles.update_one({"artisan_id": existing["artisan_id"]}, {"$set": payload})
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
            "calendar_connected": False,
            "is_subscribed": False,
            "subscription_expires": None,
            "created_at": now_utc().isoformat(),
            **payload,
        }
        await db.artisan_profiles.insert_one(profile)
        profile.pop("_id", None)
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
    return await enrich_artisan(artisan)

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
