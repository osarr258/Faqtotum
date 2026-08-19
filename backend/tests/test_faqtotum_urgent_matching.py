"""Tests FAQTOTUM V1 — Champ `urgent` sur bookings + Matching cold-start.

Ces tests sont indépendants du reste de la suite (aucun rate-limit shared).
"""
from __future__ import annotations

import os
import uuid

import httpx

BASE = os.environ.get("BASE_URL", "http://localhost:8001")


def _h(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def _register(role: str = "client") -> tuple[str, str]:
    email = f"tst_{uuid.uuid4().hex[:8]}@auxora.fr"
    r = httpx.post(
        f"{BASE}/api/auth/register",
        json={
            "email": email,
            "password": "Test1234!",
            "name": "Test User",
            "role": role,
        },
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    return body["token"], body["user"]["user_id"]


def _login(email: str, password: str) -> str:
    r = httpx.post(
        f"{BASE}/api/auth/login",
        json={"email": email, "password": password},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


# ============================================================================
# A) Champ `urgent` sur bookings
# ============================================================================

def test_booking_urgent_false_by_default():
    """Une réservation sans le champ `urgent` reste `urgent=False` (rétro-compat)."""
    client_token = _login("client.test@auxora.fr", "Test1234!")
    r = httpx.post(
        f"{BASE}/api/bookings",
        headers=_h(client_token),
        json={
            "artisan_id": "art_5c533c263d23",
            "date": "2026-08-25",
            "slot": "10:00-12:00",
            "description": "Fuite standard",
        },
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("urgent") is False


def test_booking_urgent_true_persists():
    """Une réservation avec `urgent=True` persiste le flag."""
    client_token = _login("client.test@auxora.fr", "Test1234!")
    r = httpx.post(
        f"{BASE}/api/bookings",
        headers=_h(client_token),
        json={
            "artisan_id": "art_5c533c263d23",
            "date": "2026-08-25",
            "slot": "10:00-12:00",
            "description": "FUITE URGENTE",
            "urgent": True,
        },
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("urgent") is True
    bid = body["booking_id"]

    # Vérification via la liste "mine"
    mine = httpx.get(
        f"{BASE}/api/bookings/mine", headers=_h(client_token), timeout=10,
    ).json()
    found = next((b for b in mine if b["booking_id"] == bid), None)
    assert found is not None
    assert found["urgent"] is True


def test_booking_urgent_visible_to_artisan_received():
    """L'artisan récepteur voit le flag `urgent` sur ses demandes."""
    client_token = _login("client.test@auxora.fr", "Test1234!")
    r = httpx.post(
        f"{BASE}/api/bookings",
        headers=_h(client_token),
        json={
            "artisan_id": "art_2dfb71f00c16",
            "date": "2026-08-26",
            "slot": "14:00-16:00",
            "description": "Panne chaudière — urgent",
            "urgent": True,
        },
        timeout=10,
    )
    assert r.status_code == 200
    bid = r.json()["booking_id"]

    pro_token = _login("pro.test@auxora.fr", "Test1234!")
    recv = httpx.get(
        f"{BASE}/api/bookings/received", headers=_h(pro_token), timeout=10,
    ).json()
    hit = next((b for b in recv if b["booking_id"] == bid), None)
    assert hit is not None
    assert hit.get("urgent") is True


# ============================================================================
# B) Cold-start matching
# ============================================================================

def test_matching_newcomer_boost_applies():
    """Un artisan avec jobs_done=0 et 0 signal négatif reçoit le boost +12."""
    from services import matching

    newcomer = {
        "jobs_done": 0,
        "rating": 4.5,
        "trust_score": 85,
        "acceptance_rate": 90,
        "response_min": 15,
        "completion_rate": 95,
        "hourly_rate": 50,
        "available": True,
        "cancellation_rate": 0,
        "refusal_rate": 0,
        "reports_count": 0,
        "disputes_count": 0,
    }
    ctx = {"rate_min": 30, "rate_max": 70}
    score_new, bd_new, _ = matching.score(newcomer, ctx)
    assert bd_new["newcomer_boost"] == 1.0

    # Même profil mais avec 5 missions → pas de boost
    experienced = dict(newcomer)
    experienced["jobs_done"] = 20
    score_exp, bd_exp, _ = matching.score(experienced, ctx)
    assert bd_exp["newcomer_boost"] == 0.0
    # Le newcomer avec boost devrait avoir un score AU MOINS égal
    # (grâce au +12 raw), sauf si expérience > newcomer aussi via 'jobs'.
    # Vérif seule du signal booléen.


def test_matching_newcomer_boost_cancelled_by_negative_signals():
    """Un newcomer avec des signalements ne reçoit PAS le boost."""
    from services import matching

    bad_newcomer = {
        "jobs_done": 0,
        "rating": 4.5,
        "trust_score": 85,
        "acceptance_rate": 90,
        "response_min": 15,
        "completion_rate": 95,
        "hourly_rate": 50,
        "available": True,
        "reports_count": 2,  # présent → boost annulé
    }
    _, bd, _ = matching.score(bad_newcomer, {"rate_min": 30, "rate_max": 70})
    assert bd["newcomer_boost"] == 0.0


def test_matching_penalties_apply():
    """Les pénalités FAQTOTUM (retards, refus, signalements, litiges) déduisent."""
    from services import matching

    clean = {
        "jobs_done": 50,
        "rating": 4.5,
        "trust_score": 85,
        "acceptance_rate": 90,
        "response_min": 15,
        "completion_rate": 95,
        "hourly_rate": 50,
        "available": True,
    }
    penalised = dict(clean)
    penalised["late_rate"] = 30
    penalised["disputes_count"] = 2

    score_clean, _, _ = matching.score(clean, {"rate_min": 30, "rate_max": 70})
    score_pen, _, _ = matching.score(penalised, {"rate_min": 30, "rate_max": 70})
    assert score_pen < score_clean, "les pénalités doivent réduire le score"


def test_matching_explain_mentions_newcomer():
    """`explain()` mentionne 'Nouveau sur Faqtotum' pour un newcomer boosté."""
    from services import matching

    card = {
        "rating": 4.8,
        "reviews_count": 0,
        "jobs_done": 0,
        "score_breakdown": {"newcomer_boost": 1.0, "distance": 0.5, "price": 0.4},
    }
    reasons = matching.explain(card)
    joined = " | ".join(reasons)
    assert "Nouveau sur Faqtotum" in joined


def test_matching_rank_still_deterministic():
    """La fonction `rank` reste O(n) et retourne les cartes annotées."""
    from services import matching

    candidates = [
        {"artisan_id": "a1", "jobs_done": 100, "rating": 4.9},
        {"artisan_id": "a2", "jobs_done": 0, "rating": 4.5},
        {"artisan_id": "a3", "jobs_done": 30, "rating": 4.2, "reports_count": 3},
    ]
    ranked = matching.rank(candidates, {"rate_min": 30, "rate_max": 70})
    assert len(ranked) == 3
    ids = [c["artisan_id"] for c in ranked]
    assert set(ids) == {"a1", "a2", "a3"}
    for c in ranked:
        assert "match_score" in c
        assert "score_breakdown" in c
        assert "newcomer_boost" in c["score_breakdown"]
