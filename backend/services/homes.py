"""
Auxora — Home OS / Property Passport Service
=============================================
Digital health record for each property owned by a user.

A "property" (home) is the anchor around which every other piece of data
gravitates: equipments, documents, historical events (interventions),
maintenance reminders and budget analytics.

Design invariants
-----------------
- Every write increments `properties.updated_at` (denormalized touch).
- `health_score` is recomputed on every mutation so the UI can trust it.
- Maintenance reminders are generated automatically when the user adds
  an equipment: we know from a lookup table how often each category needs
  service (e.g. boilers = every 12 months, smoke detectors = every 12).
- Public share tokens are opaque uuids stored on the property row.
  When set, the read-only passport endpoint returns identity + equipments
  + non-sensitive history. Documents remain private forever.
"""
from __future__ import annotations
import uuid
import base64
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — controlled vocabularies
# ---------------------------------------------------------------------------

PROPERTY_TYPES = {"maison", "appartement", "local_commercial", "locatif", "autre"}

EQUIPMENT_CATEGORIES = {
    # category -> (label, color, months_between_maintenance, months_of_warranty_default)
    "chaudiere": ("Chaudière", "#EF4444", 12, 24),
    "ballon_eau_chaude": ("Ballon eau chaude", "#0EA5E9", 24, 24),
    "pompe_a_chaleur": ("Pompe à chaleur", "#06B6D4", 12, 24),
    "climatisation": ("Climatisation", "#22D3EE", 12, 24),
    "vmc": ("VMC", "#94A3B8", 24, 12),
    "panneaux_solaires": ("Panneaux solaires", "#F59E0B", 60, 120),
    "alarme": ("Alarme", "#DC2626", 24, 24),
    "cameras": ("Caméras", "#7C3AED", 24, 24),
    "portail": ("Portail motorisé", "#64748B", 24, 24),
    "volets": ("Volets", "#A3A3A3", 36, 24),
    "serrure_connectee": ("Serrure connectée", "#0F766E", 36, 24),
    "detecteur_fumee": ("Détecteur fumée", "#F97316", 12, 60),
    "electrique": ("Tableau électrique", "#EAB308", 60, 0),
    "toiture": ("Toiture", "#B45309", 120, 0),
    "plomberie": ("Plomberie", "#3B82F6", 60, 0),
    "autre": ("Autre", "#6B7280", 24, 12),
    # ---- English aliases used by the existing Auxora frontend ----
    "boiler": ("Chaudière", "#EF4444", 12, 24),
    "water_heater": ("Chauffe-eau", "#0EA5E9", 24, 24),
    "heat_pump": ("Pompe à chaleur", "#06B6D4", 12, 24),
    "ac": ("Climatisation", "#22D3EE", 12, 24),
    "solar": ("Panneaux solaires", "#F59E0B", 60, 120),
    "panel": ("Tableau électrique", "#EAB308", 60, 0),
    "roof": ("Toiture", "#B45309", 120, 0),
    "windows": ("Fenêtres", "#8B5CF6", 60, 24),
    "doors": ("Portes", "#78716C", 60, 24),
    "smoke_detector": ("Détecteur fumée", "#F97316", 12, 60),
    "ev_charger": ("Borne électrique", "#10B981", 24, 36),
    "water_softener": ("Adoucisseur d'eau", "#0891B2", 12, 24),
    "other": ("Autre", "#6B7280", 24, 12),
}

EVENT_TYPES = {"installation", "entretien", "reparation", "controle", "nettoyage", "sinistre", "autre"}

DOC_TYPES = {"facture", "devis", "garantie", "notice", "diagnostic", "plan", "contrat", "assurance", "photo", "autre"}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Health score — 0..100. Higher is better.
# ---------------------------------------------------------------------------

