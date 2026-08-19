"""FAQTOTUM V1 — Broadcast multi-artisans (accept-first-wins atomique).

Une demande *broadcast* est envoyée par un client à N artisans qualifiés en
même temps. Le premier artisan qui accepte gagne — un booking est créé,
les autres candidats sont notifiés que la demande n'est plus disponible.

Modèle
------
Collection ``booking_broadcasts`` (une entrée par demande) :

    broadcast_id: str
    client_id, client_name: str
    trade: str
    description: str
    date: "YYYY-MM-DD"
    slot: "HH:MM" | "HH:MM-HH:MM"
    urgent: bool
    candidates: [artisan_id]     # les N pros sollicités
    status: "open" | "assigned" | "expired" | "cancelled"
    winner_artisan_id: str|None
    winner_booking_id: str|None
    created_at, expires_at, assigned_at

Endpoints
---------
    POST   /api/broadcasts                # client crée une demande broadcast
    GET    /api/broadcasts/pending        # artisan liste les broadcasts qui le concernent
    POST   /api/broadcasts/{id}/accept    # artisan accepte (atomique)
    POST   /api/broadcasts/{id}/decline   # artisan se retire des candidats
    POST   /api/broadcasts/{id}/cancel    # client annule sa demande

Design
------
* L'accept-first-wins utilise ``find_one_and_update`` avec un filter
  ``status == "open"`` pour garantir qu'un seul artisan gagne, même sous
  forte contention (course frontale).
* Le broadcast expire automatiquement au-delà de ``expires_at`` (60 min
  par défaut). L'expiration est déclenchée par une lecture — pas de tâche
  cron nécessaire pour V1.
* Le sélecteur de candidats utilise ``services.matching.rank`` avec un
  contexte minimaliste (trade + urgency). On prend le TOP 5.
* Pour éviter d'exposer l'ID d'un artisan à d'autres artisans, la liste
  ``candidates`` n'est visible que dans les logs d'audit — jamais dans
  la réponse publique.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, validator

from services import matching
from services import security as security_svc
from services import caution as caution_svc


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class BroadcastCreateInput(BaseModel):
    trade: str = Field(..., min_length=1, max_length=64)
    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    slot: str = Field(
        ...,
        pattern=r"^([01]\d|2[0-3]):[0-5]\d(?:-([01]\d|2[0-3]):[0-5]\d)?$",
    )
    description: str = Field("", max_length=2000)
    urgent: bool = False
    city: Optional[str] = Field(None, max_length=100)
    # FAQTOTUM V1 — Estimation (fourchette) fournie par l'IA à la fin de la
    # conversation concierge. Sert à calculer la caution 7 % de la borne haute.
    estimated_price_min_eur: Optional[float] = Field(None, ge=0, le=100000)
    estimated_price_max_eur: Optional[float] = Field(None, ge=0, le=100000)

    @validator("description")
    def _no_html(cls, v: str) -> str:  # noqa: N805
        if "<script" in v.lower() or "</script" in v.lower():
            raise ValueError("Contenu potentiellement malveillant refusé")
        return v[:2000]


class BroadcastAcceptInput(BaseModel):
    artisan_id: str = Field(..., min_length=1, max_length=64)


PUBLIC_BROADCAST_FIELDS = frozenset({
    "broadcast_id", "client_name", "trade", "date", "slot",
    "description", "urgent", "status", "created_at", "expires_at",
    # FAQTOTUM V1 — expose estimation + caution aux 2 côtés (client + candidats).
    "estimated_price_min_eur", "estimated_price_max_eur",
    "caution_cents", "caution_eur_display",
})


def _public_view(bc: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in bc.items() if k in PUBLIC_BROADCAST_FIELDS}


def build_broadcasts_router(
    db, get_current_user, *, enrich_artisan=None,
) -> APIRouter:
    r = APIRouter()

    # -----------------------------------------------------------------
    # Helper — mark expired if past TTL, returns fresh doc (or None).
    # -----------------------------------------------------------------
    async def _refresh_expiry(bc: Dict[str, Any]) -> Dict[str, Any]:
        if bc.get("status") == "open" and bc.get("expires_at"):
            try:
                exp = datetime.fromisoformat(bc["expires_at"])
                if exp < _now_utc():
                    await db.booking_broadcasts.update_one(
                        {"broadcast_id": bc["broadcast_id"], "status": "open"},
                        {"$set": {
                            "status": "expired",
                            "expired_at": _now_utc().isoformat(),
                        }},
                    )
                    bc["status"] = "expired"
            except Exception:
                pass
        return bc

    # -----------------------------------------------------------------
    # POST /broadcasts — client creates
    # -----------------------------------------------------------------
    @r.post("/broadcasts")
    async def create_broadcast(
        data: BroadcastCreateInput, user=Depends(get_current_user),
    ):
        # 1. Trouver les candidats : artisans du bon trade, visible publiquement.
        query = {
            "trade": data.trade,
            "is_subscribed": True,
            "$or": [
                {"verification_status": "approved"},
                {"verification_status": {"$exists": False}},
            ],
        }
        raw = await db.artisan_profiles.find(query, {"_id": 0}).to_list(200)
        if not raw:
            raise HTTPException(
                status_code=404,
                detail="Aucun artisan disponible pour ce métier",
            )
        # 2. Ranker via le moteur de matching (top 5).
        ctx: Dict[str, Any] = {"urgency": "urgence" if data.urgent else "normal"}
        ranked = matching.rank(raw, ctx)
        top = ranked[:5]
        candidates = [a["artisan_id"] for a in top if a.get("artisan_id")]
        if not candidates:
            raise HTTPException(
                status_code=404,
                detail="Aucun artisan éligible trouvé",
            )
        # 3. Persister le broadcast.
        broadcast_id = _new_id("bc")
        ttl_minutes = 30 if data.urgent else 60
        # FAQTOTUM V1 — estimation + caution basée sur l'estimation initiale.
        # Locked à la création : ne PAS recalculer même si prix final change.
        est_max = data.estimated_price_max_eur
        est_min = data.estimated_price_min_eur
        caution_cents = caution_svc.compute_caution_cents(est_max or 0)
        doc = {
            "broadcast_id": broadcast_id,
            "client_id": user["user_id"],
            "client_name": user["name"],
            "trade": data.trade,
            "date": data.date,
            "slot": data.slot,
            "description": data.description,
            "urgent": bool(data.urgent),
            "candidates": candidates,
            "status": "open",
            "winner_artisan_id": None,
            "winner_booking_id": None,
            "city": data.city,
            "estimated_price_min_eur": est_min,
            "estimated_price_max_eur": est_max,
            "caution_cents": caution_cents,
            "caution_eur_display": caution_svc.format_eur(caution_cents),
            "created_at": _now_utc().isoformat(),
            "expires_at": (_now_utc() + timedelta(minutes=ttl_minutes)).isoformat(),
        }
        await db.booking_broadcasts.insert_one(dict(doc))
        await security_svc.audit_log(
            db, action="broadcast.created",
            actor_id=user["user_id"], actor_role="client",
            target=broadcast_id,
            metadata={
                "trade": data.trade,
                "urgent": bool(data.urgent),
                "candidates_count": len(candidates),
            },
            severity="info",
        )
        doc.pop("_id", None)
        # Le client voit qu'il a X candidats sollicités — sans leur ID.
        out = _public_view(doc)
        out["candidates_count"] = len(candidates)
        return out

    # -----------------------------------------------------------------
    # GET /broadcasts/pending — artisan lists his open broadcasts
    # -----------------------------------------------------------------
    @r.get("/broadcasts/pending")
    async def list_pending(user=Depends(get_current_user)):
        if user.get("role") != "artisan":
            raise HTTPException(status_code=403, detail="Réservé aux artisans")
        # Récupérer l'artisan_id de ce user.
        profile = await db.artisan_profiles.find_one(
            {"user_id": user["user_id"]}, {"_id": 0, "artisan_id": 1},
        )
        if not profile or not profile.get("artisan_id"):
            return []
        artisan_id = profile["artisan_id"]
        cursor = db.booking_broadcasts.find(
            {
                "status": "open",
                "candidates": artisan_id,
            },
            {"_id": 0},
        ).sort("created_at", -1)
        raw = await cursor.to_list(50)
        # Refresh TTL & filtre les expirés fraîchement détectés.
        fresh: List[Dict[str, Any]] = []
        for bc in raw:
            bc = await _refresh_expiry(bc)
            if bc.get("status") == "open":
                fresh.append(_public_view(bc))
        return fresh

    # -----------------------------------------------------------------
    # POST /broadcasts/{id}/accept — atomic accept-first-wins
    # -----------------------------------------------------------------
    @r.post("/broadcasts/{broadcast_id}/accept")
    async def accept_broadcast(
        broadcast_id: str, data: BroadcastAcceptInput,
        user=Depends(get_current_user),
    ):
        if user.get("role") != "artisan":
            raise HTTPException(status_code=403, detail="Réservé aux artisans")
        # Vérifier ownership de l'artisan_id.
        profile = await db.artisan_profiles.find_one(
            {"artisan_id": data.artisan_id}, {"_id": 0},
        )
        if not profile:
            raise HTTPException(status_code=404, detail="Artisan introuvable")
        if profile.get("user_id") and profile["user_id"] != user["user_id"]:
            await security_svc.audit_log(
                db, action="broadcast.accept_denied",
                actor_id=user["user_id"], target=broadcast_id,
                metadata={"reason": "foreign_artisan"}, severity="warn",
            )
            raise HTTPException(
                status_code=403, detail="Ce profil ne vous appartient pas",
            )
        # Charger le broadcast (avec check TTL).
        bc = await db.booking_broadcasts.find_one(
            {"broadcast_id": broadcast_id}, {"_id": 0},
        )
        if not bc:
            raise HTTPException(status_code=404, detail="Broadcast introuvable")
        bc = await _refresh_expiry(bc)
        if bc.get("status") != "open":
            raise HTTPException(
                status_code=409,
                detail="Cette demande n'est plus disponible",
            )
        if data.artisan_id not in (bc.get("candidates") or []):
            await security_svc.audit_log(
                db, action="broadcast.accept_denied",
                actor_id=user["user_id"], target=broadcast_id,
                metadata={"reason": "not_candidate"}, severity="warn",
            )
            raise HTTPException(
                status_code=403,
                detail="Vous n'êtes pas sollicité pour ce broadcast",
            )
        # ATOMIC compare-and-set : seul le premier bascule.
        updated = await db.booking_broadcasts.find_one_and_update(
            {"broadcast_id": broadcast_id, "status": "open"},
            {"$set": {
                "status": "assigned",
                "winner_artisan_id": data.artisan_id,
                "assigned_at": _now_utc().isoformat(),
            }},
            return_document=True,
        )
        if not updated:
            # Un autre artisan a gagné entre-temps.
            raise HTTPException(
                status_code=409,
                detail="Un autre artisan vient d'accepter cette demande",
            )
        # Créer un booking classique lié au broadcast.
        booking_id = _new_id("bk")
        conv_id = "conv_" + booking_id.split("_", 1)[1]
        booking_doc = {
            "booking_id": booking_id,
            "conversation_id": conv_id,
            "client_id": bc["client_id"],
            "client_name": bc["client_name"],
            "artisan_id": data.artisan_id,
            "artisan_user_id": profile.get("user_id"),
            "artisan_name": profile.get("name") or profile.get("title"),
            "trade_name": bc.get("trade"),
            "date": bc.get("date"),
            "slot": bc.get("slot"),
            "description": bc.get("description", ""),
            "urgent": bool(bc.get("urgent")),
            "status": "accepted",
            "broadcast_id": broadcast_id,
            # FAQTOTUM V1 — Propager l'estimation + caution figées.
            "estimated_price_min_eur": bc.get("estimated_price_min_eur"),
            "estimated_price_max_eur": bc.get("estimated_price_max_eur"),
            "caution_cents": bc.get("caution_cents") or 0,
            "created_at": _now_utc().isoformat(),
        }
        await db.bookings.insert_one(dict(booking_doc))
        await db.conversations.insert_one({
            "conversation_id": conv_id,
            "booking_id": booking_id,
            "client_id": bc["client_id"],
            "client_name": bc["client_name"],
            "artisan_user_id": profile.get("user_id"),
            "artisan_id": data.artisan_id,
            "artisan_name": profile.get("name") or profile.get("title"),
            "trade_name": bc.get("trade"),
            "last_message": (
                "Demande URGENTE acceptée" if bc.get("urgent")
                else "Demande acceptée via broadcast"
            ),
            "last_at": _now_utc().isoformat(),
            "created_at": _now_utc().isoformat(),
        })
        # Lier le winner au broadcast.
        await db.booking_broadcasts.update_one(
            {"broadcast_id": broadcast_id},
            {"$set": {"winner_booking_id": booking_id}},
        )
        await security_svc.audit_log(
            db, action="broadcast.assigned",
            actor_id=user["user_id"], actor_role="artisan",
            target=broadcast_id,
            metadata={
                "winner_artisan_id": data.artisan_id,
                "booking_id": booking_id,
            },
            severity="info",
        )
        booking_doc.pop("_id", None)
        return {
            "ok": True,
            "broadcast_id": broadcast_id,
            "booking": booking_doc,
        }

    # -----------------------------------------------------------------
    # POST /broadcasts/{id}/decline — artisan retires from candidates
    # -----------------------------------------------------------------
    @r.post("/broadcasts/{broadcast_id}/decline")
    async def decline_broadcast(
        broadcast_id: str, data: BroadcastAcceptInput,
        user=Depends(get_current_user),
    ):
        if user.get("role") != "artisan":
            raise HTTPException(status_code=403, detail="Réservé aux artisans")
        profile = await db.artisan_profiles.find_one(
            {"artisan_id": data.artisan_id}, {"_id": 0},
        )
        if not profile or (
            profile.get("user_id") and profile["user_id"] != user["user_id"]
        ):
            raise HTTPException(status_code=403, detail="Refusé")
        await db.booking_broadcasts.update_one(
            {"broadcast_id": broadcast_id, "status": "open"},
            {"$pull": {"candidates": data.artisan_id}},
        )
        await security_svc.audit_log(
            db, action="broadcast.declined",
            actor_id=user["user_id"], actor_role="artisan",
            target=broadcast_id,
            metadata={"artisan_id": data.artisan_id},
            severity="info",
        )
        return {"ok": True}

    # -----------------------------------------------------------------
    # POST /broadcasts/{id}/cancel — client cancels
    # -----------------------------------------------------------------
    @r.post("/broadcasts/{broadcast_id}/cancel")
    async def cancel_broadcast(
        broadcast_id: str, user=Depends(get_current_user),
    ):
        bc = await db.booking_broadcasts.find_one(
            {"broadcast_id": broadcast_id}, {"_id": 0},
        )
        if not bc:
            raise HTTPException(status_code=404, detail="Broadcast introuvable")
        if bc.get("client_id") != user["user_id"]:
            raise HTTPException(status_code=404, detail="Broadcast introuvable")
        if bc.get("status") != "open":
            raise HTTPException(
                status_code=400,
                detail="Impossible d'annuler cette demande",
            )
        await db.booking_broadcasts.update_one(
            {"broadcast_id": broadcast_id, "status": "open"},
            {"$set": {
                "status": "cancelled",
                "cancelled_at": _now_utc().isoformat(),
            }},
        )
        await security_svc.audit_log(
            db, action="broadcast.cancelled",
            actor_id=user["user_id"], actor_role="client",
            target=broadcast_id,
            metadata={}, severity="info",
        )
        return {"ok": True}

    # -----------------------------------------------------------------
    # GET /broadcasts/mine — client lists his broadcasts
    # -----------------------------------------------------------------
    @r.get("/broadcasts/mine")
    async def my_broadcasts(user=Depends(get_current_user)):
        cursor = db.booking_broadcasts.find(
            {"client_id": user["user_id"]}, {"_id": 0},
        ).sort("created_at", -1)
        raw = await cursor.to_list(100)
        out: List[Dict[str, Any]] = []
        for bc in raw:
            bc = await _refresh_expiry(bc)
            item = _public_view(bc)
            item["candidates_count"] = len(bc.get("candidates") or [])
            item["winner_booking_id"] = bc.get("winner_booking_id")
            out.append(item)
        return out

    return r
