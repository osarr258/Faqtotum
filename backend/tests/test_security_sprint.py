"""
Sprint 8 — Security, Privacy, Authentication tests.
Covers:
- Session tracking / listing / revoke
- Password change
- Audit log (hash chain)
- GDPR consents + export + soft-delete
- MFA architecture endpoints
- Rate limiting on login
- RBAC dependency
"""
import os
import uuid
import time

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://reviens-app.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CLIENT_EMAIL = "client.test@auxora.fr"
CLIENT_PASSWORD = "Test1234!"


def _login(email=CLIENT_EMAIL, password=CLIENT_PASSWORD):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def token():
    return _login()


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------- Sessions ----------

def test_sessions_listed(headers):
    r = requests.get(f"{API}/security/sessions", headers=headers, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "sessions" in body
    assert body["total"] >= 1
    s = body["sessions"][0]
    for k in ("session_id", "device", "browser", "ip", "created_at", "last_seen_at", "is_current"):
        assert k in s
    assert "session_token" not in s  # Must NOT expose full token


def test_security_overview(headers):
    r = requests.get(f"{API}/security/overview", headers=headers, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "security_score" in body
    assert body["security_score"]["score"] >= 0
    assert body["security_score"]["level"] in ("faible", "moyen", "bon", "excellent")
    assert isinstance(body["active_sessions"], int)


def test_revoke_others():
    # Create a dedicated user for isolation
    email = f"revoke_{uuid.uuid4().hex[:8]}@auxora-test.fr"
    requests.post(f"{API}/auth/register", json={"email": email, "password": "Real1234!", "name": "R"}, timeout=10)
    t1 = _login(email, "Real1234!")
    _ = _login(email, "Real1234!")
    t3 = _login(email, "Real1234!")
    h = {"Authorization": f"Bearer {t3}"}
    r = requests.post(f"{API}/security/sessions/revoke-others", headers=h, timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["revoked_count"] >= 2
    # t1 should now fail
    r_fail = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {t1}"}, timeout=10)
    assert r_fail.status_code == 401


# ---------- Audit Log ----------

def test_audit_log_records_login(headers):
    r = requests.get(f"{API}/security/audit?limit=20", headers=headers, timeout=10)
    assert r.status_code == 200, r.text
    logs = r.json()["logs"]
    actions = [log["action"] for log in logs]
    assert "auth.login" in actions


def test_audit_denies_others_verification():
    # regular client cannot call /audit/verify
    t = _login()
    r = requests.get(f"{API}/security/audit/verify", headers={"Authorization": f"Bearer {t}"}, timeout=10)
    assert r.status_code == 403


# ---------- GDPR ----------

def test_gdpr_consents_crud(headers):
    r = requests.post(
        f"{API}/security/gdpr/consents",
        json={"marketing": True, "analytics": False, "third_party": False},
        headers=headers, timeout=10,
    )
    assert r.status_code == 200
    assert r.json()["marketing"] is True

    r = requests.get(f"{API}/security/gdpr/consents", headers=headers, timeout=10)
    assert r.status_code == 200 and r.json()["marketing"] is True


def test_gdpr_export(headers):
    r = requests.get(f"{API}/security/gdpr/export", headers=headers, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"]
    assert "collections" in body
    assert "users" in body["collections"]


# ---------- MFA ----------

def test_mfa_flow(headers):
    r = requests.get(f"{API}/security/mfa", headers=headers, timeout=10)
    assert r.status_code == 200

    r = requests.post(f"{API}/security/mfa/prepare", json={"method": "totp"}, headers=headers, timeout=10)
    assert r.status_code == 200
    assert "secret" in r.json()
    assert "provisioning_uri" in r.json()

    # Bad code
    r_bad = requests.post(f"{API}/security/mfa/verify", json={"code": "999999"}, headers=headers, timeout=10)
    assert r_bad.status_code == 400

    # Demo code
    r_ok = requests.post(f"{API}/security/mfa/verify", json={"code": "000000"}, headers=headers, timeout=10)
    assert r_ok.status_code == 200 and r_ok.json()["enabled"] is True

    # Disable
    r_off = requests.delete(f"{API}/security/mfa", headers=headers, timeout=10)
    assert r_off.status_code == 200 and r_off.json()["enabled"] is False


# ---------- Password ----------

def test_password_change_wrong_current(headers):
    r = requests.post(
        f"{API}/security/password/change",
        json={"current_password": "WrongPass!", "new_password": "SomethingNew123!"},
        headers=headers, timeout=10,
    )
    assert r.status_code == 401


def test_password_change_short(headers):
    r = requests.post(
        f"{API}/security/password/change",
        json={"current_password": CLIENT_PASSWORD, "new_password": "short"},
        headers=headers, timeout=10,
    )
    assert r.status_code == 400


# ---------- RBAC ----------

def test_roles_endpoint(headers):
    r = requests.get(f"{API}/security/roles", headers=headers, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["current_role"] == "client"
    role_keys = {r["key"] for r in body["roles"]}
    assert {"client", "artisan", "admin", "super_admin"}.issubset(role_keys)


def test_admin_sessions_forbidden_for_client(headers):
    r = requests.get(f"{API}/security/admin/sessions", headers=headers, timeout=10)
    assert r.status_code == 403


# ---------- Rate limit / brute-force ----------

def test_brute_force_lockout():
    email = f"bf_{uuid.uuid4().hex[:8]}@auxora-test.fr"
    # Create a real user first
    requests.post(f"{API}/auth/register", json={"email": email, "password": "Real1234!", "name": "BF"}, timeout=10)
    # Now hammer with wrong password
    codes = []
    for _ in range(7):
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": "Wrong"}, timeout=10)
        codes.append(r.status_code)
    assert 429 in codes  # Should hit rate limit after ~5 attempts
