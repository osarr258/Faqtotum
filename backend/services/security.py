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
import hashlib
import json
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
# MFA / Biometrics (Architecture stubs)
# ---------------------------------------------------------------
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
    return doc


async def mfa_prepare(db, user_id: str, method: str = "totp") -> Dict[str, Any]:
    """
    Prepare MFA enrollment (stub). Full TOTP with pyotp will be added later.
    Returns a placeholder secret + provisioning URI structure.
    """
    if method not in ("totp", "sms", "biometrics"):
        raise HTTPException(status_code=400, detail="Méthode MFA non supportée")
    secret_placeholder = secrets.token_hex(16).upper()
    await db.mfa_settings.update_one(
        {"user_id": user_id},
        {"$set": {
            "user_id": user_id,
            "method": method,
            "secret_pending": secret_placeholder,
            "enabled": False,
            "prepared_at": now_iso(),
        }},
        upsert=True,
    )
    return {
        "method": method,
        "secret": secret_placeholder,
        "provisioning_uri": f"otpauth://totp/Auxora:{user_id}?secret={secret_placeholder}&issuer=Auxora",
        "status": "prepared",
        "note": "Architecture prête — validation TOTP à activer via pyotp dans un prochain sprint.",
    }


async def mfa_verify_stub(db, user_id: str, code: str) -> Dict[str, Any]:
    """Stub verification — accepts '000000' as demo confirmation."""
    if code == "000000":
        await db.mfa_settings.update_one(
            {"user_id": user_id},
            {"$set": {"enabled": True, "activated_at": now_iso()}},
        )
        return {"ok": True, "enabled": True, "message": "MFA activée (mode démo)"}
    raise HTTPException(status_code=400, detail="Code invalide (démo: 000000)")


async def mfa_disable(db, user_id: str) -> Dict[str, Any]:
    await db.mfa_settings.update_one(
        {"user_id": user_id},
        {"$set": {"enabled": False, "disabled_at": now_iso()}},
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
