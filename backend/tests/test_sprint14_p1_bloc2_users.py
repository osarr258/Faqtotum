"""Sprint 14 Phase 1 Bloc 2 — Users router non-regression tests.

Covers:
- PATCH /users/me happy path + input sanitization
- Notifications get/set roundtrip
- Payment methods: create, list, set default, delete
- **Ownership**: user A cannot delete or make-default user B's payment method
- **Enumeration guard**: 404 (not 403) for foreign pm_id
"""
from __future__ import annotations
import os
import time
import httpx
import pytest


BASE = os.environ.get("AUXORA_TEST_URL", "http://localhost:8001")
CLIENT_EMAIL = "client.test@auxora.fr"
CLIENT_PASSWORD = "Test1234!"
ARTISAN_EMAIL = "pro.test@auxora.fr"
ARTISAN_PASSWORD = "Test1234!"


def _login(email: str, password: str) -> str:
    r = httpx.post(
        f"{BASE}/api/auth/login",
        json={"email": email, "password": password},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def client_token() -> str:
    return _login(CLIENT_EMAIL, CLIENT_PASSWORD)


@pytest.fixture(scope="module")
def artisan_token() -> str:
    return _login(ARTISAN_EMAIL, ARTISAN_PASSWORD)


# ---------- PATCH /users/me ----------

def test_patch_me_updates_name(client_token: str):
    orig = httpx.get(f"{BASE}/api/auth/me", headers=_h(client_token), timeout=5).json()
    new_name = f"Client Test {int(time.time()) % 1000}"
    r = httpx.patch(
        f"{BASE}/api/users/me",
        headers=_h(client_token),
        json={"name": new_name},
        timeout=5,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["user"]["name"] == new_name
    assert "password" not in body["user"]
    # restore
    httpx.patch(
        f"{BASE}/api/users/me",
        headers=_h(client_token),
        json={"name": orig["name"]},
        timeout=5,
    )


def test_patch_me_rejects_invalid_phone(client_token: str):
    r = httpx.patch(
        f"{BASE}/api/users/me",
        headers=_h(client_token),
        json={"phone": "abc<script>alert(1)</script>"},
        timeout=5,
    )
    assert r.status_code == 422


def test_patch_me_ignores_unknown_fields(client_token: str):
    """Should silently drop fields not in the whitelist (e.g. role, password)."""
    r = httpx.patch(
        f"{BASE}/api/users/me",
        headers=_h(client_token),
        json={"role": "super_admin", "password": "x", "name": "Legit"},
        timeout=5,
    )
    assert r.status_code == 200
    me = httpx.get(f"{BASE}/api/auth/me", headers=_h(client_token), timeout=5).json()
    assert me["role"] == "client"  # NOT elevated
    # restore
    httpx.patch(
        f"{BASE}/api/users/me",
        headers=_h(client_token),
        json={"name": "Client Test"},
        timeout=5,
    )


def test_patch_me_requires_auth():
    r = httpx.patch(f"{BASE}/api/users/me", json={"name": "x"}, timeout=5)
    assert r.status_code == 401


# ---------- Notifications preferences ----------

def test_notif_prefs_defaults(client_token: str):
    """After the fixture reset, GET should either return defaults or
    an existing doc — both must expose at least the mandatory fields.
    We tolerate either shape (defaults vs. stored) to be order-independent.
    """
    r = httpx.get(f"{BASE}/api/users/me/notifications", headers=_h(client_token), timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)
    assert body.get("user_id"), "user_id must always be present"
    # At least one preference key must be present (defaults or persisted)
    known_keys = {"push_enabled", "email_enabled", "sms_enabled", "marketing",
                  "intervention_updates", "new_bookings"}
    assert known_keys.intersection(body.keys()), \
        f"expected at least one pref key, got {list(body.keys())}"


def test_notif_prefs_roundtrip(client_token: str):
    r = httpx.post(
        f"{BASE}/api/users/me/notifications",
        headers=_h(client_token),
        json={"marketing": True, "sms_enabled": True},
        timeout=5,
    )
    assert r.status_code == 200
    r2 = httpx.get(f"{BASE}/api/users/me/notifications", headers=_h(client_token), timeout=5)
    assert r2.status_code == 200
    body = r2.json()
    assert body["marketing"] is True
    assert body["sms_enabled"] is True
    # reset
    httpx.post(
        f"{BASE}/api/users/me/notifications",
        headers=_h(client_token),
        json={"marketing": False, "sms_enabled": False},
        timeout=5,
    )


# ---------- Payment methods ----------

def test_pm_create_list_delete(client_token: str):
    # Create
    r = httpx.post(
        f"{BASE}/api/users/me/payment-methods",
        headers=_h(client_token),
        json={"brand": "visa", "last4": "1234", "exp_month": 12, "exp_year": 2030, "is_default": True},
        timeout=5,
    )
    assert r.status_code == 200
    pm = r.json()
    assert pm["last4"] == "1234"
    assert pm["is_default"] is True
    pm_id = pm["pm_id"]

    # List
    r2 = httpx.get(f"{BASE}/api/users/me/payment-methods", headers=_h(client_token), timeout=5)
    assert r2.status_code == 200
    ids = [m["pm_id"] for m in r2.json()["methods"]]
    assert pm_id in ids

    # Delete
    r3 = httpx.delete(f"{BASE}/api/users/me/payment-methods/{pm_id}", headers=_h(client_token), timeout=5)
    assert r3.status_code == 200


def test_pm_delete_foreign_returns_404(client_token: str, artisan_token: str):
    """Client cannot delete an artisan's payment method by guessing pm_id."""
    # Create a payment method as artisan
    r = httpx.post(
        f"{BASE}/api/users/me/payment-methods",
        headers=_h(artisan_token),
        json={"brand": "mastercard", "last4": "9999"},
        timeout=5,
    )
    assert r.status_code == 200
    foreign_pm_id = r.json()["pm_id"]

    # Client tries to delete it
    r_delete = httpx.delete(
        f"{BASE}/api/users/me/payment-methods/{foreign_pm_id}",
        headers=_h(client_token),
        timeout=5,
    )
    # MUST be 404 (not 403) to prevent enumeration of foreign resource IDs
    assert r_delete.status_code == 404

    # Client tries to mark it as default
    r_default = httpx.post(
        f"{BASE}/api/users/me/payment-methods/{foreign_pm_id}/default",
        headers=_h(client_token),
        timeout=5,
    )
    assert r_default.status_code == 404

    # Cleanup — artisan deletes its own pm
    httpx.delete(
        f"{BASE}/api/users/me/payment-methods/{foreign_pm_id}",
        headers=_h(artisan_token),
        timeout=5,
    )


def test_pm_last4_truncated_server_side(client_token: str):
    """Even if user sends 16 digits, server must store only last 4."""
    r = httpx.post(
        f"{BASE}/api/users/me/payment-methods",
        headers=_h(client_token),
        json={"brand": "visa", "last4": "12345678"},
        timeout=5,
    )
    # last4 is Field(max_length=8) so 8 chars accepted but truncated to last 4
    assert r.status_code == 200
    pm = r.json()
    assert pm["last4"] == "5678"
    httpx.delete(
        f"{BASE}/api/users/me/payment-methods/{pm['pm_id']}",
        headers=_h(client_token),
        timeout=5,
    )


def test_pm_unknown_brand_defaults_to_other(client_token: str):
    r = httpx.post(
        f"{BASE}/api/users/me/payment-methods",
        headers=_h(client_token),
        json={"brand": "some_weird_brand_XYZ", "last4": "1111"},
        timeout=5,
    )
    assert r.status_code == 200
    pm = r.json()
    assert pm["brand"] == "other"
    httpx.delete(
        f"{BASE}/api/users/me/payment-methods/{pm['pm_id']}",
        headers=_h(client_token),
        timeout=5,
    )


def test_pm_requires_auth():
    r = httpx.get(f"{BASE}/api/users/me/payment-methods", timeout=5)
    assert r.status_code == 401
    r2 = httpx.post(f"{BASE}/api/users/me/payment-methods", json={"brand": "visa", "last4": "1234"}, timeout=5)
    assert r2.status_code == 401
