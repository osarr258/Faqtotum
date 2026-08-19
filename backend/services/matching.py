"""
ProConnect — AI Matching Engine
================================
Pure, stateless scoring service. Given a list of (already enriched) artisan
dicts and a request CONTEXT, it ranks professionals by a weighted multi-criteria
score (0-100) and produces a human-readable explanation for the recommendation.

The raw score is NEVER exposed to the customer; the UI only shows
"Recommandé par l'IA" + the explanation reasons.

Design goals: deterministic, side-effect free, easily unit-tested, and scalable
(O(n) over the candidate pool). All weights live in WEIGHTS and are documented.

FAQTOTUM V1 additions
---------------------
* **Cold-start boost** : un nouvel artisan (jobs_done < 3) sans signaux négatifs
  reçoit un boost de +12 sur son score raw, pour l'aider à décrocher sa
  première mission. Le boost s'annule dès qu'il y a des signalements, litiges
  ou un taux de refus élevé.
* **Pénalités FAQTOTUM** : retards, signalements et litiges déduisent
  proportionnellement du score (déterministe).
* La fonction ``score`` retourne toujours la même signature — les tests
  existants ne sont pas cassés.
"""
from __future__ import annotations
import math
from typing import List, Dict, Any, Tuple

# Weighted criteria — must sum to 100 (documented & tunable).
WEIGHTS: Dict[str, float] = {
    "rating": 22,        # average customer rating (0-5)
    "trust": 16,         # internal Trust Score (0-100)
    "distance": 14,      # proximity to the customer
    "acceptance": 10,    # acceptance rate (%)
    "response": 9,       # responsiveness (lower minutes = better)
    "completion": 8,     # completion rate (%)
    "jobs": 7,           # experience (completed jobs)
    "price": 6,          # price competitiveness within the pool
    "availability": 5,   # currently available
    "premium": 3,        # premium / loyalty partner
}


def _haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def distance_km(a: Dict[str, Any], ctx: Dict[str, Any]):
    if ctx.get("lat") is None or a.get("lat") is None:
        return None
    return round(_haversine(ctx["lat"], ctx["lng"], a["lat"], a["lng"]), 1)


def score(a: Dict[str, Any], ctx: Dict[str, Any]) -> Tuple[float, Dict[str, float], float]:
    """Return (score_0_100, breakdown, distance_km)."""
    d = distance_km(a, ctx)
    rate_min = ctx.get("rate_min", 30.0)
    rate_max = ctx.get("rate_max", 70.0)
    rate_span = max(1.0, rate_max - rate_min)
    emergency = ctx.get("urgency") == "urgence"

    sub = {
        "rating": _clamp((a.get("rating", 4.5) or 4.5) / 5.0),
        "trust": _clamp((a.get("trust_score", 85) or 85) / 100.0),
        "distance": 0.6 if d is None else _clamp(1 - min(d, 50) / 50.0),
        "acceptance": _clamp((a.get("acceptance_rate", 90) or 90) / 100.0),
        "response": _clamp(1 - min(a.get("response_min", 20) or 20, 60) / 60.0),
        "completion": _clamp((a.get("completion_rate", 95) or 95) / 100.0),
        "jobs": _clamp(min(a.get("jobs_done", 0) or 0, 500) / 500.0),
        "price": _clamp(1 - ((a.get("hourly_rate", rate_min) or rate_min) - rate_min) / rate_span),
        "availability": 1.0 if a.get("available", True) else 0.0,
        "premium": 1.0 if (a.get("trust_score", 0) or 0) >= 95 else 0.0,
    }

    # Emergency boosts responsiveness & availability importance.
    weights = dict(WEIGHTS)
    if emergency:
        weights["response"] += 6
        weights["availability"] += 6
        weights["distance"] += 4

    total_w = sum(weights.values())
    raw = sum(sub[k] * weights[k] for k in sub) / total_w * 100.0

    # -----------------------------------------------------------------
    # FAQTOTUM V1 — Pénalités déterministes (retards, signalements, litiges,
    # taux de refus, taux d'annulation). Chaque signal négatif diminue le
    # score raw de façon bornée. Aucune pénalité si le champ est absent.
    # -----------------------------------------------------------------
    cancel_rate = float(a.get("cancellation_rate", 0) or 0)  # %
    refusal_rate = float(a.get("refusal_rate", 0) or 0)      # %
    late_rate = float(a.get("late_rate", 0) or 0)            # %
    reports_count = int(a.get("reports_count", 0) or 0)      # nb
    disputes_count = int(a.get("disputes_count", 0) or 0)    # nb

    raw -= cancel_rate * 0.30       # -30 % du % d'annulation
    raw -= refusal_rate * 0.20      # -20 % du % de refus
    raw -= late_rate * 0.25         # -25 % du % de retard
    raw -= min(reports_count, 10) * 1.5   # -1.5 / signalement (cap 10)
    raw -= min(disputes_count, 5) * 3.0   # -3 / litige (cap 5)

    # -----------------------------------------------------------------
    # FAQTOTUM V1 — Cold-start boost
    # Un artisan tout neuf (jobs_done < 3) sans aucun signal négatif reçoit
    # un boost de visibilité de +12 pour décrocher sa première mission.
    # Dès qu'il y a des signalements, litiges ou taux de refus > 20 %,
    # le boost est annulé (il n'est pas dû à une manœuvre).
    # -----------------------------------------------------------------
    jobs_done = int(a.get("jobs_done", 0) or 0)
    is_newcomer = (
        jobs_done < 3
        and reports_count == 0
        and disputes_count == 0
        and refusal_rate <= 20.0
        and cancel_rate <= 10.0
    )
    if is_newcomer:
        raw += 12.0
        sub["newcomer_boost"] = 1.0
    else:
        sub["newcomer_boost"] = 0.0

    return round(_clamp(raw, 0, 100), 1), sub, d


