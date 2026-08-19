"""
Sprint 1 brique 1 — /api/connect/onboard regression tests.

Guarantees:
  - POST /api/connect/onboard NEVER returns 500 for an artisan.
  - If Stripe accepts (Accounts v1 enabled), returns 200 with onboarding_url.
  - If Stripe refuses (v1 deprecated / permission denied), returns 503 with
    detail.code == "STRIPE_CONNECT_UNAVAILABLE" — NOT a bare 500.
  - GET /api/connect/status stays 200 for the same artisan.
  - Client role hitting /connect/onboard → 403 (never 500).
"""
from __future__ import annotations
import os
import requests
import pytest

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL", "https://reviens-app.preview.emergentagent.com"
).rstrip("/")

CLIENT_EMAIL = "client.test@auxora.fr"
CLIENT_PASSWORD = "Test1234!"
ARTISAN_EMAIL = "pro.test@auxora.fr"
ARTISAN_PASSWORD = "Test1234!"


def _login(email: str, password: str) -> str:
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=15,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


# --- /api/connect/onboard ---------------------------------------------------

def test_connect_onboard_artisan_never_500():
    """Artisan onboard must NEVER return 500. Either 200 (Stripe accepts) or
    503 with structured STRIPE_CONNECT_UNAVAILABLE code."""
    tok = _login(ARTISAN_EMAIL, ARTISAN_PASSWORD)
    r = requests.post(
        f"{BASE_URL}/api/connect/onboard",
        headers={"Authorization": f"Bearer {tok}"},
        json={"country": "FR"},
        timeout=25,
    )
    assert r.status_code != 500, f"BARE 500 leaked from connect/onboard: {r.text}"
    assert r.status_code in (200, 503), f"unexpected status {r.status_code}: {r.text}"
    if r.status_code == 503:
        body = r.json()
        # FastAPI wraps detail in {"detail": ...}
        detail = body.get("detail")
        assert isinstance(detail, dict), f"detail should be structured dict: {body}"
        assert detail.get("code") == "STRIPE_CONNECT_UNAVAILABLE", (
            f"expected STRIPE_CONNECT_UNAVAILABLE code, got {detail}"
        )
        assert detail.get("message"), f"expected French message, got {detail}"
    else:
        # 200 branch — must have onboarding_url + stripe_account_id
        body = r.json()
        assert body.get("onboarding_url"), f"missing onboarding_url: {body}"
        assert body.get("stripe_account_id"), f"missing stripe_account_id: {body}"


def test_connect_onboard_client_forbidden_no_500():
    tok = _login(CLIENT_EMAIL, CLIENT_PASSWORD)
    r = requests.post(
        f"{BASE_URL}/api/connect/onboard",
        headers={"Authorization": f"Bearer {tok}"},
        json={"country": "FR"},
        timeout=15,
    )
    assert r.status_code != 500, f"500 from connect/onboard as client: {r.text}"
    assert r.status_code == 403


def test_connect_onboard_no_auth_returns_401():
    r = requests.post(
        f"{BASE_URL}/api/connect/onboard",
        json={"country": "FR"},
        timeout=10,
    )
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}: {r.text}"


# --- /api/connect/status still healthy (iteration 23 fix) -------------------

def test_connect_status_artisan_200():
    tok = _login(ARTISAN_EMAIL, ARTISAN_PASSWORD)
    r = requests.get(
        f"{BASE_URL}/api/connect/status",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=20,
    )
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
    body = r.json()
    assert "connected" in body
