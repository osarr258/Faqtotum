"""
Security Service — Sprint 8
============================
Handles:
- Enhanced session management with device tracking
- RBAC (Role-Based Access Control) with 9 roles
- Immutable audit logs (hash-chained)
- Rate limiting / brute-force detection
- GDPR (data export & soft-delete/anonymization)
- MFA & Biometrics architecture (stubs)
- IoT trust preparation
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from fastapi import Header, HTTPException, Request, Depends


# ---------------------------------------------------------------
# Roles & Permissions
# ---------------------------------------------------------------
ROLES = {
    "client": {"weight": 10, "label": "Client"},
    "artisan": {"weight": 20, "label": "Artisan"},
    "enterprise_owner": {"weight": 40, "label": "Propriétaire Entreprise"},
    "enterprise_manager": {"weight": 35, "label": "Manager Entreprise"},
    "technician": {"weight": 25, "label": "Technicien"},
    "moderator": {"weight": 50, "label": "Modérateur"},
    "admin": {"weight": 80, "label": "Administrateur"},
    "super_admin": {"weight": 100, "label": "Super Administrateur"},
    "system": {"weight": 999, "label": "Système"},
}

ALL_ROLES = list(ROLES.keys())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


# ---------------------------------------------------------------
# Session Management
# ---------------------------------------------------------------
def parse_device_info(user_agent: str, ip: str) -> Dict[str, str]:
    """Extract lightweight device fingerprint (no external deps)."""
    ua = (user_agent or "").lower()
    if "iphone" in ua or "ipad" in ua:
        device = "iOS"
    elif "android" in ua:
        device = "Android"
    elif "macintosh" in ua or "mac os" in ua:
        device = "macOS"
    elif "windows" in ua:
        device = "Windows"
    elif "linux" in ua:
        device = "Linux"
    else:
        device = "Inconnu"

    if "chrome" in ua and "edg" not in ua:
        browser = "Chrome"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    elif "firefox" in ua:
        browser = "Firefox"
    elif "edg" in ua:
        browser = "Edge"
    elif "expo" in ua or "okhttp" in ua:
        browser = "App Native"
    else:
        browser = "Autre"

    return {
        "device": device,
        "browser": browser,
        "user_agent": (user_agent or "")[:300],
        "ip": ip or "unknown",
    }


async def create_secure_session(
    db, user_id: str, request: Optional[Request] = None, days: int = 7
) -> Dict[str, Any]:
    """Create a secure session with device fingerprinting."""
    token = secrets.token_urlsafe(48)
    ua = ""
    ip = "unknown"
    if request:
        ua = request.headers.get("user-agent", "")
        ip = request.client.host if request.client else "unknown"
        # Handle proxy forwarding
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            ip = fwd.split(",")[0].strip()
    device = parse_device_info(ua, ip)

    session = {
        "session_token": token,
        "user_id": user_id,
        "device": device["device"],
        "browser": device["browser"],
        "user_agent": device["user_agent"],
        "ip": device["ip"],
        "created_at": now_iso(),
        "last_seen_at": now_iso(),
        "expires_at": (now_utc() + timedelta(days=days)).isoformat(),
        "revoked": False,
    }
    await db.user_sessions.insert_one(session)
    return {"token": token, "session_id": token[:12], **device}


async def list_user_sessions(db, user_id: str) -> List[Dict[str, Any]]:
    cursor = db.user_sessions.find(
        {"user_id": user_id, "revoked": {"$ne": True}}, {"_id": 0}
    ).sort("last_seen_at", -1)
    sessions = await cursor.to_list(200)
    for s in sessions:
        s["session_id"] = s.get("session_token", "")[:12]
        s.pop("session_token", None)  # Never expose full token
    return sessions


async def revoke_session(db, user_id: str, session_id_prefix: str) -> bool:
    """Revoke a session by its truncated id (first 12 chars)."""
    session = await db.user_sessions.find_one({
        "user_id": user_id,
        "session_token": {"$regex": f"^{session_id_prefix}"},
    })
    if not session:
        return False
    await db.user_sessions.update_one(
        {"session_token": session["session_token"]},
        {"$set": {"revoked": True, "revoked_at": now_iso()}},
    )
    return True


async def revoke_all_sessions_except(db, user_id: str, current_token: str) -> int:
    result = await db.user_sessions.update_many(
        {"user_id": user_id, "session_token": {"$ne": current_token}, "revoked": {"$ne": True}},
        {"$set": {"revoked": True, "revoked_at": now_iso()}},
    )
    return result.modified_count


async def touch_session(db, token: str) -> None:
    """Update last_seen timestamp — call on each authenticated request."""
    await db.user_sessions.update_one(
        {"session_token": token},
        {"$set": {"last_seen_at": now_iso()}},
    )


# ---------------------------------------------------------------
# RBAC — Role-Based Access Control
# ---------------------------------------------------------------
def has_role(user: dict, required: List[str]) -> bool:
    if not user:
        return False
    role = user.get("role", "client")
    return role in required or role in ("super_admin",)


def has_min_weight(user: dict, min_weight: int) -> bool:
    if not user:
        return False
    role = user.get("role", "client")
    return ROLES.get(role, {}).get("weight", 0) >= min_weight


# ---------------------------------------------------------------
# Rate Limiting / Brute Force Protection
# ---------------------------------------------------------------
async def check_login_rate_limit(db, email: str, ip: str) -> None:
    """
    Deny if > 5 failed attempts for the SAME email in last 15 min,
    OR > 30 failed attempts across DIFFERENT emails from the same IP (distributed brute-force).
    Raises HTTPException(429) if limit exceeded.
    """
    cutoff = (now_utc() - timedelta(minutes=15)).isoformat()
    count_email = await db.login_attempts.count_documents({
        "email": email.lower(),
        "success": False,
        "created_at": {"$gte": cutoff},
    })
    if count_email >= 5:
        raise HTTPException(
            status_code=429,
            detail="Trop de tentatives de connexion. Réessayez dans quelques minutes.",
        )
    # Distributed pattern: many different emails from same IP
    if ip and ip != "unknown" and not ip.startswith("127.") and ip != "localhost":
        distinct_emails = await db.login_attempts.distinct("email", {
            "ip": ip,
            "success": False,
            "created_at": {"$gte": cutoff},
        })
        if len(distinct_emails) >= 30:
            raise HTTPException(
                status_code=429,
                detail="Trop de tentatives suspectes depuis votre réseau. Réessayez plus tard.",
            )


async def record_login_attempt(
    db, email: str, ip: str, success: bool, user_id: Optional[str] = None
) -> None:
    await db.login_attempts.insert_one({
        "attempt_id": f"la_{uuid.uuid4().hex[:12]}",
        "email": email.lower(),
        "ip": ip or "unknown",
        "success": success,
        "user_id": user_id,
        "created_at": now_iso(),
    })


# ---------------------------------------------------------------
# Immutable Audit Log (hash-chained)
# ---------------------------------------------------------------
async def _last_audit_hash(db) -> str:
    last = await db.audit_logs.find_one({}, sort=[("seq", -1)])
    return last.get("hash", "GENESIS") if last else "GENESIS"


async def _next_seq(db) -> int:
    last = await db.audit_logs.find_one({}, sort=[("seq", -1)])
    return (last.get("seq", 0) + 1) if last else 1


async def audit_log(
    db,
    action: str,
    actor_id: Optional[str] = None,
    actor_role: Optional[str] = None,
    target: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    severity: str = "info",
    ip: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Append a hash-chained immutable log entry.
    severity: info | warn | critical
    """
    prev_hash = await _last_audit_hash(db)
    seq = await _next_seq(db)
    entry = {
        "log_id": f"al_{uuid.uuid4().hex[:12]}",
        "seq": seq,
        "prev_hash": prev_hash,
        "action": action,
        "actor_id": actor_id,
        "actor_role": actor_role,
        "target": target,
        "metadata": metadata or {},
        "severity": severity,
        "ip": ip,
        "created_at": now_iso(),
    }
    # Compute hash over canonical json (excluding hash field)
    payload = json.dumps(entry, sort_keys=True, default=str)
    entry["hash"] = hashlib.sha256(payload.encode()).hexdigest()
    await db.audit_logs.insert_one(entry.copy())
    entry.pop("_id", None)
    return entry


