"""
ProConnect / Auxora — Growth & Retention Engine
================================================
Pure helpers for pro levels, loyalty points, maintenance planner suggestions
and property health mapping. Zero DB coupling — server.py persists.
"""
from __future__ import annotations
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta, timezone
import uuid

# ---------------------------------------------------------------------------
# Pro levels — NEVER driven by subscription. Only quality + Trust + jobs.
# ---------------------------------------------------------------------------

LEVELS: List[Dict[str, Any]] = [
    {"key": "bronze",   "label": "Bronze",   "trust_min": 50, "jobs_min": 5,    "color": "#B77749"},
    {"key": "silver",   "label": "Silver",   "trust_min": 70, "jobs_min": 25,   "color": "#B8B8C0"},
    {"key": "gold",     "label": "Gold",     "trust_min": 85, "jobs_min": 100,  "color": "#D4AF6A"},
    {"key": "platinum", "label": "Platinum", "trust_min": 92, "jobs_min": 500,  "color": "#E6E6EE"},
    {"key": "elite",    "label": "Elite",    "trust_min": 95, "jobs_min": 1000, "color": "#8A2BE2"},
]

def pro_level(trust_score: int, jobs_done: int) -> Dict[str, Any]:
    """Return the highest level the pro qualifies for + progress to next."""
    current = LEVELS[0]
    for lvl in LEVELS:
        if trust_score >= lvl["trust_min"] and jobs_done >= lvl["jobs_min"]:
            current = lvl
    idx = LEVELS.index(current)
    nxt = LEVELS[idx + 1] if idx < len(LEVELS) - 1 else None
    if nxt is None:
        return {**current, "next_level": None, "progress_pct": 100}
    # Progress is min of the two axes (trust + jobs) — the weaker limits us.
    trust_range = max(1, nxt["trust_min"] - current["trust_min"])
    jobs_range = max(1, nxt["jobs_min"] - current["jobs_min"])
    tp = max(0, min(100, int((trust_score - current["trust_min"]) / trust_range * 100)))
    jp = max(0, min(100, int((jobs_done - current["jobs_min"]) / jobs_range * 100)))
    return {**current, "next_level": nxt["key"], "next_label": nxt["label"],
            "next_trust_min": nxt["trust_min"], "next_jobs_min": nxt["jobs_min"],
            "progress_pct": min(tp, jp)}

# ---------------------------------------------------------------------------
# Loyalty points earn/redeem tables.
# ---------------------------------------------------------------------------

POINTS_EARN = {
    "booking_completed":       100,
    "review_posted":            25,
    "referral_converted":      500,
    "property_created":         50,
    "equipment_added":          10,
    "maintenance_completed":    75,
}

REWARDS: List[Dict[str, Any]] = [
    {"key": "discount_10",       "label": "10€ de remise",          "points": 1000, "kind": "discount", "amount_cents": 1000},
    {"key": "priority_support",  "label": "Support prioritaire 30j", "points": 2500, "kind": "flag"},
    {"key": "discount_25",       "label": "25€ de remise",          "points": 5000, "kind": "discount", "amount_cents": 2500},
    {"key": "ai_boost",          "label": "Fonctions IA débloquées","points": 7500, "kind": "flag"},
    {"key": "vip_status",        "label": "Statut VIP à vie",       "points": 15000, "kind": "flag"},
]

TIERS = [
    {"key": "member",   "label": "Membre",   "min": 0},
    {"key": "silver",   "label": "Silver",   "min": 500},
    {"key": "gold",     "label": "Gold",     "min": 2000},
    {"key": "platinum", "label": "Platinum", "min": 5000},
    {"key": "vip",      "label": "VIP",      "min": 15000},
]

def loyalty_tier(points: int) -> Dict[str, Any]:
    current = TIERS[0]
    for t in TIERS:
        if points >= t["min"]:
            current = t
    idx = TIERS.index(current)
    nxt = TIERS[idx + 1] if idx < len(TIERS) - 1 else None
    return {"tier": current["key"], "label": current["label"], "next_tier": nxt["key"] if nxt else None, "next_min": nxt["min"] if nxt else None}

# ---------------------------------------------------------------------------
# Property Health mapping (extends insights.average_health).
# ---------------------------------------------------------------------------

def health_label(score: int) -> Dict[str, str]:
    if score >= 90:
        return {"key": "excellent", "label": "Excellent", "color": "#34D399"}
    if score >= 75:
        return {"key": "good", "label": "Bon état", "color": "#22C55E"}
    if score >= 55:
        return {"key": "attention", "label": "À surveiller", "color": "#F0B429"}
    return {"key": "critical", "label": "Critique", "color": "#F87171"}

# ---------------------------------------------------------------------------
# Maintenance planner — deterministic schedule per equipment category.
# ---------------------------------------------------------------------------

MAINTENANCE_INTERVALS_MONTHS = {
    "boiler":           12,
    "heat_pump":        12,
    "water_heater":     24,
    "smoke_detector":   12,
    "roof":             24,
    "panel":            60,
    "vmc":              12,
    "solar":            24,
    "water_softener":    6,
    "ac":               12,
    "ev_charger":       24,
    "windows":          60,
    "doors":            60,
}
MAINTENANCE_LABELS = {
    "boiler":         "Entretien chaudière",
    "heat_pump":      "Inspection pompe à chaleur",
    "water_heater":   "Détartrage chauffe-eau",
    "smoke_detector": "Contrôle détecteur de fumée",
    "roof":           "Inspection toiture",
    "panel":          "Contrôle tableau électrique",
    "vmc":            "Nettoyage VMC",
    "solar":          "Nettoyage panneaux solaires",
    "water_softener": "Régénération adoucisseur",
    "ac":             "Entretien climatisation",
    "ev_charger":     "Contrôle borne VE",
    "windows":        "Révision étanchéité fenêtres",
    "doors":          "Révision portes",
}

def suggest_maintenance(equipment: Dict[str, Any], now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """Given equipment, suggest its next maintenance."""
    now = now or datetime.now(timezone.utc)
    cat = equipment.get("category")
    interval = MAINTENANCE_INTERVALS_MONTHS.get(cat)
    if not interval:
        return None
    base_str = equipment.get("installed_on") or equipment.get("created_at")
    try:
        base = datetime.fromisoformat(base_str) if base_str else now
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
    except Exception:
        base = now
    # Roll base forward by full intervals until we're in the future.
    due = base
    while due <= now:
        due += timedelta(days=30 * interval)
    return {
        "title": MAINTENANCE_LABELS.get(cat, "Entretien"),
        "due_on": due.date().isoformat(),
        "interval_months": interval,
        "equipment_id": equipment.get("equipment_id"),
        "equipment_name": equipment.get("name"),
        "category": cat,
    }

# ---------------------------------------------------------------------------
# Referral codes — deterministic, human-readable.
# ---------------------------------------------------------------------------

def make_referral_code(user_id: str) -> str:
    # Short shareable code: first 3 chars of hex + 5 random hex chars.
    seed = uuid.uuid5(uuid.NAMESPACE_URL, user_id).hex.upper()
    return "AUX" + seed[:5]
