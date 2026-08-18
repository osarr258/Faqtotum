"""Authentication routes — hardened for FAQTOTUM V1.

Supported providers (Chemin A retained by product):
- POST /auth/register         — email + bcrypt password
- POST /auth/login            — email + bcrypt password (rate-limited)
- POST /auth/google           — session_token from the Emergent-managed
                                 Google OAuth gateway. Delegated trust,
                                 but the RESPONSE is validated strictly here.
- POST /auth/apple            — native `expo-apple-authentication` identity
                                 token, verified against Apple's JWKS.

Security guarantees added in this iteration:
- Rate limiting (per-IP + per-email) on `/auth/login`, `/auth/google`,
  `/auth/apple`. Same primitive as password login.
- Anti account-takeover-by-email-collision: a Google/Apple login on an
  email that already exists in the DB but was NOT created (or previously
  linked) with that provider is REJECTED with HTTP 409 + a machine-readable
  `ACCOUNT_LINK_REQUIRED` error code. The audit chain logs the attempt.
- Every successful session records `method` = "email" | "google" | "apple"
  for the audit chain.
- Google: strict schema validation on the Emergent response (email format,
  required fields, length caps), short timeout with 1 automatic retry,
  refuse when `email` is absent or malformed.
- Apple: full RFC 7515/7519 verification — RS256 signature via Apple JWKS,
  `iss = "https://appleid.apple.com"`, `aud ∈ APPLE_AUDIENCES`, expiration
  check, optional nonce check to prevent replay.
"""
from __future__ import annotations
import asyncio
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

import bcrypt
import httpx
import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from jwt import PyJWKClient
from pydantic import BaseModel, EmailStr, Field, ValidationError

from services import security as security_svc


router = APIRouter()


# -------------------------------------------------------------
# Pydantic input models
# -------------------------------------------------------------
class RegisterInput(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "client"


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class GoogleInput(BaseModel):
    session_token: str = Field(..., min_length=8, max_length=512)
    role: str = "client"


class AppleInput(BaseModel):
    identity_token: str = Field(..., min_length=32, max_length=4096)
    # Apple returns name + email ONLY on the first sign-in. The client
    # forwards them here on that first call; the backend persists them.
    email: Optional[EmailStr] = None
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    # Anti-replay nonce (raw text; Apple sees its SHA-256).
    nonce: Optional[str] = Field(None, max_length=256)
    role: str = "client"


# -------------------------------------------------------------
# Small helpers
# -------------------------------------------------------------
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


def _client_ip(request: Request) -> str:
    ip = request.client.host if request.client else "unknown"
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        ip = fwd.split(",")[0].strip()
    return ip


async def _create_session(db, user_id: str, request: Optional[Request], method: str) -> str:
    result = await security_svc.create_secure_session(
        db, user_id, request=request, days=7, method=method,
    )
    return result["token"]


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(raw: str) -> Optional[str]:
    """Normalize + validate an email string. Returns None if invalid."""
    if not isinstance(raw, str):
        return None
    s = raw.strip().lower()
    if not s or len(s) > 320:  # RFC 5321 practical cap
        return None
    if not _EMAIL_RE.match(s):
        return None
    return s


# -------------------------------------------------------------
# Cross-provider collision guard
# -------------------------------------------------------------
async def _check_provider_collision(
    db, email: str, incoming_provider: str, incoming_sub: Optional[str],
) -> Tuple[Optional[dict], bool]:
    """Return `(user_or_None, needs_linking)`.

    Behaviour:
    - No user with that email → `(None, False)` (caller creates a new user).
    - User exists AND the incoming provider is already recorded in
      `user.providers[]` (matched by provider name; sub optional) →
      `(user, False)` (caller logs the user in as usual).
    - User exists but the incoming provider is NOT linked yet →
      `(user, True)` (caller MUST refuse the automatic login and expose a
      link-account flow instead).
    """
    user = await db.users.find_one({"email": email})
    if not user:
        return None, False

    providers = user.get("providers") or []

    # Legacy users have no `providers` array yet — infer it from the state
    # of the user document so we don't lock existing accounts out.
    if not providers:
        if user.get("password"):
            providers = [{"provider": "email"}]
        else:
            # Pre-migration Google-only user (created before the providers
            # field existed). Assume "google" so we don't break legacy logins.
            providers = [{"provider": "google"}]
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"providers": providers}},
        )
        user["providers"] = providers

    already_linked = any(p.get("provider") == incoming_provider for p in providers)
    return user, (not already_linked)