async def recompute_health_score(db, property_id: str) -> int:
    """Compute the health score of a property. Rules (simple, transparent):
    Start at 100 then subtract points for:
      - each expired warranty on a critical equipment: -5
      - each overdue maintenance reminder: -8
      - each sinistre (incident) in the past 24 months: -6
      - each equipment without brand/model (poor data quality): -1
      - +2 bonus per document uploaded (up to +10)
    Floor at 0, ceil at 100.
    """
    score = 100
    now = now_utc()

    eqs = await db.property_equipments.find({"property_id": property_id}, {"_id": 0}).to_list(500)
    for eq in eqs:
        cat = eq.get("category")
        w = eq.get("warranty_until")
        if w:
            try:
                w_dt = datetime.fromisoformat(str(w).replace("Z", "+00:00"))
                if w_dt < now and cat in {"chaudiere", "pompe_a_chaleur", "ballon_eau_chaude", "panneaux_solaires"}:
                    score -= 5
            except Exception:
                pass
        if not eq.get("brand") and not eq.get("model"):
            score -= 1

    rems = await db.property_reminders.find(
        {"property_id": property_id, "status": "pending"}, {"_id": 0}
    ).to_list(500)
    for r in rems:
        try:
            due = datetime.fromisoformat(str(r.get("due_date")).replace("Z", "+00:00"))
            if due < now:
                score -= 8
        except Exception:
            pass

    two_years_ago = (now - timedelta(days=730)).isoformat()
    sinistres = await db.property_events.count_documents(
        {"property_id": property_id, "event_type": "sinistre", "event_date": {"$gte": two_years_ago}}
    )
    score -= 6 * sinistres

    docs_count = await db.property_documents.count_documents({"property_id": property_id})
    score += min(10, docs_count * 2)

    score = max(0, min(100, score))
    await db.properties.update_one(
        {"property_id": property_id},
        {"$set": {"health_score": score, "updated_at": now.isoformat()}},
    )
    return score


# ---------------------------------------------------------------------------
# Reminders — auto-generation on equipment insert
# ---------------------------------------------------------------------------

