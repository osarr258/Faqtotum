"""
Tests for 'My Home' feature: /api/properties/** endpoints.
Covers CRUD for properties, equipment, documents, reminders,
plus timeline, insights, ai-cards and auth guards.
"""
import os
import uuid
from datetime import date, timedelta

import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://reviens-app.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CLIENT_EMAIL = "client.test@auxora.fr"
CLIENT_PASSWORD = "Test1234!"


# ---------- Fixtures ----------

@pytest.fixture(scope="module")
def client_token():
    r = requests.post(f"{API}/auth/login", json={"email": CLIENT_EMAIL, "password": CLIENT_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def headers(client_token):
    return {"Authorization": f"Bearer {client_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def property_id(headers):
    # Create a fresh test property for this test module
    payload = {
        "type": "apartment",
        "name": f"TEST_MyHome_{uuid.uuid4().hex[:6]}",
        "address": "10 rue de Test",
        "surface": 55,
        "year_built": 2010,
        "notes": "TEST property",
        "photos": [],
    }
    r = requests.post(f"{API}/properties", json=payload, headers=headers, timeout=10)
    assert r.status_code == 200, r.text
    pid = r.json()["property_id"]
    yield pid
    # Teardown
    requests.delete(f"{API}/properties/{pid}", headers=headers, timeout=10)


# ---------- AUTH GUARDS ----------

class TestAuthGuards:
    def test_list_properties_requires_auth(self):
        r = requests.get(f"{API}/properties", timeout=10)
        assert r.status_code == 401

    def test_get_property_requires_auth(self):
        r = requests.get(f"{API}/properties/prop_dummy", timeout=10)
        assert r.status_code == 401

    def test_get_property_404_when_not_owner(self, headers):
        r = requests.get(f"{API}/properties/prop_does_not_exist_zzz", headers=headers, timeout=10)
        assert r.status_code == 404


# ---------- PROPERTIES CRUD ----------

class TestPropertiesCRUD:
    def test_create_invalid_type_returns_400(self, headers):
        r = requests.post(f"{API}/properties", json={"type": "bogus", "name": "TEST_x"}, headers=headers, timeout=10)
        assert r.status_code == 400

    def test_create_missing_name_returns_422(self, headers):
        r = requests.post(f"{API}/properties", json={"type": "apartment"}, headers=headers, timeout=10)
        assert r.status_code in (400, 422)

    def test_create_and_get_property(self, headers):
        payload = {"type": "house", "name": f"TEST_House_{uuid.uuid4().hex[:6]}", "address": "5 av. Test", "surface": 120}
        r = requests.post(f"{API}/properties", json=payload, headers=headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["type"] == "house"
        assert data["name"] == payload["name"]
        assert data["surface"] == 120
        pid = data["property_id"]

        # GET back
        g = requests.get(f"{API}/properties/{pid}", headers=headers, timeout=10)
        assert g.status_code == 200
        assert g.json()["property_id"] == pid

        # Cleanup
        d = requests.delete(f"{API}/properties/{pid}", headers=headers, timeout=10)
        assert d.status_code == 200

    def test_list_properties_has_counts(self, headers, property_id):
        r = requests.get(f"{API}/properties", headers=headers, timeout=10)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        found = next((p for p in items if p["property_id"] == property_id), None)
        assert found is not None, "Created property should appear in list"
        for k in ("equipment_count", "document_count", "reminder_count"):
            assert k in found, f"Missing counter: {k}"
            assert isinstance(found[k], int)

    def test_patch_property(self, headers, property_id):
        payload = {"type": "apartment", "name": "TEST_MyHome_Updated", "address": "Nouvelle adresse", "surface": 60, "year_built": 2015}
        r = requests.patch(f"{API}/properties/{property_id}", json=payload, headers=headers, timeout=10)
        assert r.status_code == 200
        assert r.json()["name"] == "TEST_MyHome_Updated"
        # Verify persistence
        g = requests.get(f"{API}/properties/{property_id}", headers=headers, timeout=10)
        assert g.json()["surface"] == 60

    def test_delete_property_cascade(self, headers):
        # Create prop with equipment + document + reminder, then delete → all gone
        p = requests.post(f"{API}/properties", json={"type": "office", "name": "TEST_Cascade"}, headers=headers, timeout=10)
        pid = p.json()["property_id"]

        requests.post(f"{API}/properties/{pid}/equipment", json={"name": "TEST_eq", "category": "boiler", "status": "ok"}, headers=headers, timeout=10)
        requests.post(f"{API}/properties/{pid}/documents", json={"title": "TEST_doc", "category": "invoice"}, headers=headers, timeout=10)
        requests.post(f"{API}/properties/{pid}/reminders", json={"title": "TEST_rem", "due_on": (date.today() + timedelta(days=10)).isoformat()}, headers=headers, timeout=10)

        d = requests.delete(f"{API}/properties/{pid}", headers=headers, timeout=10)
        assert d.status_code == 200
        # GET should now 404
        g = requests.get(f"{API}/properties/{pid}", headers=headers, timeout=10)
        assert g.status_code == 404


# ---------- EQUIPMENT ----------

class TestEquipment:
    def test_create_equipment(self, headers, property_id):
        payload = {
            "name": "TEST_Chaudière",
            "category": "boiler",
            "brand": "Viessmann",
            "model": "Vitodens",
            "serial_number": "SN123",
            "installer": "Plombier X",
            "installed_on": "2020-01-15",
            "warranty_until": "2030-01-15",
            "status": "ok",
            "notes": "Test",
        }
        r = requests.post(f"{API}/properties/{property_id}/equipment", json=payload, headers=headers, timeout=10)
        assert r.status_code == 200
        eq = r.json()
        assert eq["name"] == "TEST_Chaudière"
        assert eq["status"] == "ok"
        pytest.eq_id = eq["equipment_id"]

    def test_list_equipment(self, headers, property_id):
        r = requests.get(f"{API}/properties/{property_id}/equipment", headers=headers, timeout=10)
        assert r.status_code == 200
        assert any(e["equipment_id"] == pytest.eq_id for e in r.json())

    def test_get_equipment(self, headers, property_id):
        r = requests.get(f"{API}/properties/{property_id}/equipment/{pytest.eq_id}", headers=headers, timeout=10)
        assert r.status_code == 200
        assert r.json()["equipment_id"] == pytest.eq_id

    def test_patch_equipment(self, headers, property_id):
        payload = {"name": "TEST_Chaudière v2", "category": "boiler", "status": "attention"}
        r = requests.patch(f"{API}/properties/{property_id}/equipment/{pytest.eq_id}", json=payload, headers=headers, timeout=10)
        assert r.status_code == 200
        assert r.json()["status"] == "attention"

    def test_invalid_status_returns_400(self, headers, property_id):
        r = requests.post(f"{API}/properties/{property_id}/equipment", json={"name": "x", "status": "wtf"}, headers=headers, timeout=10)
        assert r.status_code == 400


# ---------- DOCUMENTS ----------

class TestDocuments:
    def test_create_document(self, headers, property_id):
        payload = {"title": "TEST_Facture", "category": "invoice", "notes": "Test note"}
        r = requests.post(f"{API}/properties/{property_id}/documents", json=payload, headers=headers, timeout=10)
        assert r.status_code == 200
        pytest.doc_id = r.json()["document_id"]

    def test_invalid_category_returns_400(self, headers, property_id):
        r = requests.post(f"{API}/properties/{property_id}/documents", json={"title": "x", "category": "bogus"}, headers=headers, timeout=10)
        assert r.status_code == 400

    def test_list_documents(self, headers, property_id):
        r = requests.get(f"{API}/properties/{property_id}/documents", headers=headers, timeout=10)
        assert r.status_code == 200
        assert any(d["document_id"] == pytest.doc_id for d in r.json())

    def test_delete_document(self, headers, property_id):
        r = requests.delete(f"{API}/properties/{property_id}/documents/{pytest.doc_id}", headers=headers, timeout=10)
        assert r.status_code == 200


# ---------- REMINDERS ----------

class TestReminders:
    def test_create_reminder_upcoming(self, headers, property_id):
        payload = {"title": "TEST_Entretien VMC", "due_on": (date.today() + timedelta(days=30)).isoformat(), "frequency": "yearly"}
        r = requests.post(f"{API}/properties/{property_id}/reminders", json=payload, headers=headers, timeout=10)
        assert r.status_code == 200
        j = r.json()
        assert j["status"] == "upcoming"
        pytest.rem_id = j["reminder_id"]

    def test_create_reminder_due_auto_flag(self, headers, property_id):
        # due_on <= today should be flagged 'due' on list
        payload = {"title": "TEST_Ramonage", "due_on": (date.today() - timedelta(days=1)).isoformat()}
        r = requests.post(f"{API}/properties/{property_id}/reminders", json=payload, headers=headers, timeout=10)
        assert r.status_code == 200
        past_id = r.json()["reminder_id"]

        listed = requests.get(f"{API}/properties/{property_id}/reminders", headers=headers, timeout=10).json()
        target = next(x for x in listed if x["reminder_id"] == past_id)
        assert target["status"] == "due"
        pytest.past_rem_id = past_id

    def test_patch_reminder_done(self, headers, property_id):
        r = requests.patch(f"{API}/properties/{property_id}/reminders/{pytest.rem_id}", json={"status": "done"}, headers=headers, timeout=10)
        assert r.status_code == 200
        assert r.json()["status"] == "done"

    def test_invalid_status(self, headers, property_id):
        r = requests.patch(f"{API}/properties/{property_id}/reminders/{pytest.rem_id}", json={"status": "bogus"}, headers=headers, timeout=10)
        assert r.status_code == 400

    def test_delete_reminder(self, headers, property_id):
        r = requests.delete(f"{API}/properties/{property_id}/reminders/{pytest.past_rem_id}", headers=headers, timeout=10)
        assert r.status_code == 200


# ---------- TIMELINE ----------

class TestTimeline:
    def test_timeline_structure(self, headers, property_id):
        r = requests.get(f"{API}/properties/{property_id}/timeline", headers=headers, timeout=10)
        assert r.status_code == 200
        j = r.json()
        assert "events" in j and isinstance(j["events"], list)
        assert "grouped" in j and isinstance(j["grouped"], dict)
        # Done reminder (from previous test) should appear
        types = [e["type"] for e in j["events"]]
        assert "reminder_done" in types
        # Sanity: events sorted desc by date
        dates = [e["date"] for e in j["events"] if e.get("date")]
        assert dates == sorted(dates, reverse=True)


# ---------- INSIGHTS ----------

class TestInsights:
    def test_insights_shape(self, headers, property_id):
        r = requests.get(f"{API}/properties/{property_id}/insights", headers=headers, timeout=10)
        assert r.status_code == 200
        j = r.json()
        for k in ("equipment_count", "equipment_ok", "equipment_attention", "document_count",
                  "upcoming_maintenance", "interventions", "money_invested", "average_health", "demo_values"):
            assert k in j, f"Missing insight key: {k}"
        assert 0 <= j["average_health"] <= 100

    def test_insights_demo_values_when_empty(self, headers):
        # Fresh empty property
        p = requests.post(f"{API}/properties", json={"type": "vacation", "name": "TEST_Empty"}, headers=headers, timeout=10)
        pid = p.json()["property_id"]
        r = requests.get(f"{API}/properties/{pid}/insights", headers=headers, timeout=10)
        assert r.status_code == 200
        j = r.json()
        assert j["demo_values"] is True
        assert j["money_invested"] > 0
        assert j["interventions"] > 0
        requests.delete(f"{API}/properties/{pid}", headers=headers, timeout=10)


# ---------- AI CARDS ----------

class TestAICards:
    def test_ai_cards(self, headers, property_id):
        r = requests.get(f"{API}/properties/{property_id}/ai-cards", headers=headers, timeout=10)
        assert r.status_code == 200
        cards = r.json()
        assert isinstance(cards, list) and len(cards) == 6
        keys = {c["key"] for c in cards}
        expected = {"equipment_health", "maintenance_prediction", "risk_detection",
                    "energy_optimization", "warranty_expiration", "recommended_inspection"}
        assert keys == expected
        for c in cards:
            assert c["status"] == "coming_soon"
            assert c.get("title") and c.get("subtitle") and c.get("icon")
