"""Ownership guards — reusable resource-level authorization checks.

Each helper returns the resource dict if the user owns it, raises 403/404 otherwise.
This file centralizes the pattern so no route implements its own auth logic.
"""
from __future__ import annotations
from typing import Any, Dict
from fastapi import HTTPException


async def get_owned_property(db, property_id: str, user_id: str) -> Dict[str, Any]:
    p = await db.properties.find_one({"property_id": property_id, "user_id": user_id}, {"_id": 0})
    if not p:
        # Do NOT leak existence — same 404 for both "not found" and "not yours".
        raise HTTPException(status_code=404, detail="Bien introuvable")
    return p


async def get_owned_booking(db, booking_id: str, user_id: str) -> Dict[str, Any]:
    b = await db.bookings.find_one({"booking_id": booking_id}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Réservation introuvable")
    if b.get("client_id") != user_id and b.get("artisan_user_id") != user_id:
        raise HTTPException(status_code=404, detail="Réservation introuvable")
    return b


async def get_owned_intervention(db, iv_id: str, user_id: str) -> Dict[str, Any]:
    iv = await db.interventions.find_one({"intervention_id": iv_id}, {"_id": 0})
    if not iv:
        raise HTTPException(status_code=404, detail="Intervention introuvable")
    if iv.get("client_id") != user_id and iv.get("artisan_user_id") != user_id:
        raise HTTPException(status_code=404, detail="Intervention introuvable")
    return iv


async def get_owned_mission(db, mission_id: str, user_id: str) -> Dict[str, Any]:
    m = await db.missions.find_one({"mission_id": mission_id}, {"_id": 0})
    if not m:
        raise HTTPException(status_code=404, detail="Mission introuvable")
    if m.get("client_id") != user_id and m.get("artisan_user_id") != user_id:
        raise HTTPException(status_code=404, detail="Mission introuvable")
    return m


async def get_owned_artisan_profile(db, artisan_id: str, user_id: str) -> Dict[str, Any]:
    a = await db.artisan_profiles.find_one({"artisan_id": artisan_id, "user_id": user_id}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Profil artisan introuvable")
    return a


async def get_owned_conversation(db, conversation_id: str, user_id: str) -> Dict[str, Any]:
    c = await db.conversations.find_one({"conversation_id": conversation_id}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    if user_id not in (c.get("client_id"), c.get("artisan_user_id")):
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    return c
