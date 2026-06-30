from fastapi import FastAPI, APIRouter, HTTPException, Header, Depends
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import bcrypt
import httpx
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
from datetime import datetime, timezone, timedelta

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

class BookingInput(BaseModel):
    artisan_id: str
    date: str
    slot: str
    description: str = ""

class BookingStatusInput(BaseModel):
    status: str

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
async def list_artisans(category: Optional[str] = None, q: Optional[str] = None):
    query = {"is_subscribed": True}
    if category:
        query["trade"] = category
    artisans = await db.artisan_profiles.find(query, {"_id": 0}).to_list(500)
    artisans = [await enrich_artisan(a) for a in artisans]
    if q:
        ql = q.lower()
        artisans = [a for a in artisans if ql in a.get("title", "").lower() or ql in a.get("city", "").lower() or ql in a.get("trade_name", "").lower() or ql in (a.get("name") or "").lower()]
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
    booking = {
        "booking_id": booking_id,
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
    booking.pop("_id", None)
    return booking

@api_router.get("/bookings/mine")
async def my_bookings(user=Depends(get_current_user)):
    bookings = await db.bookings.find({"client_id": user["user_id"]}, {"_id": 0}).to_list(500)
    bookings.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return bookings

@api_router.get("/bookings/received")
async def received_bookings(user=Depends(get_current_user)):
    bookings = await db.bookings.find({"artisan_user_id": user["user_id"]}, {"_id": 0}).to_list(500)
    bookings.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return bookings

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
        for s in SEED_ARTISANS:
            cat = CATEGORY_MAP.get(s["trade"])
            doc = {
                "artisan_id": new_id("art"),
                "user_id": None,
                "seed": True,
                "is_subscribed": True,
                "subscription_expires": (now_utc() + timedelta(days=365)).isoformat(),
                "trade_name": cat["name"] if cat else s["trade"],
                "phone": "+33 6 12 34 56 78",
                "created_at": now_utc().isoformat(),
                **s,
            }
            await db.artisan_profiles.insert_one(doc)
        logger.info("Seeded artisans")

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
