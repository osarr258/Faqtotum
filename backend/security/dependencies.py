"""FastAPI dependency injection helpers for authentication and authorization.

All route modules should import from here — never redefine `get_current_user`.
This is the single source of truth for identity resolution.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Callable

from fastapi import Depends, Header, HTTPException, Request

from services import security as security_svc


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def get_db_dependency(db_ref):
    """Factory returning `get_current_user` bound to a specific Motor db.

    Motor clients are instantiated once in server.py at boot. We inject the db
    here so that route modules stay agnostic of the connection setup.
    """

    async def get_current_user(
        authorization: Optional[str] = Header(None),
        request: Request = None,
    ):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Non authentifié")
        token = authorization.split(" ", 1)[1]
        session = await db_ref.user_sessions.find_one({"session_token": token}, {"_id": 0})
        if not session:
            raise HTTPException(status_code=401, detail="Session invalide")
        if session.get("revoked"):
            raise HTTPException(status_code=401, detail="Session révoquée")
        expires = session["expires_at"]
        if isinstance(expires, str):
            expires = datetime.fromisoformat(expires)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < _now_utc():
            raise HTTPException(status_code=401, detail="Session expirée")
        user = await db_ref.users.find_one({"user_id": session["user_id"]}, {"_id": 0, "password": 0})
        if not user:
            raise HTTPException(status_code=401, detail="Utilisateur introuvable")
        if user.get("deleted") or user.get("anonymized"):
            raise HTTPException(status_code=401, detail="Compte supprimé")
        try:
            await security_svc.touch_session(db_ref, token)
        except Exception:  # noqa: BLE001 — touch is best-effort
            pass
        user["_current_token"] = token
        return user

    def require_roles(*allowed_roles: str) -> Callable:
        """RBAC dependency factory. `super_admin` is always allowed."""

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

    return get_current_user, require_roles
