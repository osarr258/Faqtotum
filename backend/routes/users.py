"""User self-service routes — Sprint 14 Phase 1 Bloc 2.

Migrated endpoints (from server.py lines 4082-4187):
- PATCH  /api/users/me
- GET    /api/users/me/notifications
- POST   /api/users/me/notifications
- GET    /api/users/me/payment-methods
- POST   /api/users/me/payment-methods
- DELETE /api/users/me/payment-methods/{pm_id}
- POST   /api/users/me/payment-methods/{pm_id}/default

Also exposes a small ROLES catalog endpoint kept aligned with the RBAC
declarations in services/security.py, so the front-end no longer has to
duplicate the list.

Ownership contract
------------------
Every write is scoped by `user_id = current_user.user_id`. Users can NEVER
touch a payment method or notification pref belonging to somebody else,
even by guessing the pm_id. This is enforced by the composite `{pm_id,
user_id}` filter on all `payment_methods` operations.
"""
from __future__ import annotations
from typing import Optional
from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, validator

from services import security as security_svc


# ---------------------------------------------------------------------------
# Pydantic input models — strict length / value constraints
# ---------------------------------------------------------------------------

class UserUpdateInput(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=32)
    picture: Optional[str] = Field(None, max_length=2_000_000)  # allow base64
    address: Optional[str] = Field(None, max_length=240)
    city: Optional[str] = Field(None, max_length=80)
    postal_code: Optional[str] = Field(None, max_length=16)

    @validator("phone")
    def _clean_phone(cls, v: Optional[str]) -> Optional[str]:  # noqa: N805
        if v is None:
            return v
        v = v.strip()
        # Basic sanitize: only digits, +, spaces, dashes, parentheses
        for ch in v:
            if not (ch.isdigit() or ch in "+ -()."):
                raise ValueError("Format de téléphone invalide")
        return v


class NotifPrefsInput(BaseModel):
    push_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    sms_enabled: Optional[bool] = None
    marketing: Optional[bool] = None
    intervention_updates: Optional[bool] = None
    new_bookings: Optional[bool] = None


class PaymentMethodInput(BaseModel):
    brand: str = Field(..., max_length=32)
    last4: str = Field(..., min_length=1, max_length=8)
    exp_month: Optional[int] = Field(None, ge=1, le=12)
    exp_year: Optional[int] = Field(None, ge=2020, le=2100)
    is_default: Optional[bool] = False

    @validator("brand")
    def _brand_lower(cls, v: str) -> str:  # noqa: N805
        allowed = {
            "visa", "mastercard", "amex", "discover", "apple_pay",
            "google_pay", "paypal", "sepa", "cb", "carte", "other",
        }
        v = (v or "").strip().lower()
        if v not in allowed:
            v = "other"
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------

def build_users_router(db, get_current_user):
    """Return the users router bound to the given Motor db + auth dep."""
    r = APIRouter(prefix="/users")

    @r.patch("/me")
    async def update_me(data: UserUpdateInput, user=Depends(get_current_user)):
        update = {k: v for k, v in data.dict(exclude_none=True).items()}
        if not update:
            return {"ok": True, "updated": 0}
        # Whitelist of fields (defense in depth) — model already restricts
        allowed = {"name", "phone", "picture", "address", "city", "postal_code"}
        update = {k: v for k, v in update.items() if k in allowed}
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": update})
        await security_svc.audit_log(
            db, action="user.profile_updated", actor_id=user["user_id"],
            target=user["user_id"], metadata={"fields": sorted(update.keys())},
            severity="info",
        )
        new_user = await db.users.find_one(
            {"user_id": user["user_id"]}, {"_id": 0, "password": 0},
        )
        return {"ok": True, "user": new_user}

    # ----- Notifications preferences -----
    @r.get("/me/notifications")
    async def get_notif_prefs(user=Depends(get_current_user)):
        doc = await db.notif_prefs.find_one({"user_id": user["user_id"]}, {"_id": 0})
        return doc or {
            "user_id": user["user_id"],
            "push_enabled": True,
            "email_enabled": True,
            "sms_enabled": False,
            "marketing": False,
            "intervention_updates": True,
            "new_bookings": True,
        }

    @r.post("/me/notifications")
    async def set_notif_prefs(data: NotifPrefsInput, user=Depends(get_current_user)):
        update = {k: v for k, v in data.dict(exclude_none=True).items()}
        update["user_id"] = user["user_id"]
        update["updated_at"] = _now_utc().isoformat()
        await db.notif_prefs.update_one(
            {"user_id": user["user_id"]}, {"$set": update}, upsert=True,
        )
        return update

    # ----- Payment methods (ownership: user_id ALWAYS in the filter) -----
    @r.get("/me/payment-methods")
    async def list_payment_methods(user=Depends(get_current_user)):
        cursor = db.payment_methods.find(
            {"user_id": user["user_id"]}, {"_id": 0},
        ).sort("created_at", -1)
        methods = await cursor.to_list(20)
        return {"methods": methods}

    @r.post("/me/payment-methods")
    async def add_payment_method(
        data: PaymentMethodInput, user=Depends(get_current_user),
    ):
        pm_id = _new_id("pm")
        doc = {
            "pm_id": pm_id,
            "user_id": user["user_id"],
            "brand": data.brand,
            "last4": data.last4[-4:],
            "exp_month": data.exp_month,
            "exp_year": data.exp_year,
            "is_default": bool(data.is_default),
            "created_at": _now_utc().isoformat(),
        }
        if doc["is_default"]:
            await db.payment_methods.update_many(
                {"user_id": user["user_id"]}, {"$set": {"is_default": False}},
            )
        await db.payment_methods.insert_one(dict(doc))
        doc.pop("_id", None)
        await security_svc.audit_log(
            db, action="pm.created", actor_id=user["user_id"], target=pm_id,
            metadata={"brand": doc["brand"], "last4": doc["last4"]}, severity="info",
        )
        return doc

    @r.delete("/me/payment-methods/{pm_id}")
    async def delete_payment_method(pm_id: str, user=Depends(get_current_user)):
        # Composite filter enforces ownership — cannot delete someone else's pm
        result = await db.payment_methods.delete_one(
            {"pm_id": pm_id, "user_id": user["user_id"]},
        )
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Introuvable")
        await security_svc.audit_log(
            db, action="pm.deleted", actor_id=user["user_id"], target=pm_id,
            severity="warn",
        )
        return {"ok": True}

    @r.post("/me/payment-methods/{pm_id}/default")
    async def set_default_payment_method(
        pm_id: str, user=Depends(get_current_user),
    ):
        pm = await db.payment_methods.find_one(
            {"pm_id": pm_id, "user_id": user["user_id"]},
        )
        if not pm:
            # 404 — do NOT leak whether a foreign pm_id exists
            raise HTTPException(status_code=404, detail="Introuvable")
        await db.payment_methods.update_many(
            {"user_id": user["user_id"]}, {"$set": {"is_default": False}},
        )
        await db.payment_methods.update_one(
            {"pm_id": pm_id, "user_id": user["user_id"]},
            {"$set": {"is_default": True}},
        )
        return {"ok": True}

    return r
