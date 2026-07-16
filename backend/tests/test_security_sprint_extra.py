"""
Sprint 8 — Extra validation tests requested by main agent.
Focus on items not fully covered by test_security_sprint.py:
- Revoke a specific session by id
- Overview factors + recent_events
- Audit hash/prev_hash NOT exposed
- GDPR account soft-delete (anonymization)
- Distributed brute-force by IP across many emails
- Admin-only /security/audit/all forbidden for client
"""
import os
import uuid
import time

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://reviens-app.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


def _register(email, password="Real1234!", name="X"):
    return requests.post(f"{API}/auth/register", json={"email": email, "password": password, "name": name}, timeout=15)


def _login(email, password="Real1234!"):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


# ---- Sessions: delete a specific session ----
def test_delete_specific_session():
    email = f"delses_{uuid.uuid4().hex[:8]}@auxora-test.fr"
    _register(email)
    t1 = _login(email)   # session A
    t2 = _login(email)   # session B (current for this test)
    h2 = {"Authorization": f"Bearer {t2}"}
    r = requests.get(f"{API}/security/sessions", headers=h2, timeout=10)
    assert r.status_code == 200
    sessions = r.json()["sessions"]
    # find non-current
    target = next((s for s in sessions if not s["is_current"]), None)
    assert target is not None, "expected at least one non-current session"
    dr = requests.delete(f"{API}/security/sessions/{target['session_id']}", headers=h2, timeout=10)
    assert dr.status_code in (200, 204), dr.text
    # t1 (revoked) should now be 401
    r_fail = requests.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {t1}"}, timeout=10)
    assert r_fail.status_code == 401
    # t2 still works
    r_ok = requests.get(f"{API}/auth/me", headers=h2, timeout=10)
    assert r_ok.status_code == 200


# ---- Overview shape ----
def test_overview_full_shape():
    email = f"ovr_{uuid.uuid4().hex[:8]}@auxora-test.fr"
    _register(email)
    t = _login(email)
    h = {"Authorization": f"Bearer {t}"}
    r = requests.get(f"{API}/security/overview", headers=h, timeout=10)
    assert r.status_code == 200
    body = r.json()
    # security_score object
    ss = body["security_score"]
    assert 0 <= ss["score"] <= 100
    assert ss["level"] in ("faible", "moyen", "bon", "excellent")
    assert isinstance(ss.get("factors", []), list)
    assert isinstance(body["active_sessions"], int) and body["active_sessions"] >= 1
    assert "mfa" in body
    assert "recent_events" in body and isinstance(body["recent_events"], list)


# ---- Audit: no hash/prev_hash exposed to user ----
def test_audit_hides_hash_fields():
    email = f"aud_{uuid.uuid4().hex[:8]}@auxora-test.fr"
    _register(email)
    t = _login(email)
    h = {"Authorization": f"Bearer {t}"}
    r = requests.get(f"{API}/security/audit?limit=20", headers=h, timeout=10)
    assert r.status_code == 200
    logs = r.json()["logs"]
    assert len(logs) >= 1
    for log in logs:
        assert "hash" not in log
        assert "prev_hash" not in log
        assert "action" in log
    # register + login should appear
    actions = {log["action"] for log in logs}
    assert "auth.login" in actions


# ---- Admin-only audit/all forbidden for client ----
def test_audit_all_forbidden_for_client():
    t = _login("client.test@auxora.fr", "Test1234!")
    r = requests.get(f"{API}/security/audit/all", headers={"Authorization": f"Bearer {t}"}, timeout=10)
    assert r.status_code == 403


# ---- GDPR: full consents payload structure ----
def test_gdpr_consents_defaults():
    email = f"csn_{uuid.uuid4().hex[:8]}@auxora-test.fr"
    _register(email)
    t = _login(email)
    h = {"Authorization": f"Bearer {t}"}
    r = requests.get(f"{API}/security/gdpr/consents", headers=h, timeout=10)
    assert r.status_code == 200
    body = r.json()
    for k in ("marketing", "analytics", "third_party"):
        assert k in body


# ---- GDPR: account soft-delete anonymizes user & revokes sessions ----
def test_gdpr_account_soft_delete():
    email = f"del_{uuid.uuid4().hex[:8]}@auxora-test.fr"
    _register(email)
    t = _login(email)
    h = {"Authorization": f"Bearer {t}"}
    r = requests.delete(f"{API}/security/gdpr/account", headers=h, timeout=15)
    assert r.status_code in (200, 204), r.text
    # Token should be revoked
    r_me = requests.get(f"{API}/auth/me", headers=h, timeout=10)
    assert r_me.status_code == 401
    # Re-login should fail (email anonymized)
    r_login = requests.post(f"{API}/auth/login", json={"email": email, "password": "Real1234!"}, timeout=10)
    assert r_login.status_code in (401, 404, 400)