async def list_audit_logs(
    db,
    actor_id: Optional[str] = None,
    action: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if actor_id:
        q["actor_id"] = actor_id
    if action:
        q["action"] = action
    if severity:
        q["severity"] = severity
    cursor = db.audit_logs.find(q, {"_id": 0}).sort("seq", -1).limit(limit)
    return await cursor.to_list(limit)


async def verify_audit_chain(db, sample: int = 200) -> Dict[str, Any]:
    """Verify hash chain integrity across the last `sample` entries."""
    cursor = db.audit_logs.find({}, {"_id": 0}).sort("seq", 1)
    entries = await cursor.to_list(sample)
    broken: List[int] = []
    prev = "GENESIS"
    for e in entries:
        if e.get("prev_hash") != prev:
            broken.append(e.get("seq"))
        # Recompute hash
        h = e.pop("hash", None)
        payload = json.dumps(e, sort_keys=True, default=str)
        expected = hashlib.sha256(payload.encode()).hexdigest()
        if h != expected:
            broken.append(e.get("seq"))
        prev = h or prev
    return {
        "total": len(entries),
        "broken_entries": broken,
        "integrity_ok": len(broken) == 0,
    }


# ---------------------------------------------------------------
# GDPR / RGPD — Data Export & Anonymization
# ---------------------------------------------------------------
GDPR_COLLECTIONS = [
    "users",
    "artisan_profiles",
    "bookings",
    "reviews",
    "conversations",
    "messages",
    "properties",
    "equipment",
    "documents",
    "concierge_sessions",
    "missions",
    "loyalty_points",
    "referrals",
    "work_orders",
    "organizations",
    "notifications",
]


async def export_user_data(db, user_id: str) -> Dict[str, Any]:
    """Aggregate all user-linked data across collections."""
    export: Dict[str, Any] = {
        "user_id": user_id,
        "exported_at": now_iso(),
        "version": "1.0",
        "collections": {},
    }
    for coll_name in GDPR_COLLECTIONS:
        coll = db[coll_name]
        # Try multiple common key fields
        docs: List[Dict] = []
        for key in ("user_id", "client_id", "artisan_id", "actor_id", "owner_id"):
            cursor = coll.find({key: user_id}, {"_id": 0}).limit(500)
            found = await cursor.to_list(500)
            if found:
                for d in found:
                    if d not in docs:
                        docs.append(d)
        export["collections"][coll_name] = docs
    return export


async def anonymize_user(db, user_id: str) -> Dict[str, Any]:
    """
    Soft-delete: anonymize PII but preserve foreign keys for legal audit trail.
    Logs kept for 30 days.
    """
    anon_email = f"anonymized_{uuid.uuid4().hex[:8]}@deleted.auxora.local"
    changes = 0

    # Users
    result = await db.users.update_one(
        {"user_id": user_id},
        {"$set": {
            "email": anon_email,
            "name": "Utilisateur supprimé",
            "picture": None,
            "phone": None,
            "password": None,
            "deleted": True,
            "deleted_at": now_iso(),
            "anonymized": True,
        }},
    )
    changes += result.modified_count

    # Revoke all sessions
    await db.user_sessions.update_many(
        {"user_id": user_id},
        {"$set": {"revoked": True, "revoked_at": now_iso()}},
    )

    # Anonymize artisan profile
    await db.artisan_profiles.update_one(
        {"user_id": user_id},
        {"$set": {
            "title": "Profil supprimé",
            "bio": "",
            "phone": None,
            "photo": None,
            "available": False,
        }},
    )

    # Anonymize sent messages content (keep metadata)
    await db.messages.update_many(
        {"sender_id": user_id},
        {"$set": {"content": "[Message supprimé]", "anonymized": True}},
    )

    # Schedule log-purge marker (audit_logs kept 30 days from now)
    await db.gdpr_deletions.insert_one({
        "gdpr_id": f"gdpr_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "deleted_at": now_iso(),
        "logs_purge_after": (now_utc() + timedelta(days=30)).isoformat(),
        "status": "completed",
    })

    return {
        "user_id": user_id,
        "anonymized": True,
        "deleted_at": now_iso(),
        "logs_retention_days": 30,
        "changes_applied": changes,
    }


# ---------------------------------------------------------------
# MFA / Biometrics — RFC 6238 TOTP
# ---------------------------------------------------------------
#
# Secrets are stored ENCRYPTED at rest with Fernet (symmetric AES-128-CBC + HMAC).
# The key is read from `MFA_ENCRYPTION_KEY` (urlsafe base64, 32 bytes).
# - In production, this MUST be set explicitly; otherwise we fail-closed.
# - In development, we derive a stable ephemeral key from a well-known
#   placeholder so tests remain deterministic (the placeholder key is NOT
#   secret — it must never be used to store real secrets).
_MFA_ISSUER = "Faqtotum"


def _get_mfa_fernet():
    """Return a Fernet instance for encrypting/decrypting MFA secrets."""
    from cryptography.fernet import Fernet
    key = os.environ.get("MFA_ENCRYPTION_KEY", "").strip()
    app_env = os.environ.get("APP_ENV", "development").strip().lower()
    if not key:
        if app_env == "production":
            raise HTTPException(
                status_code=500,
                detail="MFA_ENCRYPTION_KEY manquante en production",
            )
        # Dev/test only — deterministic ephemeral key.
        key = base64.urlsafe_b64encode(
            hashlib.sha256(b"faqtotum-dev-mfa-ephemeral-key").digest()
        ).decode()
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MFA_ENCRYPTION_KEY invalide: {e}")


def _encrypt_secret(secret_b32: str) -> str:
    return _get_mfa_fernet().encrypt(secret_b32.encode()).decode()


def _decrypt_secret(ciphertext: str) -> str:
    return _get_mfa_fernet().decrypt(ciphertext.encode()).decode()


async def mfa_status(db, user_id: str) -> Dict[str, Any]:
    doc = await db.mfa_settings.find_one({"user_id": user_id}, {"_id": 0})
    if not doc:
        return {
            "user_id": user_id,
            "enabled": False,
            "method": None,
            "biometrics_enrolled": False,
            "backup_codes_remaining": 0,
        }
    # Never expose the encrypted secret to callers.
    doc.pop("secret_pending_enc", None)
    doc.pop("secret_enc", None)
    return doc


async def mfa_prepare(db, user_id: str, method: str = "totp") -> Dict[str, Any]:
    """
    Prepare MFA enrollment with a fresh TOTP secret (RFC 6238).

    - Generates a 160-bit base32 secret via `pyotp.random_base32()`.
    - Encrypts the secret at rest with Fernet.
    - Returns the plaintext secret + provisioning URI (`otpauth://…`)
      ONLY during enrollment so the client can display a QR code and
      the user can register the account in their authenticator app.
    """
    import pyotp
    if method not in ("totp", "sms", "biometrics"):
        raise HTTPException(status_code=400, detail="Méthode MFA non supportée")
    if method != "totp":
        raise HTTPException(
            status_code=400,
            detail="Seule la méthode TOTP est supportée en V1",
        )
    secret_b32 = pyotp.random_base32()
    provisioning_uri = pyotp.TOTP(secret_b32).provisioning_uri(
        name=user_id, issuer_name=_MFA_ISSUER
    )
    await db.mfa_settings.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "method": method,
            "secret_pending_enc": _encrypt_secret(secret_b32),
            "enabled": False,
            "prepared_at": now_iso(),
        },
         "$unset": {"secret_pending": ""}},  # remove any old plaintext leftover
        upsert=True,
    )
    return {
        "method": method,
        "secret": secret_b32,
        "provisioning_uri": provisioning_uri,
        "issuer": _MFA_ISSUER,
        "status": "prepared",
    }


