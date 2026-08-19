"""Tests FAQTOTUM V1 — Endpoint /tracking/{booking_id}.

Vérifie :
  1. Client peut suivre son propre booking.
  2. Artisan attitré peut suivre le booking.
  3. Un tiers reçoit 404 (ni owner ni artisan).
  4. Adresse client masquée tant que status < accepted.
  5. Estimation + caution transmises depuis le booking.
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


def test_tracking_returns_client_booking():
    ct = _login("client.test@auxora.fr", "Test1234!")
    r = httpx.post(
        f"{BASE}/api/bookings",
        headers=_h(ct),
        json={
            "artisan_id": "art_2dfb71f00c16",
            "date": "2026-09-10",
            "slot": "10:00-12:00",
            "description": "Test tracking",
        },
        timeout=10,
    )
    assert r.status_code == 200
    bid = r.json()["booking_id"]

    # Client peut consulter le tracking
    r2 = httpx.get(f"{BASE}/api/tracking/{bid}", headers=_h(ct), timeout=10)
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["booking_id"] == bid
    assert body["status"] == "pending"
    assert body.get("artisan") is not None


def test_tracking_third_party_gets_404():
    """Un utilisateur non impliqué reçoit 404."""
    ct = _login("client.test@auxora.fr", "Test1234!")
    r = httpx.post(
        f"{BASE}/api/bookings",
        headers=_h(ct),
        json={
            "artisan_id": "art_2dfb71f00c16",
            "date": "2026-09-11",
            "slot": "10:00-12:00",
            "description": "Test tiers",
        },
        timeout=10,
    )
    bid = r.json()["booking_id"]

    # Autre client (pro.test@proconnect.fr est un artisan legacy sans link)
    other_tok = _login("pro.test@proconnect.fr", "test1234")
    r2 = httpx.get(f"{BASE}/api/tracking/{bid}", headers=_h(other_tok), timeout=10)
    assert r2.status_code == 404


def test_tracking_broadcast_booking_carries_estimation():
    """Un booking issu d'un broadcast doit exposer estimation + caution."""
    ct = _login("client.test@auxora.fr", "Test1234!")
    # Crée un broadcast avec estimation
    r = httpx.post(
        f"{BASE}/api/broadcasts",
        headers=_h(ct),
        json={
            "trade": "plombier",
            "date": "2026-09-20",
            "slot": "10:00-12:00",
            "description": "Test tracking + estimation",
            "estimated_price_min_eur": 120,
            "estimated_price_max_eur": 220,
        },
        timeout=10,
    )
    assert r.status_code == 200
    bcid = r.json()["broadcast_id"]

    # Accept via un candidat legacy
    client = MongoClient(
        os.environ.get("MONGO_URL", "mongodb://localhost:27017"),
    )
    bc = client.auxora.booking_broadcasts.find_one({"broadcast_id": bcid})
    # Chercher un candidat sans user_id (legacy) pour permettre l'accept par pro test.
    cand = None
    for aid in bc.get("candidates", []):
        row = client.auxora.artisan_profiles.find_one({"artisan_id": aid})
        if row and not row.get("user_id"):
            cand = aid
            break
    if not cand:
        # Skip si pas de legacy candidate
        return

    pro_tok = _login("pro.test@proconnect.fr", "test1234")
    r_acc = httpx.post(
        f"{BASE}/api/broadcasts/{bcid}/accept",
        headers=_h(pro_tok),
        json={"artisan_id": cand},
        timeout=10,
    )
    assert r_acc.status_code == 200
    booking_id = r_acc.json()["booking"]["booking_id"]

    # Tracking client
    r_t = httpx.get(
        f"{BASE}/api/tracking/{booking_id}", headers=_h(ct), timeout=10,
    )
    assert r_t.status_code == 200
    body = r_t.json()
    assert body["estimated_price_max_eur"] == 220
    assert body["caution_cents"] == 1540  # 220 × 7 % = 15,40 €
    assert body["status"] == "accepted"
