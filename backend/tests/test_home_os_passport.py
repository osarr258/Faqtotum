"""
Auxora — Home OS / Property Passport backend tests
=================================================
Covers the *new* additions on top of the existing MY HOME section:
  1. Enhanced PropertyInput fields (city, postal_code, rooms, dpe_grade, cover_color)
  2. Auto-generation of maintenance/warranty reminders when creating equipment
  3. GET /api/properties/{pid}/budget shape + values
  4. POST /api/properties/{pid}/share, GET /api/passport/{token} (PUBLIC), DELETE
Existing property CRUD endpoints are considered out of scope.
"""

import os
import re
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "http://localhost:8001"
BASE_URL = BASE_URL.rstrip("/")

CLIENT_EMAIL = "client.test@auxora.fr"
CLIENT_PASSWORD = "Test1234!"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def auth_headers(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": CLIENT_EMAIL, "password": CLIENT_PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    token = data.get("token") or data.get("session_token")
    assert token, f"No token in login response: {data}"
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def property_id(api, auth_headers):
    """Create the test property once, delete it at teardown."""
    payload = {
        "name": "TEST_Home_OS",
        "type": "house",
        "address": "1 rue test",
        "city": "Paris",
        "postal_code": "75011",
        "surface": 80,
        "year_built": 1990,
        "rooms": 4,
        "dpe_grade": "D",
        "cover_color": "#F59E0B",
    }
    r = api.post(f"{BASE_URL}/api/properties", headers=auth_headers, json=payload)
    assert r.status_code == 200, f"Create property failed: {r.status_code} {r.text}"
    prop = r.json()
    pid = prop.get("property_id")
    assert pid, f"No property_id in response: {prop}"
    # sanity: attach the initial payload for cross-tests
    yield pid
    # Teardown
    api.delete(f"{BASE_URL}/api/properties/{pid}", headers=auth_headers)


# ---------------------------------------------------------------------------
# 1) Enhanced PropertyInput — new fields stored & returned
# ---------------------------------------------------------------------------

class TestPropertyEnhancedFields:

    def test_create_property_returns_all_new_fields(self, api, auth_headers, property_id):
        # Reload from GET
        r = api.get(f"{BASE_URL}/api/properties/{property_id}", headers=auth_headers)
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["city"] == "Paris"
        assert p["postal_code"] == "75011"
        assert p["rooms"] == 4
        assert p["dpe_grade"] == "D"
        assert p["cover_color"] == "#F59E0B"
        assert p["type"] == "house"
        assert p["surface"] == 80
        assert p["year_built"] == 1990

    def test_patch_updates_rooms_and_dpe(self, api, auth_headers, property_id):
        r = api.patch(f"{BASE_URL}/api/properties/{property_id}",
                      headers=auth_headers, json={"rooms": 5, "dpe_grade": "C"})
        assert r.status_code == 200, r.text
        # Verify persisted via GET
        r2 = api.get(f"{BASE_URL}/api/properties/{property_id}", headers=auth_headers)
        assert r2.status_code == 200
        p = r2.json()
        assert p["rooms"] == 5
        assert p["dpe_grade"] == "C"
        # ensure other new fields remain intact
        assert p["cover_color"] == "#F59E0B"
        assert p["city"] == "Paris"


# ---------------------------------------------------------------------------
# 2) Equipment creation triggers auto-generation of reminders
# ---------------------------------------------------------------------------

class TestEquipmentAutoReminders:

    def test_create_equipment_returns_auto_reminders_counter(self, api, auth_headers, property_id, request):
        payload = {
            "name": "Chaudière test",
            "category": "boiler",
            "brand": "Frisquet",
            "installed_on": "2023-01-15",
            "warranty_until": "2027-01-15",
            "status": "ok",
        }
        r = api.post(f"{BASE_URL}/api/properties/{property_id}/equipment",
                     headers=auth_headers, json=payload)
        assert r.status_code == 200, r.text
        eq = r.json()
        assert eq.get("equipment_id"), f"Missing equipment_id: {eq}"
        assert "_auto_reminders_created" in eq, f"Missing _auto_reminders_created flag: {eq}"
        assert eq["_auto_reminders_created"] >= 1, \
            f"Expected >=1 auto reminders, got {eq['_auto_reminders_created']}"
        # stash for next test
        request.config.cache.set("equipment_id", eq["equipment_id"])
        request.config.cache.set("auto_reminders_count", eq["_auto_reminders_created"])

    def test_reminders_endpoint_lists_auto_generated_entries(self, api, auth_headers, property_id):
        r = api.get(f"{BASE_URL}/api/properties/{property_id}/reminders", headers=auth_headers)
        assert r.status_code == 200, r.text
        reminders = r.json()
        auto = [x for x in reminders if x.get("auto_generated")]
        assert len(auto) >= 1, f"No auto-generated reminders found. All={reminders}"
        types = {x.get("reminder_type") for x in auto}
        # Expect at least maintenance ('entretien'); warranty ('garantie') only present
        # if warranty_until - 30 days is in the future (test uses 2027 → should be present).
        assert "entretien" in types, f"Missing 'entretien' auto-reminder. types={types}"
        assert "garantie" in types, f"Missing 'garantie' auto-reminder. types={types}"


# ---------------------------------------------------------------------------
# 3) Share / public passport
# ---------------------------------------------------------------------------

_SHARE_TOKEN = {"value": None}


class TestPropertyPassportShare:

    def test_enable_share_returns_token_and_url(self, api, auth_headers, property_id):
        r = api.post(f"{BASE_URL}/api/properties/{property_id}/share", headers=auth_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        token = data.get("token")
        url = data.get("url")
        assert token and re.fullmatch(r"[0-9a-f]+", token), f"Token not hex: {token}"
        assert isinstance(url, str) and token in url, f"URL missing token: {url}"
        _SHARE_TOKEN["value"] = token

    def test_public_passport_no_auth_returns_property(self, api):
        token = _SHARE_TOKEN["value"]
        assert token, "Share token not captured from previous test"
        # Fresh session with NO auth headers
        anon = requests.Session()
        r = anon.get(f"{BASE_URL}/api/passport/{token}")
        assert r.status_code == 200, f"Public passport failed: {r.status_code} {r.text}"
        data = r.json()
        assert "property" in data and "equipments" in data and "events" in data, \
            f"Missing top-level keys: {data.keys()}"
        p = data["property"]
        # No sensitive fields
        assert "user_id" not in p, "property should not expose user_id"
        # New fields exposed
        assert p.get("city") == "Paris"
        assert p.get("postal_code") == "75011"
        assert p.get("cover_color") == "#F59E0B"
        # Equipments should not leak user_id / notes
        for eq in data["equipments"]:
            assert "user_id" not in eq, f"Equipment leaked user_id: {eq}"
            assert "notes" not in eq, f"Equipment leaked notes: {eq}"

    def test_disable_share_revokes_public_access(self, api, auth_headers, property_id):
        token = _SHARE_TOKEN["value"]
        assert token
        r = api.delete(f"{BASE_URL}/api/properties/{property_id}/share", headers=auth_headers)
        assert r.status_code == 200, r.text
        # Public should now 404
        anon = requests.Session()
        r2 = anon.get(f"{BASE_URL}/api/passport/{token}")
        assert r2.status_code == 404, f"Expected 404 after revoke, got {r2.status_code} {r2.text}"


# ---------------------------------------------------------------------------
# 4) Budget endpoint
# ---------------------------------------------------------------------------

class TestPropertyBudget:

    def test_budget_shape(self, api, auth_headers, property_id):
        r = api.get(f"{BASE_URL}/api/properties/{property_id}/budget", headers=auth_headers)
        assert r.status_code == 200, r.text
        b = r.json()
        for key in ["total_cents", "events_count", "by_month", "by_type", "top_artisans"]:
            assert key in b, f"Missing key '{key}' in budget response: {b}"
        assert isinstance(b["total_cents"], int)
        assert isinstance(b["events_count"], int)
        assert isinstance(b["by_month"], list)
        assert isinstance(b["by_type"], list)
        assert isinstance(b["top_artisans"], list)

    def test_post_event_endpoint_exists(self, api, auth_headers, property_id):
        """
        The review request specifies POST /api/properties/{pid}/events with cost_cents
        and expects it to affect the budget aggregation. Verify the endpoint exists.
        """
        payload = {
            "event_type": "entretien",
            "title": "Test",
            "cost_cents": 15000,
            "event_date": "2026-01-15",
            "artisan_name": "Karim B.",
        }
        r = api.post(f"{BASE_URL}/api/properties/{property_id}/events",
                     headers=auth_headers, json=payload)
        # Fail explicitly if endpoint is missing (this is the whole point of the test).
        assert r.status_code in (200, 201), \
            f"POST /properties/{{pid}}/events unavailable or failed: {r.status_code} {r.text}"

    def test_budget_reflects_new_event(self, api, auth_headers, property_id):
        r = api.get(f"{BASE_URL}/api/properties/{property_id}/budget", headers=auth_headers)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["total_cents"] >= 15000, f"Expected total_cents >= 15000, got {b['total_cents']}"
        top_names = [x.get("name") for x in b.get("top_artisans", [])]
        assert "Karim B." in top_names, f"Karim B. not in top_artisans: {top_names}"