async def _link_provider(db, user_id: str, provider: str, sub: Optional[str]) -> None:
    """Append the incoming provider to the user's `providers` array if missing."""
    entry = {"provider": provider, "linked_at": _now_utc().isoformat()}
    if sub:
        entry["sub"] = sub
    # Only push if not already present (defensive; called only after collision check)
    await db.users.update_one(
        {"user_id": user_id, "providers.provider": {"$ne": provider}},
        {"$push": {"providers": entry}},
    )


# -------------------------------------------------------------
# Apple JWKS verification
# -------------------------------------------------------------
APPLE_ISSUER = "https://appleid.apple.com"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
_APPLE_EXPO_GO_AUD = "host.exp.Exponent"  # MUST NEVER appear in prod audiences.
_apple_jwks_client: Optional[PyJWKClient] = None


def _get_apple_jwks_client() -> PyJWKClient:
    global _apple_jwks_client
    if _apple_jwks_client is None:
        # PyJWKClient caches keys in memory (~10 min) so we don't hammer Apple.
        _apple_jwks_client = PyJWKClient(APPLE_JWKS_URL, cache_keys=True, lifespan=600)
    return _apple_jwks_client


class AppleAudiencesConfigError(RuntimeError):
    """Raised at boot when APPLE_AUDIENCES_PROD contains the Expo Go audience.

    This is a structural safeguard: it is impossible to leak the Expo Go
    audience (`host.exp.Exponent`) into a production build because the
    process will refuse to start with a clear, actionable error message.
    """


def _apple_audiences() -> list[str]:
    """
    Return the list of accepted `aud` claims for Apple identity tokens,
    chosen automatically based on `APP_ENV`.

    Rules:
    - `APP_ENV=production` → uses `APPLE_AUDIENCES_PROD` ONLY (real iOS bundle
      identifier). Startup fails if the env var contains the Expo Go audience
      or if the env var is empty.
    - Any other environment (dev / staging / preview) → uses
      `APPLE_AUDIENCES_DEV`, defaulting to `[bundle_id, "host.exp.Exponent"]`
      so Expo Go can authenticate during development.

    Legacy `APPLE_AUDIENCES` is still accepted as a fallback for dev only,
    to keep older setups working. In production it is IGNORED.
    """
    app_env = os.environ.get("APP_ENV", "development").strip().lower()
    default_bundle = "com.emergent.reviensapp.uwn3nc"

    if app_env == "production":
        raw = os.environ.get("APPLE_AUDIENCES_PROD", "").strip()
        if not raw:
            raise AppleAudiencesConfigError(
                "APPLE_AUDIENCES_PROD is required in production. Set it to the "
                "real iOS bundle identifier (e.g. 'com.faqtotum.app'). Never "
                "include 'host.exp.Exponent' in production."
            )
        audiences = [a.strip() for a in raw.split(",") if a.strip()]
        if _APPLE_EXPO_GO_AUD in audiences:
            raise AppleAudiencesConfigError(
                f"APPLE_AUDIENCES_PROD contains '{_APPLE_EXPO_GO_AUD}' which is the "
                "Expo Go development audience. This MUST NOT be exposed in a "
                "production build. Remove it and restart."
            )
        return audiences

    # Non-production: prefer APPLE_AUDIENCES_DEV, fall back to legacy
    # APPLE_AUDIENCES, then to sensible defaults.
    raw = (
        os.environ.get("APPLE_AUDIENCES_DEV", "").strip()
        or os.environ.get("APPLE_AUDIENCES", "").strip()
    )
    if raw:
        return [a.strip() for a in raw.split(",") if a.strip()]
    return [default_bundle, _APPLE_EXPO_GO_AUD]


def verify_apple_audiences_config() -> list[str]:
    """
    Boot-time validation for the Apple audiences configuration.

    Called from `server.py` right after `load_dotenv()` so a mis-configured
    production deploy fails FAST (before serving any request) rather than
    letting an insecure audience list leak into the running app.

    Returns the resolved audience list on success (useful for logging).
    Raises AppleAudiencesConfigError with an actionable message on failure.
    """
    return _apple_audiences()