async def generate_reminders_for_equipment(db, equipment: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Create pending reminders (entretien + garantie expiring) for a new equipment.
    Idempotent per (property_id, equipment_id, reminder_type): skips existing.
    """
    reminders: List[Dict[str, Any]] = []
    cat = equipment.get("category", "autre")
    meta = EQUIPMENT_CATEGORIES.get(cat, EQUIPMENT_CATEGORIES["autre"])
    _, _, maint_months, _ = meta

    ref_date_str = (
        equipment.get("last_maintenance_at")
        or equipment.get("installed_at")
        or now_utc().date().isoformat()
    )
    try:
        ref_date = datetime.fromisoformat(str(ref_date_str))
    except Exception:
        ref_date = now_utc()

    if maint_months > 0:
        next_maint = ref_date + timedelta(days=maint_months * 30)
        existing = await db.property_reminders.find_one({
            "property_id": equipment["property_id"],
            "equipment_id": equipment["equipment_id"],
            "reminder_type": "entretien",
            "status": {"$in": ["pending", "upcoming", "due"]},
        })
        if not existing:
            r = {
                "reminder_id": new_id("rem"),
                "user_id": equipment["user_id"],
                "property_id": equipment["property_id"],
                "equipment_id": equipment["equipment_id"],
                "reminder_type": "entretien",
                "title": f"Entretien {meta[0]}",
                "due_on": next_maint.date().isoformat(),
                "due_date": next_maint.date().isoformat(),  # legacy alias
                "frequency": "yearly" if maint_months == 12 else None,
                "status": "upcoming",
                "auto_generated": True,
                "created_at": now_utc().isoformat(),
            }
            reminders.append(r)

    warranty = equipment.get("warranty_until")
    if warranty:
        try:
            w_dt = datetime.fromisoformat(str(warranty))
            warn = w_dt - timedelta(days=30)
            if warn > now_utc():
                existing = await db.property_reminders.find_one({
                    "property_id": equipment["property_id"],
                    "equipment_id": equipment["equipment_id"],
                    "reminder_type": "garantie",
                    "status": {"$in": ["pending", "upcoming", "due"]},
                })
                if not existing:
                    r = {
                        "reminder_id": new_id("rem"),
                        "user_id": equipment["user_id"],
                        "property_id": equipment["property_id"],
                        "equipment_id": equipment["equipment_id"],
                        "reminder_type": "garantie",
                        "title": f"Fin de garantie: {meta[0]}",
                        "due_on": warn.date().isoformat(),
                        "due_date": warn.date().isoformat(),
                        "frequency": "once",
                        "status": "upcoming",
                        "auto_generated": True,
                        "created_at": now_utc().isoformat(),
                    }
                    reminders.append(r)
        except Exception:
            pass

    if reminders:
        await db.property_reminders.insert_many([dict(r) for r in reminders])
    return reminders


# ---------------------------------------------------------------------------
# Budget aggregation
# ---------------------------------------------------------------------------

async def compute_budget_stats(db, property_id: str) -> Dict[str, Any]:
    """Aggregate cost from property_events for charts."""
    events = await db.property_events.find(
        {"property_id": property_id, "cost_cents": {"$ne": None}},
        {"_id": 0, "event_date": 1, "event_type": 1, "cost_cents": 1, "artisan_name": 1},
    ).to_list(1000)

    total_cents = 0
    by_month: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    by_artisan: Dict[str, int] = {}
    for e in events:
        cents = int(e.get("cost_cents") or 0)
        total_cents += cents
        d = e.get("event_date", "")
        month_key = str(d)[:7]  # YYYY-MM
        by_month[month_key] = by_month.get(month_key, 0) + cents
        et = e.get("event_type", "autre")
        by_type[et] = by_type.get(et, 0) + cents
        a = e.get("artisan_name")
        if a:
            by_artisan[a] = by_artisan.get(a, 0) + cents

    def sorted_by_month() -> List[Dict[str, Any]]:
        keys = sorted(by_month.keys())[-12:]
        return [{"month": k, "cents": by_month[k]} for k in keys]

    def sorted_by_type() -> List[Dict[str, Any]]:
        return [{"type": t, "cents": c} for t, c in sorted(by_type.items(), key=lambda x: -x[1])]

    def top_artisans() -> List[Dict[str, Any]]:
        return [
            {"name": n, "cents": c}
            for n, c in sorted(by_artisan.items(), key=lambda x: -x[1])[:5]
        ]

    return {
        "total_cents": total_cents,
        "events_count": len(events),
        "by_month": sorted_by_month(),
        "by_type": sorted_by_type(),
        "top_artisans": top_artisans(),
    }


# ---------------------------------------------------------------------------
# Public passport view — sanitized read-only projection
# ---------------------------------------------------------------------------

async def public_passport(db, token: str) -> Optional[Dict[str, Any]]:
    prop = await db.properties.find_one({"share_token": token}, {"_id": 0})
    if not prop:
        return None
    eqs = await db.property_equipments.find(
        {"property_id": prop["property_id"]},
        {"_id": 0, "user_id": 0, "installer_phone": 0, "notes": 0},
    ).to_list(200)
    events = await db.property_events.find(
        {"property_id": prop["property_id"]},
        {"_id": 0, "user_id": 0, "description": 0},
    ).sort("event_date", -1).to_list(50)
    return {
        "property": {
            "label": prop.get("label"),
            "property_type": prop.get("property_type"),
            "city": prop.get("city"),
            "postal_code": prop.get("postal_code"),
            "surface_m2": prop.get("surface_m2"),
            "year_built": prop.get("year_built"),
            "rooms": prop.get("rooms"),
            "dpe_grade": prop.get("dpe_grade"),
            "cover_color": prop.get("cover_color"),
            "health_score": prop.get("health_score", 100),
        },
        "equipments": eqs,
        "events": events,
    }
