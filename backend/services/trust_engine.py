"""
ProConnect — AI Trust Engine
============================
Production-ready, modular trust scoring for artisan professionals.

Design goals
------------
- **Deterministic**: no randomness. Same inputs → same output.
- **Modular**: every factor is a pure function; weights live in `WEIGHTS`,
  penalties in `PENALTIES`, tuning constants in `THRESHOLDS`.
- **Explainable**: every score exposes a per-factor breakdown + reasons.
- **Persistable**: `compute()` returns primitives suitable for Mongo `$set`.
- **ML-ready**: the same feature vector emitted by `feature_vector()` can be
  fed to a future gradient-boosting/XGBoost model without any refactor.
- **Side-effect free**: does NOT touch the database. Callers persist.

The customer-facing score is 0-100 (never negative, never above 100).
The score is never editable manually — always recomputed from signals.

Callers
-------
- `POST /reviews`, `PATCH /bookings/{id}` (status=completed | declined),
  `POST /disputes` → after mutating the artisan's counters, call
  `trust_engine.persist(db, artisan_id)` to recompute and store.
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# Configuration — every knob lives here so product/ML can tune without code.
# ---------------------------------------------------------------------------

# 20 signals. Weights sum to 100 for readability. Zero means the signal is
# tracked and surfaced in the breakdown but does not affect the composite yet.
WEIGHTS: Dict[str, float] = {
    "identity_verified":       6.0,
    "insurance_verified":      6.0,
    "business_registered":     5.0,
    "years_experience":        5.0,
    "customer_rating":        13.0,   # weighted highest — trust anchor
    "jobs_completed":          7.0,
    "acceptance_rate":         5.0,
    "cancellation_rate":       6.0,   # inverse — high cancellations lower score
    "response_speed":          6.0,
    "arrival_time":            4.0,
    "punctuality":             4.0,
    "dispute_history":         6.0,   # inverse
    "customer_satisfaction":   6.0,
    "completion_rate":         6.0,
    "recent_activity":         4.0,
    "availability":            2.0,
    "distance_relevance":      2.0,   # provided by matching, optional
    "speciality_match":        2.0,   # provided by matching, optional
    "emergency_capability":    2.0,
    "platform_loyalty":        3.0,
}
assert abs(sum(WEIGHTS.values()) - 100.0) < 0.01, "WEIGHTS must sum to 100"

# Manual downward pressure applied AFTER the weighted sum. Additive % points.
PENALTIES: Dict[str, float] = {
    "unresolved_dispute":     5.0,
    "resolved_severe":        3.0,
    "resolved_moderate":      1.5,
    "resolved_minor":         0.5,
    "recent_no_activity_60d": 4.0,
    "high_cancellation_20p":  6.0,
}

THRESHOLDS: Dict[str, float] = {
    "top_rating":              4.8,
    "fast_response_minutes":  15.0,
    "emergency_response_min": 10.0,
    "loyalty_months_gold":    12.0,
    "jobs_bronze":            25.0,
    "jobs_silver":           100.0,
    "jobs_gold":             500.0,
    "jobs_platinum":        1000.0,
}

# ---------------------------------------------------------------------------
# Feature normalizers — pure functions, easy to unit-test in isolation.
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))

def _bool(v: Any) -> float:
    return 1.0 if bool(v) else 0.0

def _months_since(iso: Optional[str]) -> float:
    if not iso:
        return 0.0
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt).days / 30.0)
    except Exception:
        return 0.0

def _days_since(iso: Optional[str]) -> float:
    if not iso:
        return 9999.0
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt).days)
    except Exception:
        return 9999.0

# Each `_f_*` returns a value in [0, 1] — the normalized signal strength.
def _f_identity(a):           return _bool(a.get("identity_verified", True))
def _f_insurance(a):          return _bool(a.get("insurance_verified", True))
def _f_business(a):           return _bool(a.get("business_registered", True))
def _f_years(a):              return _clamp((a.get("years_experience", 5) or 5) / 20.0)
def _f_rating(a):             return _clamp((a.get("rating", 4.5) or 4.5) / 5.0)
def _f_jobs(a):               return _clamp((a.get("jobs_done", 0) or 0) / 500.0)
def _f_acceptance(a):         return _clamp((a.get("acceptance_rate", 90) or 90) / 100.0)
def _f_cancellation(a):       return _clamp(1.0 - (a.get("cancellation_rate", 0) or 0) / 20.0)
def _f_response(a):           return _clamp(1.0 - min(a.get("response_min", 20) or 20, 60) / 60.0)
def _f_arrival(a):            return _clamp(1.0 - min(a.get("avg_arrival_min", 30) or 30, 90) / 90.0)
def _f_punctuality(a):        return _clamp((a.get("punctuality_rate", 95) or 95) / 100.0)
def _f_disputes(a):
    unresolved = a.get("disputes_unresolved", 0) or 0
    resolved = a.get("disputes_resolved", 0) or 0
    # Unresolved weigh 3x heavier than resolved.
    return _clamp(1.0 - min(unresolved * 3 + resolved, 10) / 10.0)
def _f_satisfaction(a):       return _clamp((a.get("satisfaction_rate", 92) or 92) / 100.0)
def _f_completion(a):         return _clamp((a.get("completion_rate", 95) or 95) / 100.0)
def _f_recent(a):
    d = _days_since(a.get("last_active_at") or a.get("updated_at"))
    return _clamp(1.0 - min(d, 90) / 90.0)
def _f_availability(a):       return _bool(a.get("available", True))
def _f_distance(a):           return _clamp((a.get("distance_relevance") or 0.5))
def _f_speciality(a):         return _clamp((a.get("speciality_match") or 0.7))
def _f_emergency(a):          return _bool(a.get("emergency_capable", False))
def _f_loyalty(a):
    months = _months_since(a.get("member_since") or a.get("created_at"))
    return _clamp(months / THRESHOLDS["loyalty_months_gold"])

FEATURES = {
    "identity_verified":      _f_identity,
    "insurance_verified":     _f_insurance,
    "business_registered":    _f_business,
    "years_experience":       _f_years,
    "customer_rating":        _f_rating,
    "jobs_completed":         _f_jobs,
    "acceptance_rate":        _f_acceptance,
    "cancellation_rate":      _f_cancellation,
    "response_speed":         _f_response,
    "arrival_time":           _f_arrival,
    "punctuality":            _f_punctuality,
    "dispute_history":        _f_disputes,
    "customer_satisfaction":  _f_satisfaction,
    "completion_rate":        _f_completion,
    "recent_activity":        _f_recent,
    "availability":           _f_availability,
    "distance_relevance":     _f_distance,
    "speciality_match":       _f_speciality,
    "emergency_capability":   _f_emergency,
    "platform_loyalty":       _f_loyalty,
}

# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def feature_vector(a: Dict[str, Any]) -> Dict[str, float]:
    """Emit the normalized [0,1] feature vector — the ML-ready input."""
    return {k: round(fn(a), 4) for k, fn in FEATURES.items()}

def compute(a: Dict[str, Any]) -> Dict[str, Any]:
    """Compute the full trust output for a single artisan dict.

    Returns
    -------
    {
      "trust_score": int (0-100, rounded),
      "breakdown": {factor: normalized_value},
      "contributions": {factor: contribution_in_pts},
      "penalties_applied": [ {reason, points} ],
      "confidence_level": "excellent" | "strong" | "solid" | "developing",
      "computed_at": iso,
    }
    """
    fv = feature_vector(a)
    contributions = {k: round(fv[k] * WEIGHTS[k], 3) for k in FEATURES}
    raw = sum(contributions.values())

    penalties: List[Dict[str, Any]] = []
    if (a.get("disputes_unresolved") or 0) > 0:
        pts = PENALTIES["unresolved_dispute"] * (a["disputes_unresolved"])
        raw -= pts
        penalties.append({"reason": "unresolved_dispute", "points": round(pts, 2)})
    if (a.get("cancellation_rate") or 0) >= 20:
        raw -= PENALTIES["high_cancellation_20p"]
        penalties.append({"reason": "high_cancellation_20p", "points": PENALTIES["high_cancellation_20p"]})
    if _days_since(a.get("last_active_at") or a.get("updated_at")) >= 60:
        raw -= PENALTIES["recent_no_activity_60d"]
        penalties.append({"reason": "recent_no_activity_60d", "points": PENALTIES["recent_no_activity_60d"]})

    final = int(round(_clamp(raw, 0, 100)))
    return {
        "trust_score": final,
        "breakdown": fv,
        "contributions": contributions,
        "penalties_applied": penalties,
        "confidence_level": _confidence_level(final),
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

def _confidence_level(score: int) -> str:
    if score >= 90:
        return "excellent"
    if score >= 80:
        return "strong"
    if score >= 65:
        return "solid"
    return "developing"

# ---------------------------------------------------------------------------
# Badges — computed from the same signals. Never editable manually.
# ---------------------------------------------------------------------------

BADGE_CATALOG = [
    "verified",
    "insured",
    "background_checked",
    "premium",
    "top_rated",
    "emergency_expert",
    "fast_response",
    "jobs_bronze",       # 25+ jobs
    "jobs_silver",       # 100+
    "jobs_gold",         # 500+
    "jobs_platinum",     # 1000+
    "highly_recommended",
    "loyal_partner",
]

def badges(a: Dict[str, Any], trust_score: Optional[int] = None) -> List[Dict[str, Any]]:
    """Return the badges an artisan qualifies for, with FR labels."""
    ts = trust_score if trust_score is not None else (a.get("trust_score") or 0)
    jobs = a.get("jobs_done", 0) or 0
    rating = a.get("rating", 0) or 0
    resp = a.get("response_min", 99) or 99
    loyalty = _months_since(a.get("member_since") or a.get("created_at"))
    out: List[Dict[str, Any]] = []

    def add(key, label, icon, tier="silver"):
        out.append({"key": key, "label": label, "icon": icon, "tier": tier})

    if a.get("identity_verified", True):
        add("verified", "Identité vérifiée", "shield-checkmark", "silver")
    if a.get("insurance_verified", True):
        add("insured", "Assurance vérifiée", "umbrella", "silver")
    if a.get("background_checked"):
        add("background_checked", "Casier vérifié", "search", "silver")
    if ts >= 95:
        add("premium", "Partenaire Premium", "diamond", "gold")
    if rating >= THRESHOLDS["top_rating"]:
        add("top_rated", "Top noté", "trophy", "gold")
    if a.get("emergency_capable") and resp <= THRESHOLDS["emergency_response_min"]:
        add("emergency_expert", "Expert Urgence", "flash", "gold")
    if resp <= THRESHOLDS["fast_response_minutes"]:
        add("fast_response", "Réponse rapide", "flash-outline", "silver")
    if jobs >= THRESHOLDS["jobs_platinum"]:
        add("jobs_platinum", "1000+ missions", "star", "platinum")
    elif jobs >= THRESHOLDS["jobs_gold"]:
        add("jobs_gold", "500+ missions", "star", "gold")
    elif jobs >= THRESHOLDS["jobs_silver"]:
        add("jobs_silver", "100+ missions", "star-half", "silver")
    elif jobs >= THRESHOLDS["jobs_bronze"]:
        add("jobs_bronze", "25+ missions", "star-outline", "bronze")
    if ts >= 90 and rating >= 4.7 and jobs >= 20:
        add("highly_recommended", "Fortement recommandé", "sparkles", "gold")
    if loyalty >= THRESHOLDS["loyalty_months_gold"]:
        add("loyal_partner", "Partenaire fidèle", "ribbon", "silver")
    return out

# ---------------------------------------------------------------------------
# Explainability — reasons + confidence card
# ---------------------------------------------------------------------------

_LABELS_FR = {
    "identity_verified":     "Identité vérifiée",
    "insurance_verified":    "Assurance vérifiée",
    "business_registered":   "Entreprise enregistrée",
    "years_experience":      "Ancienneté du métier",
    "customer_rating":       "Note clients",
    "jobs_completed":        "Missions réalisées",
    "acceptance_rate":       "Taux d'acceptation",
    "cancellation_rate":     "Peu d'annulations",
    "response_speed":        "Réactivité",
    "arrival_time":          "Temps d'arrivée",
    "punctuality":           "Ponctualité",
    "dispute_history":       "Historique de litiges",
    "customer_satisfaction": "Satisfaction client",
    "completion_rate":       "Missions menées à bien",
    "recent_activity":       "Activité récente",
    "availability":          "Disponibilité",
    "distance_relevance":    "Proximité géographique",
    "speciality_match":      "Spécialité pertinente",
    "emergency_capability":  "Capacité d'urgence",
    "platform_loyalty":      "Ancienneté sur la plateforme",
}

def top_reasons(a: Dict[str, Any], out: Dict[str, Any], k: int = 6) -> List[str]:
    """Return the top-K human-readable reasons a pro is recommended.
    Uses the score contributions to rank the strongest signals first."""
    contribs = out.get("contributions", {}) or {}
    ranked = sorted(contribs.items(), key=lambda kv: kv[1], reverse=True)
    reasons: List[str] = []
    for factor, _ in ranked:
        text = _reason_for(factor, a)
        if text and text not in reasons:
            reasons.append(text)
        if len(reasons) >= k:
            break
    return reasons

def _reason_for(factor: str, a: Dict[str, Any]) -> Optional[str]:
    """Materialize a reason string for a factor, or None if not compelling."""
    if factor == "customer_rating" and (a.get("rating") or 0) >= 4.5:
        return f"Note {a['rating']:.1f}★ ({a.get('reviews_count', 0)} avis)"
    if factor == "jobs_completed" and (a.get("jobs_done") or 0) >= 25:
        return f"{a['jobs_done']} missions réalisées"
    if factor == "response_speed" and (a.get("response_min") or 99) <= 20:
        return f"Répond en ~{a['response_min']} min"
    if factor == "arrival_time" and (a.get("avg_arrival_min") or 99) <= 45:
        return f"Arrive en moyenne en {a['avg_arrival_min']} min"
    if factor == "identity_verified" and a.get("identity_verified", True):
        return "Identité vérifiée"
    if factor == "insurance_verified" and a.get("insurance_verified", True):
        return "Assurance responsabilité civile vérifiée"
    if factor == "business_registered" and a.get("business_registered", True):
        return "Entreprise enregistrée (SIRET)"
    if factor == "acceptance_rate" and (a.get("acceptance_rate") or 0) >= 85:
        return f"{a['acceptance_rate']}% d'acceptation"
    if factor == "completion_rate" and (a.get("completion_rate") or 0) >= 95:
        return f"{a['completion_rate']}% de missions menées à bien"
    if factor == "punctuality" and (a.get("punctuality_rate") or 0) >= 95:
        return f"{a['punctuality_rate']}% de ponctualité"
    if factor == "cancellation_rate" and (a.get("cancellation_rate") or 0) <= 3:
        return "Très peu d'annulations"
    if factor == "customer_satisfaction" and (a.get("satisfaction_rate") or 0) >= 90:
        return f"Satisfaction client {a['satisfaction_rate']}%"
    if factor == "emergency_capability" and a.get("emergency_capable"):
        return "Intervient en urgence"
    if factor == "availability" and a.get("available", True):
        return "Disponible aujourd'hui"
    if factor == "years_experience" and (a.get("years_experience") or 0) >= 5:
        return f"{a['years_experience']} ans d'expérience"
    if factor == "platform_loyalty":
        m = _months_since(a.get("member_since") or a.get("created_at"))
        if m >= 12:
            return f"Membre depuis {int(m // 12)} an(s)"
    return None

def confidence_card(a: Dict[str, Any], out: Dict[str, Any]) -> Dict[str, Any]:
    """The client-facing confidence card (safe fields only)."""
    return {
        "trust_score": out["trust_score"],
        "confidence_level": out["confidence_level"],
        "verified":                a.get("identity_verified", True),
        "insured":                 a.get("insurance_verified", True),
        "business_registered":     a.get("business_registered", True),
        "background_checked":      bool(a.get("background_checked")),
        "avg_response_min":        a.get("response_min"),
        "avg_arrival_min":         a.get("avg_arrival_min"),
        "completion_rate":         a.get("completion_rate"),
        "satisfaction_rate":       a.get("satisfaction_rate"),
        "jobs_done":               a.get("jobs_done"),
        "years_experience":        a.get("years_experience"),
        "emergency_capable":       bool(a.get("emergency_capable")),
        "reasons":                 top_reasons(a, out, k=6),
        "badges":                  badges(a, out["trust_score"]),
    }

# ---------------------------------------------------------------------------
# Artisan scoreboard — improvement recommendations
# ---------------------------------------------------------------------------

def scoreboard(a: Dict[str, Any], out: Dict[str, Any]) -> Dict[str, Any]:
    """Pro-facing dashboard: how the score is built + what to improve."""
    contribs = out.get("contributions", {}) or {}
    # Recommendations: pick low-contribution factors with high potential upside.
    upsides: List[Dict[str, Any]] = []
    fv = out.get("breakdown", {}) or {}
    for factor, value in fv.items():
        headroom = 1.0 - value
        potential = round(headroom * WEIGHTS[factor], 2)
        if potential <= 0.3:
            continue
        upsides.append({
            "factor": factor,
            "label": _LABELS_FR.get(factor, factor),
            "current": value,
            "potential_pts": potential,
            "recommendation": _recommendation_for(factor),
        })
    upsides.sort(key=lambda x: x["potential_pts"], reverse=True)

    # Ranked strongest factors so the pro sees what's already working.
    strengths = [
        {"factor": k, "label": _LABELS_FR.get(k, k), "points": v}
        for k, v in sorted(contribs.items(), key=lambda kv: kv[1], reverse=True)[:5]
    ]

    return {
        "trust_score": out["trust_score"],
        "confidence_level": out["confidence_level"],
        "penalties": out.get("penalties_applied", []),
        "strengths": strengths,
        "improvements": upsides[:5],
        "badges": badges(a, out["trust_score"]),
    }

def _recommendation_for(factor: str) -> str:
    m = {
        "identity_verified":     "Complétez la vérification d'identité (pièce + selfie).",
        "insurance_verified":    "Ajoutez votre attestation d'assurance responsabilité civile.",
        "business_registered":   "Renseignez votre numéro SIRET pour valider l'entreprise.",
        "response_speed":        "Réduisez votre temps de réponse en dessous de 15 min.",
        "arrival_time":          "Améliorez votre temps d'arrivée moyen (planifiez à l'avance).",
        "punctuality":           "Arrivez à l'heure : chaque retard impacte votre score.",
        "cancellation_rate":     "Réduisez vos annulations — bloquez vos indisponibilités.",
        "acceptance_rate":       "Acceptez plus de missions ou définissez mieux vos zones.",
        "completion_rate":       "Terminez chaque mission acceptée pour éviter les pénalités.",
        "customer_satisfaction": "Demandez à vos clients de laisser un avis à la fin.",
        "customer_rating":       "Améliorez votre note moyenne — soignez la relation client.",
        "jobs_completed":        "Continuez à réaliser des missions — l'expérience compte.",
        "dispute_history":       "Résolvez les litiges ouverts via notre équipe support.",
        "recent_activity":       "Restez actif sur la plateforme (au moins 1 connexion/semaine).",
        "availability":          "Passez en 'disponible' pour recevoir plus de demandes.",
        "emergency_capability":  "Activez l'option 'Intervention urgence' pour gagner en visibilité.",
        "platform_loyalty":      "Votre ancienneté augmente votre score chaque mois.",
        "years_experience":      "Renseignez précisément vos années d'expérience.",
    }
    return m.get(factor, "Continuez sur cette lancée.")

# ---------------------------------------------------------------------------
# Disputes — auto-penalty engine
# ---------------------------------------------------------------------------

DISPUTE_SEVERITY = {
    "minor":     {"unresolved_bump": 0, "resolved_bump": 1, "score_delta": -2},
    "moderate":  {"unresolved_bump": 1, "resolved_bump": 0, "score_delta": -6},
    "severe":    {"unresolved_bump": 1, "resolved_bump": 0, "score_delta": -12, "requires_manual_review": True},
}

def dispute_penalty(severity: str) -> Dict[str, Any]:
    """Return the delta counters + score reduction for a dispute severity."""
    s = DISPUTE_SEVERITY.get(severity, DISPUTE_SEVERITY["minor"])
    return {**s, "severity": severity}

# ---------------------------------------------------------------------------
# Smart recommendations — alternatives to a picked candidate
# ---------------------------------------------------------------------------

def smart_alternatives(picked: Dict[str, Any], pool: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Given a picked artisan and the ranked pool, surface up to 5 smart
    alternatives — never returning the picked one."""
    others = [a for a in pool if a.get("artisan_id") != picked.get("artisan_id")]
    if not others:
        return {"alternatives": []}

    def best_by(key_fn, label: str, key: str, reason_fn):
        candidates = [c for c in others if key_fn(c) is not None]
        if not candidates:
            return None
        top = max(candidates, key=key_fn)
        return {
            "key": key,
            "label": label,
            "artisan_id": top.get("artisan_id"),
            "name": top.get("name"),
            "photo": top.get("photo"),
            "rating": top.get("rating"),
            "reason": reason_fn(top),
        }

    picks: List[Optional[Dict[str, Any]]] = [
        # Higher rated
        best_by(lambda c: c.get("rating") if (c.get("rating") or 0) > (picked.get("rating") or 0) else None,
                "Mieux noté", "higher_rated",
                lambda c: f"Note {c.get('rating', 0):.1f}★ ({c.get('reviews_count', 0)} avis)"),
        # Faster response
        best_by(lambda c: -(c.get("response_min") or 999)
                    if (c.get("response_min") or 999) < (picked.get("response_min") or 999) else None,
                "Plus rapide", "faster",
                lambda c: f"Répond en ~{c.get('response_min')} min"),
        # Closer
        best_by(lambda c: -(c.get("distance_km") or 999)
                    if (c.get("distance_km") is not None and picked.get("distance_km") is not None
                        and c["distance_km"] < picked["distance_km"]) else None,
                "Plus proche", "closer",
                lambda c: f"À {c.get('distance_km')} km"),
        # Cheaper
        best_by(lambda c: -(c.get("hourly_rate") or 9999)
                    if (c.get("hourly_rate") or 9999) < (picked.get("hourly_rate") or 9999) else None,
                "Moins cher", "cheaper",
                lambda c: f"{c.get('hourly_rate')} €/h"),
        # Earliest availability (mocked via response_min proxy if no slot data)
        best_by(lambda c: 1 if c.get("available") and not picked.get("available") else None,
                "Disponible plus tôt", "earlier_slot",
                lambda c: "Disponible maintenant"),
    ]
    return {"alternatives": [p for p in picks if p]}

# ---------------------------------------------------------------------------
# Persistence helpers — thin wrappers around Mongo. Kept here so the DB
# integration is trivial from server.py without polluting business logic.
# ---------------------------------------------------------------------------

async def persist(db, artisan_id: str) -> Optional[Dict[str, Any]]:
    """Recompute + persist trust score for a single artisan. Idempotent.
    Returns the full trust output, or None if artisan not found."""
    a = await db.artisan_profiles.find_one({"artisan_id": artisan_id}, {"_id": 0})
    if not a:
        return None
    out = compute(a)
    await db.artisan_profiles.update_one(
        {"artisan_id": artisan_id},
        {"$set": {
            "trust_score": out["trust_score"],
            "trust_breakdown": out["breakdown"],
            "trust_contributions": out["contributions"],
            "trust_penalties": out["penalties_applied"],
            "trust_confidence": out["confidence_level"],
            "trust_computed_at": out["computed_at"],
        }},
    )
    return out
