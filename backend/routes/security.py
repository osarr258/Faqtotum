"""Security & privacy routes — Sprint 14 Phase 1 migration.

Migrated endpoints (from server.py lines 3627-3862):
- /api/security/overview
- /api/security/sessions[/{id}] + revoke-others
- /api/security/password/change
- /api/security/audit[/verify][/all]
- /api/security/gdpr/consents + export + delete
- /api/security/mfa[/prepare][/verify]
- /api/security/biometrics[/register]
- /api/security/roles
- /api/security/admin/sessions
"""
from __future__ import annotations
from typing import Optional
from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from services import security as security_svc


class PasswordChangeInput(BaseModel):
    current_password: str
    new_password: str


class MfaPrepareInput(BaseModel):
    method: str = "totp"


class MfaVerifyInput(BaseModel):
    code: str


class BiometricRegisterInput(BaseModel):
    device_id: str
    public_key: str


class GdprConsentInput(BaseModel):
    marketing: bool = False
    analytics: bool = False
    third_party: bool = False


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False


def _hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def build_security_router(db, get_current_user, require_roles):
    r = APIRouter(prefix="/security")

    # ----- Overview -----
    @r.get("/overview")
    async def security_overview(user=Depends(get_current_user)):
        score = await security_svc.compute_security_score(db, user["user_id"])
        active_sessions = await db.user_sessions.count_documents({
            "user_id": user["user_id"], "revoked": {"$ne": True},
        })
        recent_events = await security_svc.list_audit_logs(db, actor_id=user["user_id"], limit=10)
        mfa = await security_svc.mfa_status(db, user["user_id"])
        return {
            "security_score": score,
            "active_sessions": active_sessions,
            "mfa": mfa,
            "recent_events": recent_events,
        }

    # ----- Sessions Management -----
    @r.get("/sessions")
    async def get_sessions(user=Depends(get_current_user)):
        sessions = await security_svc.list_user_sessions(db, user["user_id"])
        current_token = user.get("_current_token", "")
        current_id = current_token[:12] if current_token else ""
        for s in sessions:
            s["is_current"] = s.get("session_id") == current_id
        return {"sessions": sessions, "total": len(sessions)}

    @r.delete("/sessions/{session_id}")
    async def revoke_session_endpoint(session_id: str, user=Depends(get_current_user)):
        ok = await security_svc.revoke_session(db, user["user_id"], session_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Session introuvable")
        await security_svc.audit_log(
            db, action="session.revoke", actor_id=user["user_id"],
            actor_role=user.get("role"), target=session_id, severity="info",
        )
        return {"ok": True, "revoked": session_id}

    @r.post("/sessions/revoke-others")
    async def revoke_other_sessions(user=Depends(get_current_user)):
        current_token = user.get("_current_token", "")
        count = await security_svc.revoke_all_sessions_except(db, user["user_id"], current_token)
        await security_svc.audit_log(
            db, action="session.revoke_all_others", actor_id=user["user_id"],
            actor_role=user.get("role"), metadata={"count": count}, severity="warn",
        )
        return {"ok": True, "revoked_count": count}

    # ----- Password Change -----
    @r.post("/password/change")
    async def change_password(
        data: PasswordChangeInput,
        request: Request,
        user=Depends(get_current_user),
    ):
        full = await db.users.find_one({"user_id": user["user_id"]})
        if not full or not full.get("password"):
            raise HTTPException(status_code=400, detail="Aucun mot de passe configuré (compte Google?)")
        if not _verify_password(data.current_password, full["password"]):
            await security_svc.audit_log(
                db, action="password.change_failed", actor_id=user["user_id"],
                actor_role=user.get("role"), severity="warn",
            )
            raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect")
        if len(data.new_password) < 8:
            raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit contenir au moins 8 caractères")
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {"password": _hash_password(data.new_password), "password_changed_at": _now_utc().isoformat()}},
        )
        await security_svc.audit_log(
            db, action="password.changed", actor_id=user["user_id"],
            actor_role=user.get("role"), severity="critical",
        )
        return {"ok": True, "message": "Mot de passe modifié"}

    # ----- Audit Logs -----
    @r.get("/audit")
    async def my_audit_logs(user=Depends(get_current_user), limit: int = 50):
        logs = await security_svc.list_audit_logs(db, actor_id=user["user_id"], limit=min(200, max(1, limit)))
        for log in logs:
            log.pop("hash", None)
            log.pop("prev_hash", None)
        return {"logs": logs, "total": len(logs)}

    @r.get("/audit/verify")
    async def audit_chain_verify(user=Depends(require_roles("admin", "super_admin"))):
        return await security_svc.verify_audit_chain(db, sample=500)

    @r.get("/audit/all")
    async def all_audit_logs(
        limit: int = 100,
        action: Optional[str] = None,
        severity: Optional[str] = None,
        user=Depends(require_roles("admin", "super_admin")),
    ):
        logs = await security_svc.list_audit_logs(
            db, action=action, severity=severity, limit=min(500, limit),
        )
        return {"logs": logs, "total": len(logs)}

    # ----- GDPR / RGPD -----
    @r.get("/gdpr/consents")
    async def get_consents(user=Depends(get_current_user)):
        doc = await db.gdpr_consents.find_one({"user_id": user["user_id"]}, {"_id": 0})
        if not doc:
            return {
                "user_id": user["user_id"],
                "marketing": False,
                "analytics": False,
                "third_party": False,
                "updated_at": None,
            }
        return doc

    @r.post("/gdpr/consents")
    async def update_consents(data: GdprConsentInput, user=Depends(get_current_user)):
        doc = {
            "user_id": user["user_id"],
            "marketing": data.marketing,
            "analytics": data.analytics,
            "third_party": data.third_party,
            "updated_at": _now_utc().isoformat(),
        }
        await db.gdpr_consents.update_one(
            {"user_id": user["user_id"]}, {"$set": doc}, upsert=True,
        )
        await security_svc.audit_log(
            db, action="gdpr.consents_updated", actor_id=user["user_id"],
            actor_role=user.get("role"), metadata=doc, severity="info",
        )
        return doc

    @r.get("/gdpr/export")
    async def gdpr_export(user=Depends(get_current_user)):
        data = await security_svc.export_user_data(db, user["user_id"])
        await security_svc.audit_log(
            db, action="gdpr.data_exported", actor_id=user["user_id"],
            actor_role=user.get("role"), severity="critical",
            metadata={"collections": list(data.get("collections", {}).keys())},
        )
        return data

    @r.delete("/gdpr/account")
    async def gdpr_delete_account(user=Depends(get_current_user)):
        result = await security_svc.anonymize_user(db, user["user_id"])
        await security_svc.audit_log(
            db, action="gdpr.account_deleted", actor_id=user["user_id"],
            actor_role=user.get("role"), severity="critical",
            metadata={"logs_retention_days": 30},
        )
        return result

    # ----- MFA -----
    @r.get("/mfa")
    async def get_mfa(user=Depends(get_current_user)):
        return await security_svc.mfa_status(db, user["user_id"])

    @r.post("/mfa/prepare")
    async def prepare_mfa(data: MfaPrepareInput, user=Depends(get_current_user)):
        result = await security_svc.mfa_prepare(db, user["user_id"], method=data.method)
        await security_svc.audit_log(
            db, action="mfa.prepared", actor_id=user["user_id"],
            actor_role=user.get("role"), metadata={"method": data.method}, severity="info",
        )
        return result

    @r.post("/mfa/verify")
    async def verify_mfa(data: MfaVerifyInput, user=Depends(get_current_user)):
        result = await security_svc.mfa_verify_stub(db, user["user_id"], data.code)
        await security_svc.audit_log(
            db, action="mfa.enabled", actor_id=user["user_id"],
            actor_role=user.get("role"), severity="critical",
        )
        return result

    @r.delete("/mfa")
    async def disable_mfa(user=Depends(get_current_user)):
        result = await security_svc.mfa_disable(db, user["user_id"])
        await security_svc.audit_log(
            db, action="mfa.disabled", actor_id=user["user_id"],
            actor_role=user.get("role"), severity="warn",
        )
        return result

    # ----- Biometrics -----
    @r.post("/biometrics/register")
    async def register_biometric(data: BiometricRegisterInput, user=Depends(get_current_user)):
        result = await security_svc.biometrics_register(
            db, user["user_id"], data.device_id, data.public_key,
        )
        await security_svc.audit_log(
            db, action="biometrics.registered", actor_id=user["user_id"],
            actor_role=user.get("role"), metadata={"device_id": data.device_id}, severity="info",
        )
        return result

    @r.get("/biometrics")
    async def list_biometrics(user=Depends(get_current_user)):
        docs = await db.biometric_credentials.find(
            {"user_id": user["user_id"], "active": True}, {"_id": 0, "public_key": 0},
        ).to_list(50)
        return {"devices": docs, "total": len(docs)}

    # ----- Roles -----
    @r.get("/roles")
    async def get_roles(user=Depends(get_current_user)):
        return {
            "current_role": user.get("role"),
            "roles": [
                {"key": k, "label": v["label"], "weight": v["weight"]}
                for k, v in security_svc.ROLES.items()
            ],
        }

    # ----- Admin sessions listing -----
    @r.get("/admin/sessions")
    async def admin_list_sessions(
        user=Depends(require_roles("admin", "super_admin")),
        limit: int = 100,
    ):
        cursor = db.user_sessions.find(
            {"revoked": {"$ne": True}},
            {"_id": 0, "session_token": 0},
        ).sort("last_seen_at", -1).limit(min(500, limit))
        sessions = await cursor.to_list(500)
        return {"sessions": sessions, "total": len(sessions)}

    return r
