"""Sprint 14 Phase 1 Bloc 2 — Smoke script covering the 11 explicit
verification points from the review_request (users router migration).

Runs live against http://localhost:8001 with the seeded test accounts.
This complements test_sprint14_p1_bloc2_users.py; it re-checks the exact
scenarios the reviewer requested so we can generate a clear pass/fail
table for the report.
"""
from __future__ import annotations
import os
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
def client_tok() -> str:
    return _login(CLIENT_EMAIL, CLIENT_PASSWORD)


@pytest.fixture(scope="module")
def artisan_tok() -> str:
    return _login(ARTISAN_EMAIL, ARTISAN_PASSWORD)


# 1. PATCH /api/users/me name update
def test_1_patch_me_name(client_tok):
    orig = httpx.get(f"{BASE}/api/auth/me", headers=_h(client_tok), timeout=5).json()
    r = httpx.patch(
        f"{BASE}/api/users/me", headers=_h(client_tok),
        json={"name": "NewName123"}, timeout=5,
    )
    assert r.status_code == 200
    assert r.json()["user"]["name"] == "NewName123"
    me = httpx.get(f"{BASE}/api/auth/me", headers=_h(client_tok), timeout=5).json()
    assert me["name"] == "NewName123"
    # restore
    httpx.patch(
        f"{BASE}/api/users/me", headers=_h(client_tok),
        json={"name": orig["name"]}, timeout=5,
    )


# 2. Privilege escalation must NOT succeed
def test_2_no_privilege_escalation(client_tok):
    r = httpx.patch(
        f"{BASE}/api/users/me", headers=_h(client_tok),
        json={"role": "super_admin", "password": "x", "name": "Legit"},
        timeout=5,
    )
    assert r.status_code == 200
    me = httpx.get(f"{BASE}/api/auth/me", headers=_h(client_tok), timeout=5).json()
    assert me["role"] == "client"
    # restore
    httpx.patch(
        f"{BASE}/api/users/me", headers=_h(client_tok),
        json={"name": "Client Test"}, timeout=5,
    )


# 3. XSS in phone → 422
def test_3_phone_sanitization(client_tok):
    r = httpx.patch(
        f"{BASE}/api/users/me", headers=_h(client_tok),
        json={"phone": "<script>alert(1)</script>"}, timeout=5,
    )
    assert r.status_code == 422


# 4. PATCH without auth → 401
def test_4_patch_requires_auth():
    r = httpx.patch(f"{BASE}/api/users/me", json={"name": "x"}, timeout=5)
    assert r.status_code == 401


# 5. GET notifications → 200 dict
def test_5_get_notifications(client_tok):
    r = httpx.get(f"{BASE}/api/users/me/notifications", headers=_h(client_tok), timeout=5)
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


# 6. POST notifications persistence
def test_6_notifications_persistence(client_tok):
    httpx.post(
        f"{BASE}/api/users/me/notifications", headers=_h(client_tok),
        json={"marketing": True, "sms_enabled": True}, timeout=5,
    )
    r = httpx.get(f"{BASE}/api/users/me/notifications", headers=_h(client_tok), timeout=5)
    body = r.json()
    assert body["marketing"] is True
    assert body["sms_enabled"] is True
    # cleanup
    httpx.post(
        f"{BASE}/api/users/me/notifications", headers=_h(client_tok),
        json={"marketing": False, "sms_enabled": False}, timeout=5,
    )


# 7. Create pm returns pm_id
def test_7_create_pm(client_tok):
    r = httpx.post(
        f"{BASE}/api/users/me/payment-methods", headers=_h(client_tok),
        json={"brand": "visa", "last4": "1234", "is_default": True}, timeout=5,
    )
    assert r.status_code == 200
    pm = r.json()
    assert pm["pm_id"].startswith("pm_")
    # cleanup
    httpx.delete(
        f"{BASE}/api/users/me/payment-methods/{pm['pm_id']}",
        headers=_h(client_tok), timeout=5,
    )


# 8. GET lists newly created pm
def test_8_list_pm(client_tok):
    r_create = httpx.post(
        f"{BASE}/api/users/me/payment-methods", headers=_h(client_tok),
        json={"brand": "visa", "last4": "4242"}, timeout=5,
    )
    assert r_create.status_code == 200
    pm_id = r_create.json()["pm_id"]
    r_list = httpx.get(
        f"{BASE}/api/users/me/payment-methods", headers=_h(client_tok), timeout=5,
    )
    assert r_list.status_code == 200
    ids = [m["pm_id"] for m in r_list.json()["methods"]]
    assert pm_id in ids
    httpx.delete(
        f"{BASE}/api/users/me/payment-methods/{pm_id}",
        headers=_h(client_tok), timeout=5,
    )


# 9. Brand normalization + last4 truncation
def test_9_normalization(client_tok):
    r = httpx.post(
        f"{BASE}/api/users/me/payment-methods", headers=_h(client_tok),
        json={"brand": "WEIRDBRAND", "last4": "12345678"}, timeout=5,
    )
    assert r.status_code == 200
    pm = r.json()
    assert pm["brand"] == "other"
    assert pm["last4"] == "5678"
    httpx.delete(
        f"{BASE}/api/users/me/payment-methods/{pm['pm_id']}",
        headers=_h(client_tok), timeout=5,
    )


# 10. CRITICAL: cross-user ownership → 404 (not 403)
def test_10_ownership_404(client_tok, artisan_tok):
    # Create pm as artisan
    r = httpx.post(
        f"{BASE}/api/users/me/payment-methods", headers=_h(artisan_tok),
        json={"brand": "mastercard", "last4": "9999"}, timeout=5,
    )
    assert r.status_code == 200
    foreign_pm = r.json()["pm_id"]

    # Client tries DELETE → 404
    r_del = httpx.delete(
        f"{BASE}/api/users/me/payment-methods/{foreign_pm}",
        headers=_h(client_tok), timeout=5,
    )
    assert r_del.status_code == 404, f"Expected 404, got {r_del.status_code}"

    # Client tries set-default → 404
    r_def = httpx.post(
        f"{BASE}/api/users/me/payment-methods/{foreign_pm}/default",
        headers=_h(client_tok), timeout=5,
    )
    assert r_def.status_code == 404, f"Expected 404, got {r_def.status_code}"

    # Cleanup — artisan can still delete its own
    r_own = httpx.delete(
        f"{BASE}/api/users/me/payment-methods/{foreign_pm}",
        headers=_h(artisan_tok), timeout=5,
    )
    assert r_own.status_code == 200


# 11. POST pm without auth → 401
def test_11_pm_requires_auth():
    r = httpx.post(
        f"{BASE}/api/users/me/payment-methods",
        json={"brand": "visa", "last4": "1234"}, timeout=5,
    )
    assert r.status_code == 401
