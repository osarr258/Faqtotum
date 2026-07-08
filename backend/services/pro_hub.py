"""
ProConnect / Auxora — Professional Hub
======================================
The "digital HQ" for every pro. Aggregates existing signals (Trust, jobs,
transfers, response times) and adds Community feed, Academy (placeholders),
Marketing (placeholders), AI Business Coach (deterministic recommendations
based on Trust Engine breakdown).

Design invariant: no DB coupling — server.py owns persistence.
"""
from __future__ import annotations
from typing import Any, Dict, List

# --- Academy content (architecture only — categories + curated cards) ------
ACADEMY_CATEGORIES = [
    {"key": "business",         "label": "Business & gestion",     "icon": "briefcase"},
    {"key": "sales",            "label": "Vente & devis",          "icon": "trending-up"},
    {"key": "customer_service", "label": "Relation client",        "icon": "happy"},
    {"key": "technical",        "label": "Savoir-faire technique", "icon": "hammer"},
    {"key": "marketing",        "label": "Marketing & visibilité", "icon": "megaphone"},
    {"key": "legal",            "label": "Juridique & assurance",  "icon": "shield"},
    {"key": "platform",         "label": "Tutoriels Auxora",       "icon": "book"},
]

ACADEMY_CARDS = [
    {"key": "biz_pricing",       "category": "business",         "title": "Fixer les bons tarifs en 2026",        "duration_min": 8,  "status": "coming_soon"},
    {"key": "sales_devis",       "category": "sales",            "title": "Rédiger un devis qui convertit",       "duration_min": 12, "status": "coming_soon"},
    {"key": "cs_reviews",        "category": "customer_service", "title": "Obtenir 5 étoiles à chaque mission",   "duration_min": 6,  "status": "coming_soon"},
    {"key": "tech_diagnostic",   "category": "technical",        "title": "Diagnostic rapide chaudière moderne",  "duration_min": 15, "status": "coming_soon"},
    {"key": "mkt_social",        "category": "marketing",        "title": "Instagram pour artisans",              "duration_min": 10, "status": "coming_soon"},
    {"key": "legal_rc",          "category": "legal",            "title": "Assurance RC Pro — l'essentiel",       "duration_min": 8,  "status": "coming_soon"},
    {"key": "platform_start",    "category": "platform",         "title": "Bien démarrer sur Auxora",             "duration_min": 5,  "status": "coming_soon"},
]

# --- Marketing tools (placeholders / architecture) ------------------------
MARKETING_MODULES = [
    {"key": "promotion",       "title": "Promotions ponctuelles",  "status": "coming_soon"},
    {"key": "discount_camp",   "title": "Campagne de remise",      "status": "coming_soon"},
    {"key": "featured_profile","title": "Mise en avant profil",    "status": "coming_soon"},
    {"key": "seasonal",        "title": "Offres saisonnières",     "status": "coming_soon"},
    {"key": "referral_camp",   "title": "Campagne de parrainage",  "status": "coming_soon"},
]

# --- AI Business Coach — deterministic reco selection --------------------

COACH_RECOMMENDATIONS = {
    "identity_verified":     ("Complétez la vérification d'identité — piece + selfie < 5 min.", "shield-checkmark", 5),
    "insurance_verified":    ("Uploadez votre attestation d'assurance RC Pro — visible sur votre profil.", "umbrella", 4),
    "business_registered":   ("Renseignez votre SIRET pour débloquer les paiements Stripe Connect.", "briefcase", 5),
    "response_speed":        ("Objectif : répondre en < 15 min. Activez les notifications.", "flash", 4),
    "arrival_time":          ("Améliorez votre temps d'arrivée moyen — planifiez à l'avance.", "time", 3),
    "punctuality":           ("Ponctualité 100 % — chaque retard baisse votre Trust Score.", "checkmark-done", 4),
    "cancellation_rate":     ("Réduisez vos annulations sous les 3 % — bloquez vos indispos.", "close-circle", 4),
    "acceptance_rate":       ("Acceptez plus de missions ou affinez vos zones/tarifs.", "add-circle", 3),
    "completion_rate":       ("Terminez chaque mission acceptée pour éviter les pénalités.", "checkmark-circle", 5),
    "customer_satisfaction": ("Envoyez un mini-message post-mission — booste vos avis.", "chatbubbles", 4),
    "customer_rating":       ("Améliorez votre note en soignant la relation client.", "star", 5),
    "jobs_completed":        ("Chaque mission compte — visez le prochain palier de badge.", "trophy", 3),
    "recent_activity":       ("Connectez-vous au moins 1×/semaine pour rester visible.", "wifi", 3),
    "availability":          ("Passez en 'disponible' pour recevoir plus de demandes.", "toggle", 3),
    "emergency_capability":  ("Activez l'option Urgence pour +30 % de visibilité.", "alert-circle", 4),
    "platform_loyalty":      ("Votre ancienneté booste votre Trust chaque mois.", "ribbon", 2),
    "years_experience":      ("Renseignez précisément vos années d'expérience.", "school", 2),
}