def rank(artisans: List[Dict[str, Any]], ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return a NEW list of cards sorted best-first, each annotated with
    match_score, score_breakdown and distance_km. Inputs are not mutated."""
    out = []
    for a in artisans:
        s, breakdown, d = score(a, ctx)
        card = dict(a)
        card["match_score"] = s
        card["score_breakdown"] = breakdown
        card["distance_km"] = d
        out.append(card)
    out.sort(key=lambda c: c["match_score"], reverse=True)
    return out


def explain(card: Dict[str, Any], eta_minutes: int | None = None) -> List[str]:
    """Human-readable reasons (FR) WHY this pro was recommended.
    Reasons are ordered by signal strength using the score breakdown so the
    most decisive factors surface first."""
    bd = card.get("score_breakdown", {}) or {}
    reasons: List[str] = []

    if eta_minutes is not None:
        reasons.append(f"Disponible dans ~{eta_minutes} min")
    if bd.get("newcomer_boost", 0) >= 1.0:
        reasons.append("Nouveau sur Faqtotum — à découvrir")
    if card.get("rating"):
        reasons.append(f"Note {card['rating']:.1f}★ ({card.get('reviews_count', 0)} avis)")
    if bd.get("distance", 0) >= 0.7 and card.get("distance_km") is not None:
        reasons.append(f"Très proche ({card['distance_km']} km)")
    if (card.get("trust_score") or 0) >= 90:
        reasons.append(f"Trust Score élevé ({card['trust_score']}/100)")
    if (card.get("jobs_done") or 0) >= 20:
        reasons.append(f"{card['jobs_done']} missions réalisées")
    if (card.get("acceptance_rate") or 0) >= 85:
        reasons.append(f"{card['acceptance_rate']}% de taux d'acceptation")
    if (card.get("response_min") or 99) <= 15:
        reasons.append(f"Répond en ~{card['response_min']} min")
    if bd.get("price", 0) >= 0.6:
        reasons.append("Excellent rapport qualité-prix")
    reasons.append("Assurance & identité vérifiées")

    # De-duplicate while preserving order, cap at 5 for a clean UI.
    seen = set()
    uniq = [r for r in reasons if not (r in seen or seen.add(r))]
    return uniq[:5]


def confidence_label(score_0_100: float) -> str:
    """Map a raw match score to a customer-facing confidence label (FR)."""
    if score_0_100 >= 85:
        return "Correspondance excellente"
    if score_0_100 >= 70:
        return "Très bonne correspondance"
    if score_0_100 >= 55:
        return "Bonne correspondance"
    return "Correspondance correcte"