def _totp_verify(secret_b32: str, code: str, valid_window: int = 1) -> bool:
    """Verify a 6-digit TOTP code with ±1 period tolerance (default)."""
    import pyotp
    if not code or len(code) != 6 or not code.isdigit():
        return False
    return pyotp.TOTP(secret_b32).verify(code, valid_window=valid_window)


async def mfa_verify_stub(db, user_id: str, code: str) -> Dict[str, Any]:
    """
    Verify an MFA code.

    Priority:
    1. If there is a pending or active TOTP secret → verify the 6-digit code
       against pyotp with a ±1 period window (RFC 6238, standard tolerance
       for clock drift). On success, promote `secret_pending_enc` → `secret_enc`
       and flip `enabled=True`.
    2. Otherwise (no secret enrolled) fall back to the demo bypass — but only
       when BOTH `MFA_DEMO_MODE=true` AND `APP_ENV != production`.
       In every other configuration, the demo bypass is closed.

    Demo mode is intended solely for automated tests and preview builds where
    setting up a real authenticator app is impractical. Real users always go
    through the real TOTP flow.
    """
    doc = await db.mfa_settings.find_one({"user_id": user_id}) or {}
    enc = doc.get("secret_pending_enc") or doc.get("secret_enc")
    if enc:
        try:
            secret_b32 = _decrypt_secret(enc)
        except Exception:
            raise HTTPException(status_code=500, detail="Secret MFA corrompu")
        if _totp_verify(secret_b32, code, valid_window=1):
            # Promote pending → active on first successful verification.
            update = {"$set": {"enabled": True, "activated_at": now_iso()}}
            if doc.get("secret_pending_enc"):
                update["$set"]["secret_enc"] = doc["secret_pending_enc"]
                update["$unset"] = {"secret_pending_enc": ""}
            await db.mfa_settings.update_one({"user_id": user_id}, update)
            return {"ok": True, "enabled": True, "message": "MFA activée"}
        # Real secret exists but code is wrong — no fallback to demo mode.
        raise HTTPException(status_code=400, detail="Code MFA invalide")

    # No enrolled secret → demo bypass ONLY in dev + explicit flag.
    demo_enabled = (
        os.environ.get("MFA_DEMO_MODE", "").strip().lower() == "true"
        and os.environ.get("APP_ENV", "development").strip().lower() != "production"
    )
    if demo_enabled and code == "000000":
        await db.mfa_settings.update_one(
            {"user_id": user_id},
            {"$set": {
                "user_id": user_id,
                "method": "totp",
                "enabled": True,
                "activated_at": now_iso(),
                "demo_mode": True,
            }},
            upsert=True,
        )
        return {"ok": True, "enabled": True, "message": "MFA activée (mode démo)"}
    raise HTTPException(status_code=400, detail="Code MFA invalide")


