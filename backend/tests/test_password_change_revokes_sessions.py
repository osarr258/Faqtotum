"""
V1 hardening — session revocation on password change.

Verifies that when a user changes their password:
- The caller's OWN session remains valid (no forced logout after success).
- ALL OTHER active sessions for that user are revoked immediately, so any
  stolen/leaked bearer token stops working.

Uses a dedicated test user (created & torn down inside the test) so the
existing pre-seeded credentials in test_credentials.md stay untouched.
"""
import os
import uuid

import pymongo
import pytest
import requests

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://reviens-app.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "auxora")


@pytest.fixture()
def ephemeral_user():
    """Register a throw-away user; delete it at teardown."""
    email = f"revoke-{uuid.uuid4().hex[:10]}@faqtotum.fr"
    pw = "InitialPass123!"
    r = requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": pw, "name": "Revoke Test", "role": "client"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    yield email, pw
    sync = pymongo.MongoClient(MONGO_URL)
    try:
        db = sync[DB_NAME]
        u = db.users.find_one({"email": email}, {"user_id": 1})
        if u:
            db.users.delete_one({"user_id": u["user_id"]})
            db.user_sessions.delete_many({"user_id": u["user_id"]})
    finally:
        sync.close()


def _login(email: str, password: str) -> str:
    r = requests.post(
        f"{API}/auth/login",
        json={"email": email, "password": password},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _me(token: str) -> requests.Response:
    return requests.get(
        f"{API}/auth/me",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )


def test_password_change_revokes_other_sessions(ephemeral_user):
    email, pw = ephemeral_user
    # Open TWO independent sessions for the same user.
    token_a = _login(email, pw)  # will be "caller" during password change
    token_b = _login(email, pw)  # simulates another device / stolen token

    # Both work initially.
    assert _me(token_a).status_code == 200
    assert _me(token_b).status_code == 200

    # A changes the password.
    new_pw = "BrandNewPass456!"
    r = requests.post(
        f"{API}/security/password/change",
        json={"current_password": pw, "new_password": new_pw},
        headers={"Authorization": f"Bearer {token_a}"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    # At least one OTHER session must have been revoked (B's).
    assert body["other_sessions_revoked"] >= 1

    # The caller's own session (A) is still valid.
    assert _me(token_a).status_code == 200
    # The other session (B) is now invalid → 401.
    r_b = _me(token_b)
    assert r_b.status_code == 401


def test_password_change_wrong_current_does_not_revoke(ephemeral_user):
    """Failed password change must NOT log anyone out."""
    email, pw = ephemeral_user
    token_a = _login(email, pw)
    token_b = _login(email, pw)

    r = requests.post(
        f"{API}/security/password/change",
        json={"current_password": "wrong-pw", "new_password": "NewPass123456!"},
        headers={"Authorization": f"Bearer {token_a}"},
        timeout=15,
    )
    assert r.status_code == 401  # rejected

    # Both sessions still valid.
    assert _me(token_a).status_code == 200
    assert _me(token_b).status_code == 200


def test_password_change_reports_revoked_count(ephemeral_user):
    """The response must always expose an integer `other_sessions_revoked` field."""
    email, pw = ephemeral_user
    # Wipe any session leftover from register so we control the exact count.
    sync = pymongo.MongoClient(MONGO_URL)
    try:
        u = sync[DB_NAME].users.find_one({"email": email}, {"user_id": 1})
        sync[DB_NAME].user_sessions.delete_many({"user_id": u["user_id"]})
    finally:
        sync.close()

    token = _login(email, pw)
    r = requests.post(
        f"{API}/security/password/change",
        json={"current_password": pw, "new_password": "SoloUserNew789!"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["other_sessions_revoked"], int)
    assert body["other_sessions_revoked"] == 0  # only the caller's own session existed
    assert _me(token).status_code == 200
