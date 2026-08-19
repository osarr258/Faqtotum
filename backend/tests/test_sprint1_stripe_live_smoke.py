"""
Sprint 1 brique 1 — Stripe live-mode HTTP smoke tests.

Guarantees that after switching MOCK_MODE off (real sk_test_ keys in .env),
the Stripe-facing endpoints:
  1. Do NOT return 500 (would indicate a code path still assuming mock IDs
     or an unhandled Stripe exception).
  2. Return sensible auth/validation codes (401 / 400 / 404) instead.

Also asserts:
  - /api/ returns "Faqtotum API".
  - /api/auth/apple with a bogus but structurally valid token returns 401 (JWKS
     path exercised), not 500.
"""
from __future__ import annotations
import os
import requests
import pytest

BASE_URL = "https://reviens-app.preview.emergentagent.com"

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
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("token") or data.get("session_token") or data.get("access_token")
    assert tok, f"no token in login response: {data}"
    return tok


# ---------------------------------------------------------------------------
# Basic reachability
# ---------------------------------------------------------------------------

def test_root_returns_faqtotum_api():
    r = requests.get(f"{BASE_URL}/api/", timeout=10)
    assert r.status_code == 200
    assert r.json().get("message") == "Faqtotum API"


# ---------------------------------------------------------------------------
# Auth methods still work
# ---------------------------------------------------------------------------

def test_email_login_client():
    tok = _login(CLIENT_EMAIL, CLIENT_PASSWORD)
    assert isinstance(tok, str) and len(tok) > 10


def test_email_login_artisan():
    tok = _login(ARTISAN_EMAIL, ARTISAN_PASSWORD)
    assert isinstance(tok, str) and len(tok) > 10


def test_apple_bogus_token_returns_401_not_500():
    """Apple endpoint must exercise JWKS rejection path (401), never 500."""
    # >= 32 chars so we clear the Pydantic min_length gate and actually reach
    # the JWKS verification code.
    fake = "a" * 64
    r = requests.post(
        f"{BASE_URL}/api/auth/apple",
        json={"identity_token": fake},
        timeout=15,
    )
    assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"


def test_google_bogus_token_returns_4xx_not_500():
    r = requests.post(
        f"{BASE_URL}/api/auth/google",
        json={"session_token": "definitely-not-a-real-google-session-token"},
        timeout=15,
    )
    assert 400 <= r.status_code < 500, f"expected 4xx, got {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# Stripe endpoints must not 500 in live mode
# ---------------------------------------------------------------------------

def test_connect_status_artisan_no_500():
    """Artisan → /api/connect/status must return 2xx/4xx, never 500.

    An artisan that has never onboarded returns a stubby status; one who has
    hits Stripe for the real account state.
    """
    tok = _login(ARTISAN_EMAIL, ARTISAN_PASSWORD)
    r = requests.get(
        f"{BASE_URL}/api/connect/status",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=20,
    )
    assert r.status_code != 500, f"500 from connect/status: {r.text}"
    assert r.status_code in (200, 400, 401, 403, 404), (
        f"unexpected status {r.status_code}: {r.text}"
    )


def test_connect_status_client_forbidden_no_500():
    """A client hitting /connect/status should NOT trigger a 500."""
    tok = _login(CLIENT_EMAIL, CLIENT_PASSWORD)
    r = requests.get(
        f"{BASE_URL}/api/connect/status",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    assert r.status_code != 500, f"500 from connect/status as client: {r.text}"


def test_payments_create_intent_client_no_500():
    """Client hitting /api/payments/create-intent must not 500 (may 400/404 on
    missing target booking, that's OK)."""
    tok = _login(CLIENT_EMAIL, CLIENT_PASSWORD)
    r = requests.post(
        f"{BASE_URL}/api/payments/create-intent",
        headers={"Authorization": f"Bearer {tok}"},
        json={"booking_id": "bkg_does_not_exist", "amount_cents": 1000, "currency": "eur"},
        timeout=20,
    )
    assert r.status_code != 500, f"500 from create-intent: {r.text}"


def test_escrows_mine_client_no_500():
    tok = _login(CLIENT_EMAIL, CLIENT_PASSWORD)
    r = requests.get(
        f"{BASE_URL}/api/escrows/mine",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    assert r.status_code != 500, f"500 from escrows/mine: {r.text}"


def test_payment_summary_missing_intervention_no_500():
    tok = _login(CLIENT_EMAIL, CLIENT_PASSWORD)
    r = requests.get(
        f"{BASE_URL}/api/interventions/does_not_exist/payment-summary",
        headers={"Authorization": f"Bearer {tok}"},
        timeout=15,
    )
    # Expect 404/400 — not 500.
    assert r.status_code != 500, f"500 from payment-summary: {r.text}"
    assert r.status_code in (400, 401, 403, 404), (
        f"unexpected status {r.status_code}: {r.text}"
    )