async def mfa_disable(db, user_id: str) -> Dict[str, Any]:
    await db.mfa_settings.update_one(
        {"user_id": user_id},
        {"$set": {"enabled": False, "disabled_at": now_iso()},
         "$unset": {"secret_enc": "", "secret_pending_enc": ""}},
    )
    return {"enabled": False}


async def biometrics_register(db, user_id: str, device_id: str, public_key: str) -> Dict[str, Any]:
    """Register a device biometric public key (architecture stub)."""
    entry = {
        "biometric_id": f"bio_{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "device_id": device_id,
        "public_key": public_key[:512],
        "created_at": now_iso(),
        "active": True,
    }
    await db.biometric_credentials.insert_one(entry)
    entry.pop("_id", None)
    return entry


# ---------------------------------------------------------------
# Security Score (per user)
# ---------------------------------------------------------------
async def compute_security_score(db, user_id: str) -> Dict[str, Any]:
    """Compute a security posture score for the Security Center."""
    score = 40  # base
    factors: List[Dict[str, Any]] = []

    user = await db.users.find_one({"user_id": user_id}, {"_id": 0}) or {}
    if user.get("password"):
        score += 15
        factors.append({"label": "Mot de passe défini", "delta": 15, "ok": True})
    else:
        factors.append({"label": "Mot de passe absent (Google)", "delta": 0, "ok": True})

    mfa = await db.mfa_settings.find_one({"user_id": user_id, "enabled": True})
    if mfa:
        score += 25
        factors.append({"label": "MFA activée", "delta": 25, "ok": True})
    else:
        factors.append({"label": "MFA non activée", "delta": 0, "ok": False})

    bio = await db.biometric_credentials.find_one({"user_id": user_id, "active": True})
    if bio:
        score += 10
        factors.append({"label": "Biométrie enrôlée", "delta": 10, "ok": True})
    else:
        factors.append({"label": "Biométrie non configurée", "delta": 0, "ok": False})

    active_sessions = await db.user_sessions.count_documents({
        "user_id": user_id, "revoked": {"$ne": True},
    })
    if active_sessions <= 3:
        score += 10
        factors.append({"label": f"{active_sessions} sessions actives", "delta": 10, "ok": True})
    else:
        factors.append({"label": f"{active_sessions} sessions actives (élevé)", "delta": 0, "ok": False})

    score = min(100, score)
    level = "faible"
    if score >= 80:
        level = "excellent"
    elif score >= 60:
        level = "bon"
    elif score >= 40:
        level = "moyen"

    return {
        "score": score,
        "level": level,
        "factors": factors,
        "computed_at": now_iso(),
    }
