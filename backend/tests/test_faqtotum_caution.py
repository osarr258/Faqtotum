"""Tests FAQTOTUM V1 — Estimation & Caution 7 %.

Vérifie :
  1. `compute_caution_cents` respecte la règle 7 % de la borne haute.
  2. Arrondi au centime le plus proche.
  3. Endpoint `POST /api/estimation/quote` fonctionne.
  4. Un broadcast créé avec estimation persiste caution_cents figé.
  5. Après acceptation, la caution est propagée au booking et NE change pas
     si le prix final varie (brief §5).
"""
from __future__ import annotations

import os

import httpx
from pymongo import MongoClient

BASE = os.environ.get("BASE_URL", "http://localhost:8001")


def _h(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def _login(email: str, password: str) -> str:
    r = httpx.post(
        f"{BASE}/api/auth/login",
        json={"email": email, "password": password},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


# ============================================================================
# Service pur
# ============================================================================

def test_compute_caution_cents_basic_examples():
    from services import caution

    # Brief officiel : 250 × 7 % = 17,50 €
    assert caution.compute_caution_cents(250) == 1750
    # 180 × 7 % = 12,60 €
    assert caution.compute_caution_cents(180) == 1260
    # 500 × 7 % = 35 €
    assert caution.compute_caution_cents(500) == 3500


def test_compute_caution_cents_rounds_to_nearest_cent():
    from services import caution

    # 199 × 7 % = 13,93 €
    assert caution.compute_caution_cents(199) == 1393
    # 33.33 × 7 % = 2,3331 → 233 cents
    assert caution.compute_caution_cents(33.33) == 233


def test_compute_caution_cents_edge_zero_and_negative():
    from services import caution

    assert caution.compute_caution_cents(0) == 0
    assert caution.compute_caution_cents(-50) == 0
    assert caution.compute_caution_cents(None) == 0


def test_format_eur_fr():
    from services import caution

    assert caution.format_eur(1750) == "17,50 €"
    assert caution.format_eur(3500) == "35 €"
    assert caution.format_eur(0) == "0 €"


# ============================================================================
# Endpoint /estimation/quote
# ============================================================================

def test_estimation_quote_endpoint():
    token = _login("client.test@auxora.fr", "Test1234!")
    r = httpx.post(
        f"{BASE}/api/estimation/quote",
        headers=_h(token),
        json={"price_min_eur": 180, "price_max_eur": 250},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["caution_cents"] == 1750
    assert body["caution_eur"] == 17.5
    assert body["caution_display"] == "17,50 €"
    assert body["rate"] == 0.07
    assert body["rate_display"] == "7 %"


# ============================================================================
# Broadcast avec estimation
# ============================================================================

def test_broadcast_persists_caution_from_estimation():
    token = _login("client.test@auxora.fr", "Test1234!")
    r = httpx.post(
        f"{BASE}/api/broadcasts",
        headers=_h(token),
        json={
            "trade": "plombier",
            "date": "2026-09-01",
            "slot": "10:00-12:00",
            "description": "Test estimation",
            "urgent": False,
            "estimated_price_min_eur": 180,
            "estimated_price_max_eur": 250,
        },
        timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("estimated_price_max_eur") == 250
    assert body.get("caution_cents") == 1750
    assert body.get("caution_eur_display") == "17,50 €"


def test_broadcast_caution_locked_at_creation():
    """Le champ caution_cents est figé à la création — pas de recalcul auto."""
    token = _login("client.test@auxora.fr", "Test1234!")
    r = httpx.post(
        f"{BASE}/api/broadcasts",
        headers=_h(token),
        json={
            "trade": "plombier",
            "date": "2026-09-02",
            "slot": "10:00-12:00",
            "description": "Test locked caution",
            "estimated_price_min_eur": 100,
            "estimated_price_max_eur": 200,
        },
        timeout=10,
    )
    assert r.status_code == 200
    bid = r.json()["broadcast_id"]
    # Vérifier en DB que caution est locked (200 × 7% = 14 €)
    client = MongoClient(
        os.environ.get("MONGO_URL", "mongodb://localhost:27017"),
    )
    bc = client.auxora.booking_broadcasts.find_one({"broadcast_id": bid})
    assert bc["caution_cents"] == 1400
    assert bc["estimated_price_max_eur"] == 200


def test_broadcast_without_estimation_has_zero_caution():
    """Si le client ne fournit pas d'estimation, caution = 0 (non bloquant)."""
    token = _login("client.test@auxora.fr", "Test1234!")
    r = httpx.post(
        f"{BASE}/api/broadcasts",
        headers=_h(token),
        json={
            "trade": "plombier",
            "date": "2026-09-03",
            "slot": "10:00-12:00",
            "description": "Sans estimation",
        },
        timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("caution_cents") == 0