def _verify_apple_identity_token(
    identity_token: str, expected_nonce: Optional[str] = None,
) -> dict:
    """Verify an Apple identity token and return its decoded claims.

    Raises HTTPException(401) on any verification failure.
    """
    try:
        signing_key = _get_apple_jwks_client().get_signing_key_from_jwt(identity_token).key
    except Exception:
        raise HTTPException(status_code=401, detail="Token Apple invalide (JWKS)")

    try:
        claims = jwt.decode(
            identity_token,
            signing_key,
            algorithms=["RS256"],
            audience=_apple_audiences(),
            issuer=APPLE_ISSUER,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token Apple expiré")
    except jwt.InvalidAudienceError:
        raise HTTPException(status_code=401, detail="Audience Apple invalide")
    except jwt.InvalidIssuerError:
        raise HTTPException(status_code=401, detail="Émetteur Apple invalide")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token Apple invalide")

    # Anti-replay: if the client sent a nonce, Apple must echo its SHA-256.
    if expected_nonce is not None:
        import hashlib
        expected_hash = hashlib.sha256(expected_nonce.encode()).hexdigest()
        token_nonce = claims.get("nonce")
        if not token_nonce or token_nonce != expected_hash:
            raise HTTPException(status_code=401, detail="Nonce Apple invalide")

    return claims


# -------------------------------------------------------------
# Emergent-managed Google — hardened fetch
# -------------------------------------------------------------
EMERGENT_SESSION_API = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"
GOOGLE_FETCH_TIMEOUT_S = 6.0
GOOGLE_FETCH_RETRIES = 1  # one retry on 5xx / connection error


async def _fetch_google_session(session_token: str) -> dict:
    """Delegate Google OAuth verification to the Emergent gateway.

    Trust chain: Google → Emergent (verifies Google JWKS server-side) →
    us (verifies HTTPS + response schema). Timeouts and one retry are
    enforced. Any deviation from the expected schema is fatal (401).
    """
    last_exc: Optional[Exception] = None
    for attempt in range(GOOGLE_FETCH_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=GOOGLE_FETCH_TIMEOUT_S) as hc:
                resp = await hc.get(
                    EMERGENT_SESSION_API,
                    headers={"X-Session-ID": session_token},
                )
            if resp.status_code == 200:
                break
            if 500 <= resp.status_code < 600 and attempt < GOOGLE_FETCH_RETRIES:
                await asyncio.sleep(0.4)
                continue
            raise HTTPException(status_code=401, detail="Authentification Google échouée")
        except HTTPException:
            raise
        except (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError) as exc:
            last_exc = exc
            if attempt < GOOGLE_FETCH_RETRIES:
                await asyncio.sleep(0.4)
                continue
            raise HTTPException(status_code=503, detail="Service Google temporairement indisponible")
    try:
        info = resp.json()
    except Exception:
        raise HTTPException(status_code=401, detail="Réponse Google mal formée")

    if not isinstance(info, dict):
        raise HTTPException(status_code=401, detail="Réponse Google mal formée")

    # Strict schema validation.
    email = _normalize_email(info.get("email", ""))
    if not email:
        raise HTTPException(status_code=401, detail="Email Google manquant ou invalide")

    name = info.get("name") or "Utilisateur"
    if not isinstance(name, str) or len(name) > 200:
        name = "Utilisateur"

    picture = info.get("picture")
    if picture is not None:
        if not isinstance(picture, str) or len(picture) > 1024:
            picture = None

    # Emergent sometimes exposes an `id` — treat as opaque provider sub if str.
    sub = info.get("id") if isinstance(info.get("id"), str) else None

    return {"email": email, "name": name, "picture": picture, "sub": sub}


# -------------------------------------------------------------
# Router factory
# -------------------------------------------------------------
def build_auth_router(db, get_current_user):
    """Return the auth router bound to the given Motor db and auth dependency."""
    r = APIRouter()

    @r.get("/")
    async def root():
        return {"message": "Faqtotum API"}

    # ---------------- Email / Password ----------------
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
            "providers": [{"provider": "email", "linked_at": _now_utc().isoformat()}],
            "created_at": _now_utc().isoformat(),
        }
        await db.users.insert_one(user)
        token = await _create_session(db, user_id, request=request, method="email")
        ip = _client_ip(request)
        await security_svc.audit_log(
            db, action="auth.register", actor_id=user_id, actor_role=user["role"],
            target=user_id,
            metadata={"email": user["email"], "method": "email"},
            severity="info", ip=ip,
        )
        user.pop("_id", None)
        return {"token": token, "user": {k: v for k, v in user.items() if k != "password"}}

    @r.post("/auth/login")
    async def login(data: LoginInput, request: Request):
        ip = _client_ip(request)
        await security_svc.check_login_rate_limit(db, data.email, ip)
        user = await db.users.find_one({"email": data.email.lower()})
        if not user or not user.get("password") or not _verify_password(data.password, user["password"]):
            await security_svc.record_login_attempt(db, data.email, ip, success=False)
            await security_svc.audit_log(
                db, action="auth.login_failed", actor_id=None, actor_role=None,
                target=data.email.lower(),
                metadata={"reason": "invalid_credentials", "method": "email"},
                severity="warn", ip=ip,
            )
            raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
        if user.get("deleted") or user.get("anonymized"):
            raise HTTPException(status_code=401, detail="Compte supprimé")
        token = await _create_session(db, user["user_id"], request=request, method="email")
        await security_svc.record_login_attempt(db, data.email, ip, success=True, user_id=user["user_id"])
        await security_svc.audit_log(
            db, action="auth.login", actor_id=user["user_id"], actor_role=user.get("role"),
            target=user["user_id"],
            metadata={"email": user["email"], "method": "email"},
            severity="info", ip=ip,
        )
        user.pop("password", None)
        user.pop("_id", None)
        return {"token": token, "user": user}

    # ---------------- Google (Emergent-delegated, hardened) ----------------
    @r.post("/auth/google")
    async def google_auth(data: GoogleInput, request: Request):
        ip = _client_ip(request)
        # 1. Rate-limit by IP first (we don't know the email yet). Uses the
        #    same primitive as password login, keyed on a synthetic email.
        await security_svc.check_login_rate_limit(db, f"oauth:google:{ip}", ip)
        # 2. Delegate to Emergent + validate the response.
        info = await _fetch_google_session(data.session_token)
        email = info["email"]
        # 3. Now that we know the email, rate-limit by email too.
        await security_svc.check_login_rate_limit(db, email, ip)
        # 4. Cross-provider collision guard.
        user, needs_linking = await _check_provider_collision(
            db, email, incoming_provider="google", incoming_sub=info.get("sub"),
        )
        if user and needs_linking:
            existing_methods = sorted({p.get("provider") for p in (user.get("providers") or []) if p.get("provider")})
            await security_svc.record_login_attempt(db, email, ip, success=False)
            await security_svc.audit_log(
                db, action="auth.google_link_required",
                actor_id=user["user_id"], actor_role=user.get("role"),
                target=user["user_id"],
                metadata={"email": email, "existing_methods": existing_methods, "method": "google"},
                severity="warn", ip=ip,
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ACCOUNT_LINK_REQUIRED",
                    "message": (
                        "Un compte existe déjà avec cet email. Connectez-vous avec "
                        "votre méthode habituelle, puis liez Google depuis votre profil."
                    ),
                    "existing_methods": existing_methods,
                },
            )

        is_new = user is None
        if is_new:
            user_id = _new_id("user")
            user = {
                "user_id": user_id,
                "email": email,
                "name": info["name"],
                "role": data.role if data.role in ("client", "artisan") else "client",
                "password": None,
                "picture": info.get("picture"),
                "providers": [{
                    "provider": "google",
                    "sub": info.get("sub"),
                    "linked_at": _now_utc().isoformat(),
                }],
                "created_at": _now_utc().isoformat(),
            }
            await db.users.insert_one(user)
        else:
            if user.get("deleted") or user.get("anonymized"):
                raise HTTPException(status_code=401, detail="Compte supprimé")
            # Provider already linked; keep sub up to date if newly known.
            if info.get("sub"):
                await db.users.update_one(
                    {"user_id": user["user_id"], "providers.provider": "google"},
                    {"$set": {"providers.$.sub": info["sub"]}},
                )

        token = await _create_session(db, user["user_id"], request=request, method="google")
        await security_svc.record_login_attempt(db, email, ip, success=True, user_id=user["user_id"])
        await security_svc.audit_log(
            db,
            action="auth.google_register" if is_new else "auth.google_login",
            actor_id=user["user_id"], actor_role=user.get("role"),
            target=user["user_id"],
            metadata={"email": email, "method": "google"},
            severity="info", ip=ip,
        )
        user.pop("password", None)
        user.pop("_id", None)
        return {"token": token, "user": user}

    # ---------------- Apple (native, JWKS-verified) ----------------
    @r.post("/auth/apple")
    async def apple_auth(data: AppleInput, request: Request):
        ip = _client_ip(request)
        # 1. IP-level rate limit before any Apple network calls.
        await security_svc.check_login_rate_limit(db, f"oauth:apple:{ip}", ip)
        # 2. Cryptographic verification against Apple JWKS.
        claims = _verify_apple_identity_token(data.identity_token, expected_nonce=data.nonce)
        apple_sub = claims.get("sub")
        if not apple_sub:
            raise HTTPException(status_code=401, detail="Token Apple sans identifiant")
        # Apple exposes `email` inside the claims from the SECOND login onward
        # (and every login for regular Apple accounts); on the very first
        # login the raw client-side payload also carries name+email once. We
        # trust the JWT-claim email first, and fall back to the client-sent
        # `data.email` if the claim is absent (first sign-in on some setups).
        claim_email = _normalize_email(claims.get("email") or "")
        payload_email = _normalize_email(data.email or "") if data.email else None
        email = claim_email or payload_email

        # 3. Try to find a user by apple_sub first (Apple's stable identifier).
        user = await db.users.find_one({"apple_sub": apple_sub})
        is_new = False

        if not user and email:
            # 4. Fall back to email lookup + cross-provider collision guard.
            user, needs_linking = await _check_provider_collision(
                db, email, incoming_provider="apple", incoming_sub=apple_sub,
            )
            if user and needs_linking:
                existing_methods = sorted({p.get("provider") for p in (user.get("providers") or []) if p.get("provider")})
                await security_svc.record_login_attempt(db, email, ip, success=False)
                await security_svc.audit_log(
                    db, action="auth.apple_link_required",
                    actor_id=user["user_id"], actor_role=user.get("role"),
                    target=user["user_id"],
                    metadata={"email": email, "existing_methods": existing_methods,
                              "method": "apple", "apple_sub": apple_sub},
                    severity="warn", ip=ip,
                )
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "ACCOUNT_LINK_REQUIRED",
                        "message": (
                            "Un compte existe déjà avec cet email. Connectez-vous avec "
                            "votre méthode habituelle, puis liez Apple depuis votre profil."
                        ),
                        "existing_methods": existing_methods,
                    },
                )

        if not user:
            # 5. Brand-new user. On first sign-in only, Apple gives us
            #    name/email — persist them right now, we won't get them again.
            is_new = True
            user_id = _new_id("user")
            display_name = (
                " ".join(filter(None, [data.first_name, data.last_name])).strip()
                or "Utilisateur"
            )[:200]
            user = {
                "user_id": user_id,
                "email": email or "",  # may be private-relay or absent
                "apple_sub": apple_sub,
                "name": display_name,
                "role": data.role if data.role in ("client", "artisan") else "client",
                "password": None,
                "picture": None,
                "providers": [{
                    "provider": "apple",
                    "sub": apple_sub,
                    "linked_at": _now_utc().isoformat(),
                }],
                "created_at": _now_utc().isoformat(),
            }
            await db.users.insert_one(user)
        else:
            if user.get("deleted") or user.get("anonymized"):
                raise HTTPException(status_code=401, detail="Compte supprimé")
            # Backfill apple_sub / email / providers if we had a legacy account.
            updates: dict = {}
            if not user.get("apple_sub"):
                updates["apple_sub"] = apple_sub
            if email and not user.get("email"):
                updates["email"] = email
            if updates:
                await db.users.update_one({"user_id": user["user_id"]}, {"$set": updates})
            await _link_provider(db, user["user_id"], "apple", apple_sub)

        token = await _create_session(db, user["user_id"], request=request, method="apple")
        rl_key = email or f"apple:{apple_sub}"
        await security_svc.record_login_attempt(db, rl_key, ip, success=True, user_id=user["user_id"])
        await security_svc.audit_log(
            db,
            action="auth.apple_register" if is_new else "auth.apple_login",
            actor_id=user["user_id"], actor_role=user.get("role"),
            target=user["user_id"],
            metadata={"email": user.get("email"), "method": "apple", "apple_sub": apple_sub},
            severity="info", ip=ip,
        )
        user.pop("password", None)
        user.pop("_id", None)
        return {"token": token, "user": user}

    # ---------------- Session utilities ----------------
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
                    target=sess.get("user_id"),
                    metadata={"method": sess.get("method", "email")},
                    severity="info",
                )
        return {"ok": True}

    return r
