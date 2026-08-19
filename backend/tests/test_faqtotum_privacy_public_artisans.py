"""Tests FAQTOTUM V1 — Audit privacy sur endpoints publics artisans.

Vérifie que `GET /api/artisans`, `GET /api/artisans/{id}`, `GET /api/artisans/top`
et `GET /api/artisans/nearby` ne fuitent JAMAIS de données privées (téléphone,
email, iban, siret, position GPS précise, docs d'identité).
"""
from __future__ import annotations

import os

import httpx

BASE = os.environ.get("BASE_URL", "http://localhost:8001")

# Champs strictement interdits dans TOUT payload public.
FORBIDDEN = {
    "phone", "email", "stripe_account_id", "iban", "siret",
    "identity_docs", "insurance_docs", "password", "password_hash",
    "kbis", "verification_docs",
}

# Champs de position précise interdits sur endpoints publics NON-nearby.
FORBIDDEN_POSITION = {"lat", "lng", "live_lat", "live_lng"}


def _assert_no_leak(payload: dict, allow_position: bool = False):
    keys = set(payload.keys())
    leak = keys & FORBIDDEN
    assert not leak, f"Fuite privé : {leak} dans {sorted(keys)}"
    if not allow_position:
        pos_leak = keys & FORBIDDEN_POSITION
        assert not pos_leak, f"Fuite position : {pos_leak}"


def test_get_artisan_public_strips_private():
    """`GET /api/artisans/{id}` (public) ne doit exposer NI téléphone NI position précise."""
    # Utilise l'artisan de référence du seed.
    r = httpx.get(f"{BASE}/api/artisans/art_5c533c263d23", timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    _assert_no_leak(body)


def test_list_artisans_public_strips_private():
    r = httpx.get(f"{BASE}/api/artisans", timeout=10)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    if items:
        for a in items[:20]:
            _assert_no_leak(a)


def test_top_artisans_public_strips_private():
    r = httpx.get(f"{BASE}/api/artisans/top", timeout=10)
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    if items:
        for a in items:
            _assert_no_leak(a)


def test_nearby_artisans_public_strips_sensitive_but_keeps_position():
    """Nearby autorise `current_lat`/`current_lng` (pour la carte) mais bannit
    phone/email/stripe/iban/siret."""
    r = httpx.get(
        f"{BASE}/api/artisans/nearby",
        params={"lat": 48.858, "lng": 2.349, "radius": 50, "limit": 10},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "artisans" in body
    for a in body["artisans"][:10]:
        # Phone / email / stripe / iban / siret : jamais.
        forbidden_here = FORBIDDEN & set(a.keys())
        assert not forbidden_here, f"Nearby leak: {forbidden_here}"


def test_public_profile_contains_expected_fields():
    """Vérifie que les champs UTILES restent bien exposés."""
    r = httpx.get(f"{BASE}/api/artisans/art_5c533c263d23", timeout=10)
    assert r.status_code == 200
    body = r.json()
    for k in ("artisan_id", "name", "trade", "rating", "trade_name"):
        assert k in body, f"Champ manquant : {k}"


def test_public_profile_hides_precise_city_address():
    """La `city` publique ne doit pas contenir d'adresse complète (rue+cp).
    Le formatage : `_public_view` garde seulement ce qui précède la première virgule."""
    r = httpx.get(f"{BASE}/api/artisans/art_5c533c263d23", timeout=10)
    body = r.json()
    city = body.get("city", "")
    # pas de virgule (donc pas "Paris, 75011")
    assert "," not in city
