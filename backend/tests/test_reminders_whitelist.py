"""
V1 hardening — /properties/{pid}/reminders whitelist test.

Verifies that `PATCH /properties/{pid}/reminders/{rid}` REJECTS any field
that is not in the explicit allow-list, preventing mass-assignment attacks
where a malicious client could try to overwrite `user_id`, `property_id`,
`reminder_id`, `created_at`, or inject arbitrary fields.
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://reviens-app.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

CLIENT_EMAIL = "client.test@auxora.fr"
CLIENT_PASSWORD = "Test1234!"


@pytest.fixture(scope="module")
def headers():
    r = requests.post(
        f"{API}/auth/login",
        json={"email": CLIENT_EMAIL, "password": CLIENT_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def property_and_reminder(headers):
    # Create a property to hang the reminder on.
    r = requests.post(
        f"{API}/properties",
        json={"name": f"WLProp-{uuid.uuid4().hex[:6]}", "kind": "home"},
        headers=headers,
        timeout=15,
    )
    assert r.status_code == 200, r.text
    pid = r.json()["property_id"]

    r = requests.post(
        f"{API}/properties/{pid}/reminders",
        json={"title": "Vérifier chaudière", "due_on": "2027-01-15"},
        headers=headers,
        timeout=15,
    )
    assert r.status_code == 200, r.text
    rid = r.json()["reminder_id"]

    yield pid, rid

    requests.delete(f"{API}/properties/{pid}/reminders/{rid}", headers=headers, timeout=10)
    requests.delete(f"{API}/properties/{pid}", headers=headers, timeout=10)


# ---------- Positive cases ----------

def test_patch_reminder_valid_field_accepted(headers, property_and_reminder):
    pid, rid = property_and_reminder
    r = requests.patch(
        f"{API}/properties/{pid}/reminders/{rid}",
        json={"notes": "commentaire mis à jour"},
        headers=headers, timeout=10,
    )
    assert r.status_code == 200
    assert r.json()["notes"] == "commentaire mis à jour"


def test_patch_reminder_valid_status_accepted(headers, property_and_reminder):
    pid, rid = property_and_reminder
    r = requests.patch(
        f"{API}/properties/{pid}/reminders/{rid}",
        json={"status": "done"},
        headers=headers, timeout=10,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "done"


# ---------- Whitelist enforcement ----------

def test_patch_reminder_rejects_reminder_id_override(headers, property_and_reminder):
    """Attacker cannot rewrite the reminder_id via mass-assignment."""
    pid, rid = property_and_reminder
    r = requests.patch(
        f"{API}/properties/{pid}/reminders/{rid}",
        json={"reminder_id": "rem_pwned"},
        headers=headers, timeout=10,
    )
    assert r.status_code == 422  # Pydantic extra="forbid"


def test_patch_reminder_rejects_user_id_override(headers, property_and_reminder):
    """Attacker cannot rewrite the owning user via mass-assignment."""
    pid, rid = property_and_reminder
    r = requests.patch(
        f"{API}/properties/{pid}/reminders/{rid}",
        json={"user_id": "user_pwned"},
        headers=headers, timeout=10,
    )
    assert r.status_code == 422


def test_patch_reminder_rejects_property_id_override(headers, property_and_reminder):
    """Attacker cannot move a reminder to another property."""
    pid, rid = property_and_reminder
    r = requests.patch(
        f"{API}/properties/{pid}/reminders/{rid}",
        json={"property_id": "prop_pwned"},
        headers=headers, timeout=10,
    )
    assert r.status_code == 422


def test_patch_reminder_rejects_created_at_override(headers, property_and_reminder):
    """Attacker cannot rewrite immutable metadata."""
    pid, rid = property_and_reminder
    r = requests.patch(
        f"{API}/properties/{pid}/reminders/{rid}",
        json={"created_at": "1970-01-01T00:00:00Z"},
        headers=headers, timeout=10,
    )
    assert r.status_code == 422


def test_patch_reminder_rejects_arbitrary_field(headers, property_and_reminder):
    """Any unknown key must be rejected."""
    pid, rid = property_and_reminder
    r = requests.patch(
        f"{API}/properties/{pid}/reminders/{rid}",
        json={"malicious_flag": True, "note": "typo of notes"},
        headers=headers, timeout=10,
    )
    assert r.status_code == 422


def test_patch_reminder_rejects_invalid_status(headers, property_and_reminder):
    """Whitelist for `status` values still applies."""
    pid, rid = property_and_reminder
    r = requests.patch(
        f"{API}/properties/{pid}/reminders/{rid}",
        json={"status": "hacked_status"},
        headers=headers, timeout=10,
    )
    assert r.status_code == 400


def test_patch_reminder_empty_body_rejected(headers, property_and_reminder):
    """Empty PATCH is a bug on the client side — surface it with 400."""
    pid, rid = property_and_reminder
    r = requests.patch(
        f"{API}/properties/{pid}/reminders/{rid}",
        json={},
        headers=headers, timeout=10,
    )
    assert r.status_code == 400
