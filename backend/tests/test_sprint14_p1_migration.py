"""Sprint 14 Phase 1 — Strangler migration non-regression tests.

Ensures the auth + security routers moved from server.py to routes/*.py behave
identically to the legacy inline implementation. Runs against a live backend
(assumes port 8001 and a seeded test client).
"""
from __future__ import annotations
import os
import httpx
import pytest


BASE = os.environ.get("AUXORA_TEST_URL", "http://localhost:8001")
CLIENT_EMAIL = "client.test@auxora.fr"
CLIENT_PASSWORD = "Test1234!"


@pytest.fixture(scope="module")
def token() -> str:
    r = httpx.post(
        f"{BASE}/api/auth/login",
        json={"email": CLIENT_EMAIL, "password": CLIENT_PASSWORD},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


# ---------- Auth router ----------

def test_root_ok():
    r = httpx.get(f"{BASE}/api/", timeout=5)
    assert r.status_code == 200
    assert "message" in r.json()


def test_login_wrong_password_401():
    r = httpx.post(
        f"{BASE}/api/auth/login",
        json={"email": CLIENT_EMAIL, "password": "nope"},
        timeout=10,
    )
    assert r.status_code == 401


def test_login_unknown_user_401():
    r = httpx.post(
        f"{BASE}/api/auth/login",
        json={"email": "does-not-exist@auxora.fr", "password": "whatever"},
        timeout=10,
    )
    assert r.status_code == 401


def test_auth_me_without_token_401():
    r = httpx.get(f"{BASE}/api/auth/me", timeout=5)
    assert r.status_code == 401


def test_auth_me_with_valid_token_200(token: str):
    r = httpx.get(f"{BASE}/api/auth/me", headers=_h(token), timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == CLIENT_EMAIL
    assert body["role"] == "client"
    # Sensitive data must not leak
    assert "password" not in body
    assert "_current_token" not in body


def test_auth_me_with_bad_token_401():
    r = httpx.get(f"{BASE}/api/auth/me", headers=_h("garbage_token"), timeout=5)
    assert r.status_code == 401


def test_logout_invalidates_session(token: str):
    r = httpx.post(f"{BASE}/api/auth/logout", headers=_h(token), timeout=5)
    assert r.status_code == 200
    # The same token must now fail
    r2 = httpx.get(f"{BASE}/api/auth/me", headers=_h(token), timeout=5)
    assert r2.status_code == 401


# ---------- Security router ----------

def test_security_overview_shape():
    tok = httpx.post(
        f"{BASE}/api/auth/login",
        json={"email": CLIENT_EMAIL, "password": CLIENT_PASSWORD},
        timeout=10,
    ).json()["token"]
    r = httpx.get(f"{BASE}/api/security/overview", headers=_h(tok), timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert "security_score" in body
    assert "active_sessions" in body
    assert "mfa" in body
    assert "recent_events" in body


def test_security_sessions_lists_own(token_scope=None):
    tok = httpx.post(
        f"{BASE}/api/auth/login",
        json={"email": CLIENT_EMAIL, "password": CLIENT_PASSWORD},
        timeout=10,
    ).json()["token"]
    r = httpx.get(f"{BASE}/api/security/sessions", headers=_h(tok), timeout=5)
    assert r.status_code == 200
    assert "sessions" in r.json()


def test_security_roles_shape():
    tok = httpx.post(
        f"{BASE}/api/auth/login",
        json={"email": CLIENT_EMAIL, "password": CLIENT_PASSWORD},
        timeout=10,
    ).json()["token"]
    r = httpx.get(f"{BASE}/api/security/roles", headers=_h(tok), timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert body["current_role"] == "client"
    assert isinstance(body["roles"], list)
    assert len(body["roles"]) >= 5  # at least the base roles catalog


def test_security_audit_lists_only_own_actor():
    tok = httpx.post(
        f"{BASE}/api/auth/login",
        json={"email": CLIENT_EMAIL, "password": CLIENT_PASSWORD},
        timeout=10,
    ).json()["token"]
    r = httpx.get(f"{BASE}/api/security/audit", headers=_h(tok), timeout=5)
    assert r.status_code == 200
    logs = r.json()["logs"]
    # Every returned log must be an action performed BY this user
    me = httpx.get(f"{BASE}/api/auth/me", headers=_h(tok), timeout=5).json()
    for log in logs:
        # `actor_id` may be null for auth.login_failed etc.
        if log.get("actor_id"):
            assert log["actor_id"] == me["user_id"]


def test_security_audit_all_requires_admin():
    tok = httpx.post(
        f"{BASE}/api/auth/login",
        json={"email": CLIENT_EMAIL, "password": CLIENT_PASSWORD},
        timeout=10,
    ).json()["token"]
    r = httpx.get(f"{BASE}/api/security/audit/all", headers=_h(tok), timeout=5)
    # Regular client must be forbidden
    assert r.status_code == 403