# ---- MFA status shape ----
def test_mfa_status_shape():
    email = f"mfa_{uuid.uuid4().hex[:8]}@auxora-test.fr"
    _register(email)
    t = _login(email)
    h = {"Authorization": f"Bearer {t}"}
    r = requests.get(f"{API}/security/mfa", headers=h, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "enabled" in body


# ---- Roles endpoint returns 9 roles ----
def test_roles_endpoint_returns_nine():
    t = _login("client.test@auxora.fr", "Test1234!")
    r = requests.get(f"{API}/security/roles", headers={"Authorization": f"Bearer {t}"}, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert len(body["roles"]) == 9, f"expected 9 roles, got {len(body['roles'])}"


# ---- Password change: success path then revert ----
def test_password_change_success_and_revert():
    email = f"pwd_{uuid.uuid4().hex[:8]}@auxora-test.fr"
    _register(email, password="Real1234!")
    t = _login(email, "Real1234!")
    h = {"Authorization": f"Bearer {t}"}
    r = requests.post(
        f"{API}/security/password/change",
        json={"current_password": "Real1234!", "new_password": "Brand5678!"},
        headers=h, timeout=10,
    )
    assert r.status_code == 200, r.text
    # Login with new password
    t2 = _login(email, "Brand5678!")
    assert t2


# ---- Distributed brute force by IP (30+ distinct emails) → 429 ----
def test_distributed_brute_force_by_ip():
    """Deterministic version: pre-seed 29 fake failed login_attempts for the
    expected client IP so that attempt #2 (30th total) triggers the distributed
    brute-force guard, regardless of whether k8s ingress forwards X-Forwarded-For.

    This still exercises the same rate-limit code path (`check_login_rate_limit`
    distinct-emails-per-IP branch) but removes flakiness caused by infrastructure
    header inconsistencies.
    """
    import os
    import pymongo
    from datetime import datetime, timezone, timedelta

    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "auxora")
    mongo_client = pymongo.MongoClient(mongo_url)
    db = mongo_client[db_name]

    # 1) Find which IP the backend will attribute to us by making ONE bad
    #    login and reading it back. This works whether we're going through
    #    the ingress (real IP) or direct-to-loopback (127.0.0.1).
    probe_email = f"probe_{uuid.uuid4().hex[:8]}@auxora-test.fr"
    requests.post(f"{API}/auth/login", json={"email": probe_email, "password": "Wrong123!"}, timeout=10)
    probe_doc = db.login_attempts.find_one({"email": probe_email})
    assert probe_doc, "login_attempts row not persisted — service down?"
    real_ip = probe_doc.get("ip", "unknown")

    # If we're on loopback the distributed check is disabled by design
    # (see services/security.py). Skip in that infrastructure case: the
    # per-email check still catches brute force via `test_login_rate_limit_5_fails`.
    if not real_ip or real_ip == "unknown" or real_ip.startswith("127.") or real_ip == "localhost":
        pytest.skip(f"distributed brute-force guard disabled for loopback IP {real_ip!r}")

    # 2) Pre-seed 29 fake failed attempts from that IP with distinct emails,
    #    inside the 15-minute sliding window.
    now = datetime.now(timezone.utc)
    seed_docs = [
        {
            "attempt_id": f"la_seed_{uuid.uuid4().hex[:10]}",
            "email": f"seed_{uuid.uuid4().hex[:6]}_{i}@auxora-test.fr",
            "ip": real_ip,
            "success": False,
            "user_id": None,
            "created_at": (now - timedelta(minutes=2)).isoformat(),
        }
        for i in range(29)
    ]
    db.login_attempts.insert_many(seed_docs)
    mongo_client.close()

    # 3) The very next failed login from a NEW email should hit 429.
    codes = []
    for i in range(5):
        e = f"trigger_{uuid.uuid4().hex[:6]}_{i}@auxora-test.fr"
        r = requests.post(f"{API}/auth/login", json={"email": e, "password": "Wrong123!"}, timeout=10)
        codes.append(r.status_code)
        if r.status_code == 429:
            break
    assert 429 in codes, f"expected 429 after pre-seeding 29 attempts, got {codes} (ip={real_ip})"
