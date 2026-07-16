"""Authentication routes — Sprint 14 Phase 1 migration.

Migrated endpoints (from server.py lines 225-338):
- GET  /api/                (root)
- POST /api/auth/register
- POST /api/auth/login
- POST /api/auth/google
- GET  /api/auth/me
- POST /api/auth/logout

No behavior change — this is a lift-and-shift with the DB and helpers injected.
"""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, EmailStr

import bcrypt
import httpx
import os

from services import security as security_svc
from datetime import datetime, timezone
import uuid


router = APIRouter()


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


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False


async def _create_session(db, user_id: str, request: Optional[Request] = None) -> str:
    result = await security_svc.create_secure_session(db, user_id, request=request, days=7)
    return result["token"]


def _client_ip(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        ip = fwd.split(",")[0].strip()
    return ip


EMERGENT_SESSION_API = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"


def build_auth_router(db, get_current_user):
    """Return the auth router bound to the given Motor db and auth dependency."""
    r = APIRouter()

    @r.get("/")
    async def root():
        return {"message": "Auxora API"}

    @r.post("/auth/register")
    async def register(data: RegisterInput, request: Request):
        existing = await db.users.find_one({"email": data.email.lower()})
        if existing:
            raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")
        user_id = _new_id("user")
        user = {
            "user_id": user_id,
            "email": data.email.lower(),
            "name": data.name,
            "role": data.role if data.role in ("client", "artisan") else "client",
            "password": _hash_password(data.password),
            "picture": None,
            "created_at": _now_utc().isoformat(),
        }
        await db.users.insert_one(user)
        token = await _create_session(db, user_id, request=request)
        ip = _client_ip(request)
        await security_svc.audit_log(
            db, action="auth.register", actor_id=user_id, actor_role=user["role"],
            target=user_id, metadata={"email": user["email"]}, severity="info", ip=ip,
        )
        user.pop("_id", None)
        return {"token": token, "user": {k: v for k, v in user.items() if k != "password"}}

    @r.post("/auth/login")
    async def login(data: LoginInput, request: Request):
        ip = _client_ip(request)
        # Brute-force / rate-limit guard (Sprint 8)
        await security_svc.check_login_rate_limit(db, data.email, ip)
        user = await db.users.find_one({"email": data.email.lower()})
        if not user or not user.get("password") or not _verify_password(data.password, user["password"]):
            await security_svc.record_login_attempt(db, data.email, ip, success=False)
            await security_svc.audit_log(
                db, action="auth.login_failed", actor_id=None, actor_role=None,
                target=data.email.lower(), metadata={"reason": "invalid_credentials"},
                severity="warn", ip=ip,
            )
            raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
        if user.get("deleted") or user.get("anonymized"):
            raise HTTPException(status_code=401, detail="Compte supprimé")
        token = await _create_session(db, user["user_id"], request=request)
        await security_svc.record_login_attempt(db, data.email, ip, success=True, user_id=user["user_id"])
        await security_svc.audit_log(
            db, action="auth.login", actor_id=user["user_id"], actor_role=user.get("role"),
            target=user["user_id"], metadata={"email": user["email"]}, severity="info", ip=ip,
        )
        user.pop("password", None)
        user.pop("_id", None)
        return {"token": token, "user": user}

    @r.post("/auth/google")
    async def google_auth(data: GoogleInput, request: Request):
        async with httpx.AsyncClient() as hc:
            resp = await hc.get(EMERGENT_SESSION_API, headers={"X-Session-ID": data.session_token})
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Authentification Google échouée")
        info = resp.json()
        email = info["email"].lower()
        user = await db.users.find_one({"email": email})
        is_new = False
        if not user:
            is_new = True
            user_id = _new_id("user")
            user = {
                "user_id": user_id,
                "email": email,
                "name": info.get("name", "Utilisateur"),
                "role": data.role if data.role in ("client", "artisan") else "client",
                "password": None,
                "picture": info.get("picture"),
                "created_at": _now_utc().isoformat(),
            }
            await db.users.insert_one(user)
        if user.get("deleted") or user.get("anonymized"):
            raise HTTPException(status_code=401, detail="Compte supprimé")
        token = await _create_session(db, user["user_id"], request=request)
        ip = _client_ip(request)
        await security_svc.audit_log(
            db, action="auth.google_login" if not is_new else "auth.google_register",
            actor_id=user["user_id"], actor_role=user.get("role"),
            target=user["user_id"], metadata={"email": email}, severity="info", ip=ip,
        )
        user.pop("password", None)
        user.pop("_id", None)
        return {"token": token, "user": user}

    @r.get("/auth/me")
    async def me(user=Depends(get_current_user)):
        user.pop("_current_token", None)
        return user

    @r.post("/auth/logout")
    async def logout(authorization: Optional[str] = Header(None)):
        if authorization and authorization.startswith("Bearer "):
            token = authorization.split(" ", 1)[1]
            sess = await db.user_sessions.find_one({"session_token": token})
            if sess:
                await db.user_sessions.update_one(
                    {"session_token": token},
                    {"$set": {"revoked": True, "revoked_at": _now_utc().isoformat()}},
                )
                await security_svc.audit_log(
                    db, action="auth.logout", actor_id=sess.get("user_id"),
                    target=sess.get("user_id"), severity="info",
                )
        return {"ok": True}

    return r