def coach_recommendations(breakdown: Dict[str, float], badges: List[Dict[str, Any]],
                          jobs_done: int, trust_score: int) -> List[Dict[str, Any]]:
    """Return up to 5 personalized recommendations, ranked by potential impact.

    Combines:
    - Low-scored factors (< 0.6) — biggest headroom
    - Missing verifications (identity/insurance/business) — quick wins
    - Job milestones (25/100/500/1000) — next badge
    """
    recos: List[Dict[str, Any]] = []
    for factor, value in (breakdown or {}).items():
        if value >= 0.7:
            continue
        rec = COACH_RECOMMENDATIONS.get(factor)
        if not rec:
            continue
        text, icon, impact = rec
        recos.append({
            "key": factor, "title": text, "icon": icon,
            "impact": impact, "current": round(value, 2),
            "kind": "improvement",
        })
    # Job milestone reco
    milestones = [25, 100, 500, 1000]
    next_ms = next((m for m in milestones if jobs_done < m), None)
    if next_ms:
        needed = next_ms - jobs_done
        recos.append({
            "key": "next_badge", "kind": "milestone",
            "title": f"Plus que {needed} mission(s) avant votre badge {next_ms}+.",
            "icon": "trophy", "impact": 3, "current": jobs_done, "target": next_ms,
        })
    # Trust milestone
    if trust_score < 90:
        recos.append({
            "key": "trust_90", "kind": "milestone",
            "title": f"Trust Score {trust_score}/100 — visez 90+ pour la carte 'Fortement recommandé'.",
            "icon": "sparkles", "impact": 4, "current": trust_score, "target": 90,
        })
    recos.sort(key=lambda r: -r["impact"])
    return recos[:6]


def profile_completion(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Weighted profile completion — used in the pro dashboard progress bar."""
    checks = [
        ("logo",             bool(profile.get("logo")),                                 10),
        ("cover",            bool(profile.get("cover")),                                 8),
        ("bio",              bool((profile.get("bio") or "").strip()),                  10),
        ("services",         len(profile.get("services") or []) > 0,                    10),
        ("areas",            len(profile.get("areas_covered") or []) > 0,                8),
        ("opening_hours",    bool(profile.get("opening_hours")),                         5),
        ("certifications",   len(profile.get("certifications") or []) > 0,               8),
        ("insurance",        profile.get("insurance_verified") is True,                 10),
        ("identity",         profile.get("identity_verified") is True,                  10),
        ("business",         profile.get("business_registered") is True,                 8),
        ("languages",        len(profile.get("languages") or []) > 0,                    5),
        ("website_or_social",bool(profile.get("website") or profile.get("social")),      4),
        ("hourly_rate",      bool(profile.get("hourly_rate")),                           4),
    ]
    total_weight = sum(w for _, _, w in checks)
    scored = sum(w for _, ok, w in checks if ok)
    completion_pct = int(round(scored / total_weight * 100))
    missing = [{"key": k, "weight": w} for k, ok, w in checks if not ok]
    return {"completion_pct": completion_pct, "missing": missing, "checks_count": len(checks), "checks_ok": sum(1 for _, ok, _ in checks if ok)}
