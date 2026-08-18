"""
properties router — V1 migration (Option B: fast structural partition).

Legacy routes previously defined inline in ``server.py`` are moved here
verbatim (bodies unchanged) and mounted via ``build_properties_router(**deps)``.
All external references (db, helpers, services, Pydantic models) are
injected via keyword arguments so this module has no circular import back
to ``server``.

Do NOT add new business logic here without splitting into a dedicated file —
this file exists to keep server.py small; the "canonical" refactor (typed
Pydantic input models per route, explicit dependency signatures) is a
follow-up sprint.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
import logging
logger = logging.getLogger(__name__)
from services import homes as homes_svc, security
from datetime import datetime, timezone
import uuid
import os

# `db`, `get_current_user`, and every helper/service/model this module needs
# are captured in the closure of `build_properties_router(**deps)` below.


def build_properties_router(**deps) -> APIRouter:
    """Factory: returns an APIRouter mounting every properties endpoint.

    `deps` MUST include (all names as used inside the extracted route bodies):
    db, get_current_user, now_utc, new_id, _get_property, _append_passport_history, homes_svc, growth, PROPERTY_TYPES, REMINDER_STATUSES, EVENT_KINDS, DOCUMENT_KINDS, PropertyInput, EquipmentInput, DocumentInput, ReminderInput, ReminderPatchInput, EventInput
    """
    # Explode deps into locals so the extracted route bodies find them by name.
    globals().update(deps)  # noqa: F821 — populates module scope for closures
    _locals = deps
    for _k, _v in _locals.items():
        locals()[_k] = _v

    r = APIRouter()

    @r.get("/properties")
    async def list_properties(user=Depends(get_current_user)):
        props = await db.properties.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
        # attach quick counts
        out = []
        for p in props:
            pid = p["property_id"]
            equip_count = await db.property_equipment.count_documents({"property_id": pid})
            doc_count = await db.property_documents.count_documents({"property_id": pid})
            reminder_count = await db.property_reminders.count_documents({"property_id": pid, "status": {"$in": ["upcoming", "due"]}})
            p["equipment_count"] = equip_count
            p["document_count"] = doc_count
            p["reminder_count"] = reminder_count
            out.append(p)
        return out


    @r.post("/properties")
    async def create_property(body: PropertyInput, user=Depends(get_current_user)):
        if body.type not in PROPERTY_TYPES:
            raise HTTPException(status_code=400, detail="Type de bien invalide")
        prop = {
            "property_id": new_id("prop"),
            "user_id": user["user_id"],
            "name": body.name.strip(),
            "type": body.type,
            "address": (body.address or "").strip(),
            "city": (body.city or "").strip(),
            "postal_code": (body.postal_code or "").strip(),
            "surface": body.surface,
            "year_built": body.year_built,
            "rooms": body.rooms,
            "dpe_grade": body.dpe_grade,
            "cover_color": body.cover_color or "#0EA5E9",
            "photos": body.photos or [],
            "notes": (body.notes or "").strip(),
            "health_score": 100,
            "share_token": None,
            "created_at": now_utc().isoformat(),
            "updated_at": now_utc().isoformat(),
        }
        await db.properties.insert_one(dict(prop))
        return prop


    @r.get("/properties/{pid}")
    async def get_property(pid: str, user=Depends(get_current_user)):
        return await _get_property(pid, user["user_id"])


    @r.patch("/properties/{pid}")
    async def update_property(pid: str, body: dict, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        if "type" in body and body["type"] not in PROPERTY_TYPES:
            raise HTTPException(status_code=400, detail="Type de bien invalide")
        allowed = {"name", "type", "address", "city", "postal_code", "surface", "year_built", "rooms", "dpe_grade", "cover_color", "photos", "notes"}
        updates = {k: v for k, v in body.items() if k in allowed}
        if "name" in updates and isinstance(updates["name"], str):
            updates["name"] = updates["name"].strip()
        if "address" in updates and isinstance(updates["address"], str):
            updates["address"] = updates["address"].strip()
        if "notes" in updates and isinstance(updates["notes"], str):
            updates["notes"] = updates["notes"].strip()
        updates["updated_at"] = now_utc().isoformat()
        await db.properties.update_one({"property_id": pid}, {"$set": updates})
        return await db.properties.find_one({"property_id": pid}, {"_id": 0})


    @r.delete("/properties/{pid}")
    async def delete_property(pid: str, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        await db.properties.delete_one({"property_id": pid})
        await db.property_equipment.delete_many({"property_id": pid})
        await db.property_documents.delete_many({"property_id": pid})
        await db.property_reminders.delete_many({"property_id": pid})
        return {"ok": True}


    @r.get("/properties/{pid}/equipment")
    async def list_equipment(pid: str, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        items = await db.property_equipment.find({"property_id": pid}, {"_id": 0}).sort("created_at", -1).to_list(500)
        return items


    @r.post("/properties/{pid}/equipment")
    async def create_equipment(pid: str, body: EquipmentInput, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        if body.status not in EQUIPMENT_STATUSES:
            raise HTTPException(status_code=400, detail="Statut invalide")
        doc = {
            "equipment_id": new_id("eq"),
            "property_id": pid,
            "user_id": user["user_id"],
            "name": body.name.strip(),
            "category": body.category or "other",
            "brand": body.brand or "",
            "model": body.model or "",
            "serial_number": body.serial_number or "",
            "installed_on": body.installed_on,
            "installer": body.installer or "",
            "warranty_until": body.warranty_until,
            "photos": body.photos or [],
            "documents": body.documents or [],
            "status": body.status or "ok",
            "notes": body.notes or "",
            "created_at": now_utc().isoformat(),
            "updated_at": now_utc().isoformat(),
        }
        await db.property_equipment.insert_one(dict(doc))
        # Auto-generate maintenance + warranty reminders (idempotent)
        eq_for_svc = {
            "equipment_id": doc["equipment_id"],
            "property_id": doc["property_id"],
            "user_id": doc["user_id"],
            "category": doc["category"],
            "installed_at": doc.get("installed_on"),
            "last_maintenance_at": None,
            "warranty_until": doc.get("warranty_until"),
        }
        try:
            reminders_created = await homes_svc.generate_reminders_for_equipment(db, eq_for_svc)
            doc["_auto_reminders_created"] = len(reminders_created)
        except Exception as ex:
            logger.warning(f"auto-reminder generation failed: {ex}")
            doc["_auto_reminders_created"] = 0
        return doc


    @r.get("/properties/{pid}/equipment/{eid}")
    async def get_equipment(pid: str, eid: str, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        e = await db.property_equipment.find_one({"equipment_id": eid, "property_id": pid}, {"_id": 0})
        if not e:
            raise HTTPException(status_code=404, detail="Équipement introuvable")
        return e


    @r.patch("/properties/{pid}/equipment/{eid}")
    async def update_equipment(pid: str, eid: str, body: dict, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        e = await db.property_equipment.find_one({"equipment_id": eid, "property_id": pid})
        if not e:
            raise HTTPException(status_code=404, detail="Équipement introuvable")
        if "status" in body and body["status"] not in EQUIPMENT_STATUSES:
            raise HTTPException(status_code=400, detail="Statut invalide")
        allowed = {"name", "category", "brand", "model", "serial_number", "installed_on", "installer", "warranty_until", "photos", "documents", "status", "notes"}
        updates = {k: v for k, v in body.items() if k in allowed}
        updates["updated_at"] = now_utc().isoformat()
        await db.property_equipment.update_one({"equipment_id": eid}, {"$set": updates})
        return await db.property_equipment.find_one({"equipment_id": eid}, {"_id": 0})


    @r.delete("/properties/{pid}/equipment/{eid}")
    async def delete_equipment(pid: str, eid: str, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        await db.property_equipment.delete_one({"equipment_id": eid, "property_id": pid})
        return {"ok": True}


    @r.get("/properties/{pid}/documents")
    async def list_documents(pid: str, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        return await db.property_documents.find({"property_id": pid}, {"_id": 0}).sort("created_at", -1).to_list(500)


    @r.post("/properties/{pid}/documents")
    async def create_document(pid: str, body: DocumentInput, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        if body.category not in DOC_CATEGORIES:
            raise HTTPException(status_code=400, detail="Catégorie invalide")
        d = {
            "document_id": new_id("doc"),
            "property_id": pid,
            "user_id": user["user_id"],
            "title": body.title.strip(),
            "category": body.category,
            "file_uri": body.file_uri or "",
            "equipment_id": body.equipment_id,
            "notes": body.notes or "",
            "created_at": now_utc().isoformat(),
        }
        await db.property_documents.insert_one(dict(d))
        return d


    @r.delete("/properties/{pid}/documents/{doc_id}")
    async def delete_document(pid: str, doc_id: str, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        await db.property_documents.delete_one({"document_id": doc_id, "property_id": pid})
        return {"ok": True}


    @r.get("/properties/{pid}/reminders")
    async def list_reminders(pid: str, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        items = await db.property_reminders.find({"property_id": pid}, {"_id": 0}).sort("due_on", 1).to_list(500)
        # Auto-flag due
        today = now_utc().date().isoformat()
        for r in items:
            if r.get("status") == "upcoming" and r.get("due_on") and r["due_on"] <= today:
                r["status"] = "due"
        return items


    @r.post("/properties/{pid}/reminders")
    async def create_reminder(pid: str, body: ReminderInput, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        r = {
            "reminder_id": new_id("rem"),
            "property_id": pid,
            "user_id": user["user_id"],
            "title": body.title.strip(),
            "due_on": body.due_on,
            "frequency": body.frequency,
            "equipment_id": body.equipment_id,
            "notes": body.notes or "",
            "status": "upcoming",
            "created_at": now_utc().isoformat(),
        }
        await db.property_reminders.insert_one(dict(r))
        return r


    @r.patch("/properties/{pid}/reminders/{rid}")
    async def update_reminder(pid: str, rid: str, body: ReminderPatchInput, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        # `exclude_unset` → only fields explicitly sent by the client are updated.
        updates = body.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(status_code=400, detail="Aucun champ à modifier")
        if "status" in updates and updates["status"] not in REMINDER_STATUSES:
            raise HTTPException(status_code=400, detail="Statut invalide")
        updates["updated_at"] = now_utc().isoformat()
        await db.property_reminders.update_one(
            {"reminder_id": rid, "property_id": pid}, {"$set": updates}
        )
        return await db.property_reminders.find_one({"reminder_id": rid}, {"_id": 0})


    @r.delete("/properties/{pid}/reminders/{rid}")
    async def delete_reminder(pid: str, rid: str, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        await db.property_reminders.delete_one({"reminder_id": rid, "property_id": pid})
        return {"ok": True}


    @r.get("/properties/{pid}/timeline")
    async def property_timeline(pid: str, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        events = []
        # equipment install events
        async for e in db.property_equipment.find({"property_id": pid}, {"_id": 0}):
            if e.get("installed_on"):
                events.append({
                    "id": e["equipment_id"],
                    "type": "equipment_installed",
                    "title": f"{e['name']} installé",
                    "subtitle": e.get("brand") or "",
                    "date": e["installed_on"],
                    "icon": "cog",
                    "ref": {"equipment_id": e["equipment_id"]},
                })
        # documents added
        async for d in db.property_documents.find({"property_id": pid}, {"_id": 0}):
            events.append({
                "id": d["document_id"],
                "type": "document",
                "title": d["title"],
                "subtitle": d["category"],
                "date": d["created_at"][:10],
                "icon": "document-text",
                "ref": {"document_id": d["document_id"]},
            })
        # linked bookings (interventions completed on this property)
        async for b in db.bookings.find({"client_id": user["user_id"], "property_id": pid}, {"_id": 0}):
            events.append({
                "id": b["booking_id"],
                "type": "intervention",
                "title": b.get("description", "Intervention"),
                "subtitle": f"Statut: {b.get('status', 'pending')}",
                "date": (b.get("scheduled_at") or b.get("created_at", ""))[:10],
                "icon": "briefcase",
                "ref": {"booking_id": b["booking_id"]},
            })
        # reminders completed
        async for r in db.property_reminders.find({"property_id": pid, "status": "done"}, {"_id": 0}):
            events.append({
                "id": r["reminder_id"],
                "type": "reminder_done",
                "title": r["title"],
                "subtitle": "Rappel terminé",
                "date": r.get("updated_at", r.get("due_on", ""))[:10],
                "icon": "checkmark-circle",
                "ref": {"reminder_id": r["reminder_id"]},
            })
        # sort desc by date
        events.sort(key=lambda x: x["date"] or "", reverse=True)
        # group by year
        grouped: dict = {}
        for ev in events:
            y = (ev["date"] or "")[:4] or "—"
            grouped.setdefault(y, []).append(ev)
        return {"events": events, "grouped": grouped}


    @r.get("/properties/{pid}/insights")
    async def property_insights(pid: str, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        equipment_count = await db.property_equipment.count_documents({"property_id": pid})
        ok_count = await db.property_equipment.count_documents({"property_id": pid, "status": "ok"})
        attention_count = await db.property_equipment.count_documents({"property_id": pid, "status": {"$in": ["attention", "maintenance", "replace"]}})
        document_count = await db.property_documents.count_documents({"property_id": pid})
        upcoming = await db.property_reminders.count_documents({"property_id": pid, "status": {"$in": ["upcoming", "due"]}})
        # Interventions linked
        interventions = await db.bookings.count_documents({"client_id": user["user_id"], "property_id": pid})
        # Money invested = sum of intervention amounts if any
        money = 0
        async for b in db.bookings.find({"client_id": user["user_id"], "property_id": pid}, {"_id": 0, "amount": 1}):
            try:
                money += float(b.get("amount") or 0)
            except Exception:
                pass
        # Realistic demo values when empty so the UI feels alive from day 1
        if equipment_count == 0 and interventions == 0 and money == 0:
            demo = True
            money = 3240
            interventions = 6
        else:
            demo = False
        health = 100 if equipment_count == 0 else int(round((ok_count / max(equipment_count, 1)) * 100))
        return {
            "equipment_count": equipment_count,
            "equipment_ok": ok_count,
            "equipment_attention": attention_count,
            "document_count": document_count,
            "upcoming_maintenance": upcoming,
            "interventions": interventions,
            "money_invested": money,
            "average_health": health,
            "demo_values": demo,
        }


    @r.get("/properties/{pid}/ai-cards")
    async def property_ai_cards(pid: str, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        cards = [
            {"key": "equipment_health", "title": "Santé des équipements", "subtitle": "IA analysera l'état et la longévité de vos équipements.", "icon": "pulse"},
            {"key": "maintenance_prediction", "title": "Maintenance prédictive", "subtitle": "L'IA anticipera les entretiens critiques avant les pannes.", "icon": "calendar"},
            {"key": "risk_detection", "title": "Détection de risques", "subtitle": "Identifiera les risques (fuite, incendie, humidité) automatiquement.", "icon": "shield-checkmark"},
            {"key": "energy_optimization", "title": "Optimisation énergétique", "subtitle": "Recommandations pour baisser vos factures et l'empreinte carbone.", "icon": "flash"},
            {"key": "warranty_expiration", "title": "Expiration garanties", "subtitle": "Vous préviendra avant chaque fin de garantie.", "icon": "ribbon"},
            {"key": "recommended_inspection", "title": "Inspection recommandée", "subtitle": "Suggérera les diagnostics à réaliser selon votre bien.", "icon": "sparkles"},
        ]
        return [{**c, "status": "coming_soon"} for c in cards]



    @r.get("/properties/{pid}/events")
    async def list_property_events(pid: str, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        rows = await db.property_events.find({"property_id": pid}, {"_id": 0}).sort("event_date", -1).to_list(500)
        return {"items": rows, "count": len(rows)}



    @r.post("/properties/{pid}/events")
    async def create_property_event(pid: str, body: PropertyEventInput, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        if body.event_type not in homes_svc.EVENT_TYPES:
            raise HTTPException(status_code=400, detail="Type d'événement invalide")
        ev = {
            "event_id": homes_svc.new_id("evt"),
            "property_id": pid,
            "user_id": user["user_id"],
            "event_type": body.event_type,
            "title": body.title.strip(),
            "description": body.description,
            "artisan_name": body.artisan_name,
            "cost_cents": body.cost_cents,
            "event_date": body.event_date,
            "created_at": now_utc().isoformat(),
        }
        await db.property_events.insert_one(dict(ev))
        return ev



    @r.delete("/properties/{pid}/events/{event_id}")
    async def delete_property_event(pid: str, event_id: str, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        r = await db.property_events.delete_one({"event_id": event_id, "property_id": pid})
        if r.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Événement introuvable")
        return {"ok": True}



    @r.post("/properties/{pid}/equipment/{eid}/auto-reminders")
    async def generate_equipment_reminders(pid: str, eid: str, user=Depends(get_current_user)):
        """Idempotent: (re)generate maintenance + warranty reminders for an equipment.
        Called automatically after equipment creation, but exposed to the client to
        let users re-trigger it if they update dates on an existing equipment.
        """
        await _get_property(pid, user["user_id"])
        eq = await db.property_equipment.find_one({"equipment_id": eid, "property_id": pid}, {"_id": 0})
        if not eq:
            raise HTTPException(status_code=404, detail="Équipement introuvable")
        # Normalize equipment for homes_svc helper (it expects a slightly different shape)
        eq_for_svc = {
            "equipment_id": eq["equipment_id"],
            "property_id": eq["property_id"],
            "user_id": eq["user_id"],
            "category": eq.get("category", "autre"),
            "installed_at": eq.get("installed_on"),
            "last_maintenance_at": eq.get("last_maintenance_at"),
            "warranty_until": eq.get("warranty_until"),
        }
        reminders = await homes_svc.generate_reminders_for_equipment(db, eq_for_svc)
        return {"reminders_created": len(reminders), "reminders": reminders}



    @r.get("/properties/{pid}/budget")
    async def property_budget(pid: str, user=Depends(get_current_user)):
        """Return aggregated budget stats (total, by month, by type, top artisans).
        Sources:
          - `property_events` collection (manual entries with cost_cents)
          - `bookings` collection (interventions attached to this property)
        """
        await _get_property(pid, user["user_id"])

        events = await db.property_events.find(
            {"property_id": pid, "cost_cents": {"$ne": None}}, {"_id": 0}
        ).to_list(1000)

        # Also pull bookings that had a completed payment
        async for b in db.bookings.find(
            {"client_id": user["user_id"], "property_id": pid, "status": {"$in": ["completed", "in_progress"]}},
            {"_id": 0, "amount": 1, "created_at": 1, "trade": 1, "artisan_name": 1},
        ):
            try:
                events.append({
                    "event_type": "intervention",
                    "event_date": (b.get("created_at") or "")[:10],
                    "cost_cents": int(float(b.get("amount") or 0) * 100),
                    "artisan_name": b.get("artisan_name"),
                })
            except Exception:
                pass

        total_cents = 0
        by_month: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        by_artisan: Dict[str, int] = {}
        for e in events:
            cents = int(e.get("cost_cents") or 0)
            total_cents += cents
            month_key = str(e.get("event_date", ""))[:7]
            by_month[month_key] = by_month.get(month_key, 0) + cents
            et = e.get("event_type", "autre")
            by_type[et] = by_type.get(et, 0) + cents
            a = e.get("artisan_name")
            if a:
                by_artisan[a] = by_artisan.get(a, 0) + cents

        keys = sorted(by_month.keys())[-12:]
        return {
            "total_cents": total_cents,
            "events_count": len(events),
            "by_month": [{"month": k, "cents": by_month[k]} for k in keys],
            "by_type": [
                {"type": t, "cents": c}
                for t, c in sorted(by_type.items(), key=lambda x: -x[1])
            ],
            "top_artisans": [
                {"name": n, "cents": c}
                for n, c in sorted(by_artisan.items(), key=lambda x: -x[1])[:5]
            ],
        }



    @r.post("/properties/{pid}/share")
    async def enable_property_share(pid: str, user=Depends(get_current_user)):
        """Enable a public read-only passport link for this property."""
        await _get_property(pid, user["user_id"])
        token = uuid.uuid4().hex
        await db.properties.update_one(
            {"property_id": pid},
            {"$set": {"share_token": token, "updated_at": now_utc().isoformat()}},
        )
        platform = os.environ.get("PLATFORM_URL", "https://reviens-app.preview.emergentagent.com")
        await security.audit_log(db, action="property.share_enabled", actor_id=user["user_id"], target=pid, severity="info")
        return {"token": token, "url": f"{platform}/passport/{token}"}



    @r.delete("/properties/{pid}/share")
    async def disable_property_share(pid: str, user=Depends(get_current_user)):
        await _get_property(pid, user["user_id"])
        await db.properties.update_one(
            {"property_id": pid},
            {"$set": {"share_token": None, "updated_at": now_utc().isoformat()}},
        )
        await security.audit_log(db, action="property.share_disabled", actor_id=user["user_id"], target=pid, severity="info")
        return {"ok": True}



    @r.get("/passport/{token}")
    async def passport_public(token: str):
        """Public read-only endpoint — no authentication required."""
        prop = await db.properties.find_one({"share_token": token}, {"_id": 0})
        if not prop:
            raise HTTPException(status_code=404, detail="Passeport introuvable ou révoqué")
        eqs = await db.property_equipment.find(
            {"property_id": prop["property_id"]},
            {"_id": 0, "user_id": 0, "serial_number": 0, "notes": 0, "documents": 0},
        ).to_list(200)
        events: List[Dict[str, Any]] = []
        async for e in db.property_events.find(
            {"property_id": prop["property_id"]},
            {"_id": 0, "user_id": 0, "description": 0, "cost_cents": 0},
        ).sort("event_date", -1):
            events.append(e)
        return {
            "property": {
                "name": prop.get("name") or prop.get("label"),
                "property_type": prop.get("type") or prop.get("property_type"),
                "city": prop.get("city"),
                "postal_code": prop.get("postal_code"),
                "address": prop.get("address"),
                "surface": prop.get("surface"),
                "year_built": prop.get("year_built"),
                "rooms": prop.get("rooms"),
                "dpe_grade": prop.get("dpe_grade"),
                "cover_color": prop.get("cover_color") or "#0EA5E9",
                "health_score": prop.get("health_score", 100),
            },
            "equipments": eqs,
            "events": events,
        }



    return r
