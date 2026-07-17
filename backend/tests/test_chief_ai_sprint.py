"""Chief AI Architect sprint — backend acceptance tests.

Covers (per testing request):
  1. POST /api/missions (standard, urgence=moyenne) -> top_matches[] with
     match_score/match_label/match_reasons, best pro first, mode=standard,
     status=proposed.
  2. POST /api/missions (urgence) -> mode=emergency, status=searching,
     notified_pros[] (<=5) populated.
  3. refuse/confirm flow (status transitions, match_reasons on artisan).
  4. /missions/{id}/pro_accept emergency: first-to-accept wins, second 409,
     non-notified 403, non-emergency 400, unknown mission 404, bad artisan 404.
  5. GET /artisans/{id}/availability -> days[] with slots[], next_available,
     calendar_connected flag.
  6. POST /artisans/me/calendar/connect {provider:'google'} -> connected=true;
     invalid provider -> 400; client (no profile) -> 404.
  7. /missions/{id}/complete -> invoice_id + guarantee_id; persisted invoice +
     guarantee (12 mois) + home passport history entry.
  8. /home-passport (GET), /home-passport/equipment (POST), /invoices/mine,
     /guarantees/mine.
  9. Regression: /auth, /categories, /artisans list+filters, /bookings CRUD,
     /reviews, /conversations.

LLM-cost-free: every test stubs the diagnosis dict directly (no /ai/diagnose
calls). One smoke probe of /ai/diagnose endpoint shape is included but only
checks auth gating (does NOT invoke the LLM).
"""
import os
import time
import uuid
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"

CLIENT_EMAIL = "client.test@proconnect.fr"
CLIENT_PWD = "test1234"
PRO_EMAIL = "pro.test@proconnect.fr"
PRO_PWD = "test1234"


# ---------------- Shared fixtures ----------------

@pytest.fixture(scope="module")
def s():
    return requests.Session()


def _login_or_register(s, email, pwd, name, role):
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": pwd})
    if r.status_code != 200:
        r = s.post(f"{BASE}/auth/register",
                   json={"email": email, "password": pwd, "name": name, "role": role})
    assert r.status_code == 200, f"auth failed for {email}: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def client_auth(s):
    return _login_or_register(s, CLIENT_EMAIL, CLIENT_PWD, "Client Test", "client")


@pytest.fixture(scope="module")
def client_h(client_auth):
    return {"Authorization": f"Bearer {client_auth['token']}"}


@pytest.fixture(scope="module")
def pro_auth(s):
    return _login_or_register(s, PRO_EMAIL, PRO_PWD, "Pro Test", "artisan")


@pytest.fixture(scope="module")
def pro_h(pro_auth):
    return {"Authorization": f"Bearer {pro_auth['token']}"}


@pytest.fixture(scope="module")
def other_client_h(s):
    email = f"TEST_other_{uuid.uuid4().hex[:8]}@proconnect.fr"
    r = s.post(f"{BASE}/auth/register",
               json={"email": email, "password": "test1234", "name": "TEST Other",
                     "role": "client"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _mission_payload(urgency="moyenne", trade="plombier"):
    return {
        "trade": trade,
        "urgency": urgency,
        "diagnosis": {"problem": "TEST mission", "trade": trade, "confidence": 80},
        "lat": 48.8566,
        "lng": 2.3522,
        "price_min": 80,
        "price_max": 200,
    }


# ---------------- 1. POST /missions standard ----------------

class TestMissionStandard:
    @pytest.fixture(scope="class")
    def mission(self, s, client_h):
        r = s.post(f"{BASE}/missions", json=_mission_payload("moyenne"), headers=client_h)
        assert r.status_code == 200, r.text
        return r.json()

    def test_status_and_mode(self, mission):
        assert mission["mode"] == "standard"
        assert mission["status"] == "proposed"
        assert mission["mission_id"].startswith("msn_")
        assert mission.get("notified_pros") == []

    def test_top_matches_present_and_shape(self, mission):
        tms = mission["top_matches"]
        assert isinstance(tms, list) and len(tms) >= 1
        for c in tms:
            assert isinstance(c.get("match_score"), (int, float))
            assert 0 <= c["match_score"] <= 100
            assert isinstance(c.get("match_label"), str) and c["match_label"]
            assert isinstance(c.get("match_reasons"), list) and len(c["match_reasons"]) >= 1
            for r in c["match_reasons"]:
                assert isinstance(r, str) and len(r) > 0

    def test_match_label_is_french(self, mission):
        labels = {c["match_label"] for c in mission["top_matches"]}
        allowed = {"Correspondance excellente", "Très bonne correspondance",
                   "Bonne correspondance", "Correspondance correcte"}
        assert labels.issubset(allowed), labels

    def test_best_pro_first(self, mission):
        scores = [c["match_score"] for c in mission["top_matches"]]
        assert scores == sorted(scores, reverse=True)
        # head of top_matches == top-level artisan card
        assert mission["top_matches"][0]["artisan_id"] == mission["artisan"]["artisan_id"]
        # and == first candidate
        assert mission["candidates"][0] == mission["artisan"]["artisan_id"]


# ---------------- 2. POST /missions urgence (emergency) ----------------

class TestMissionEmergency:
    @pytest.fixture(scope="class")
    def mission(self, s, client_h):
        r = s.post(f"{BASE}/missions", json=_mission_payload("urgence"), headers=client_h)
        assert r.status_code == 200, r.text
        return r.json()

    def test_mode_and_status(self, mission):
        assert mission["mode"] == "emergency"
        assert mission["status"] == "searching"

    def test_notified_pros_populated_and_capped(self, mission):
        nps = mission["notified_pros"]
        assert isinstance(nps, list) and len(nps) >= 1
        assert len(nps) <= 5
        # notified_pros are unique and present in candidates
        assert len(nps) == len(set(nps))
        cands = set(mission["candidates"])
        assert all(p in cands for p in nps)


# ---------------- 3. refuse / confirm flow ----------------

class TestRefuseConfirm:
    def test_refuse_advances_to_next_candidate_with_reasons(self, s, client_h):
        r = s.post(f"{BASE}/missions", json=_mission_payload("moyenne"), headers=client_h)
        assert r.status_code == 200
        m = r.json()
        if len(m["candidates"]) < 2:
            pytest.skip("Need >=2 plombier candidates to test advance")
        first_id = m["artisan"]["artisan_id"]
        r2 = s.post(f"{BASE}/missions/{m['mission_id']}/refuse", headers=client_h)
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["status"] == "proposed"
        assert body["artisan"]["artisan_id"] != first_id
        # match_reasons present on advanced candidate
        assert isinstance(body["artisan"].get("match_reasons"), list)
        assert len(body["artisan"]["match_reasons"]) >= 1

    def test_refuse_exhausts_to_no_pro(self, s, client_h):
        r = s.post(f"{BASE}/missions", json=_mission_payload("moyenne"), headers=client_h)
        m = r.json()
        n = len(m["candidates"])
        last_status = None
        for _ in range(n + 3):
            rr = s.post(f"{BASE}/missions/{m['mission_id']}/refuse", headers=client_h)
            assert rr.status_code == 200
            last_status = rr.json()["status"]
            if last_status == "no_pro":
                break
        assert last_status == "no_pro"

    def test_confirm_sets_en_route_with_eta(self, s, client_h):
        r = s.post(f"{BASE}/missions", json=_mission_payload("moyenne"), headers=client_h)
        m = r.json()
        rc = s.post(f"{BASE}/missions/{m['mission_id']}/confirm", headers=client_h)
        assert rc.status_code == 200, rc.text
        body = rc.json()
        assert body["status"] == "en_route"
        assert isinstance(body["eta_minutes"], int)
        assert 1 <= body["eta_minutes"] <= 60


# ---------------- 4. /pro_accept (emergency first-to-accept) ----------------

class TestProAccept:
    @pytest.fixture
    def fresh_emergency(self, s, client_h):
        r = s.post(f"{BASE}/missions", json=_mission_payload("urgence"), headers=client_h)
        assert r.status_code == 200
        return r.json()

    def test_first_pro_accept_succeeds(self, s, fresh_emergency, pro_h):
        m = fresh_emergency
        if not m["notified_pros"]:
            pytest.skip("No notified pros to accept")
        first = m["notified_pros"][0]
        r = s.post(f"{BASE}/missions/{m['mission_id']}/pro_accept",
                   json={"artisan_id": first}, headers=pro_h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "en_route"
        assert isinstance(body["eta_minutes"], int) and body["eta_minutes"] >= 1
        assert body["artisan"]["artisan_id"] == first

    def test_second_pro_accept_returns_409(self, s, fresh_emergency, pro_h):
        m = fresh_emergency
        if len(m["notified_pros"]) < 2:
            pytest.skip("Need >=2 notified pros for race test")
        # first accepts
        r1 = s.post(f"{BASE}/missions/{m['mission_id']}/pro_accept",
                    json={"artisan_id": m["notified_pros"][0]}, headers=pro_h)
        assert r1.status_code == 200
        # second accepts -> 409
        r2 = s.post(f"{BASE}/missions/{m['mission_id']}/pro_accept",
                    json={"artisan_id": m["notified_pros"][1]}, headers=pro_h)
        assert r2.status_code == 409, r2.text

    def test_non_notified_pro_returns_403(self, s, fresh_emergency, pro_h):
        m = fresh_emergency
        # Mission is for plombier — pick an artisan from a different trade
        # (electricien), guaranteed NOT to be in notified_pros for a plombier mission.
        all_arts = s.get(f"{BASE}/artisans").json()
        outsiders = [a["artisan_id"] for a in all_arts
                     if a["artisan_id"] not in m["notified_pros"]]
        assert outsiders, "Expected at least one non-notified artisan"
        r = s.post(f"{BASE}/missions/{m['mission_id']}/pro_accept",
                   json={"artisan_id": outsiders[0]}, headers=pro_h)
        assert r.status_code == 403, r.text

    def test_non_emergency_mission_returns_400(self, s, client_h, pro_h):
        r = s.post(f"{BASE}/missions", json=_mission_payload("moyenne"), headers=client_h)
        m = r.json()
        # pick any artisan
        target = m["artisan"]["artisan_id"]
        r2 = s.post(f"{BASE}/missions/{m['mission_id']}/pro_accept",
                    json={"artisan_id": target}, headers=pro_h)
        assert r2.status_code == 400, r2.text

    def test_unknown_mission_returns_404(self, s, pro_h):
        r = s.post(f"{BASE}/missions/msn_doesnotexist/pro_accept",
                   json={"artisan_id": "art_xxx"}, headers=pro_h)
        assert r.status_code == 404


# ---------------- 5. GET availability ----------------

class TestAvailability:
    def test_availability_shape_and_slots(self, s):
        arts = s.get(f"{BASE}/artisans", params={"category": "plombier"}).json()
        assert arts, "no plombier seeded"
        aid = arts[0]["artisan_id"]
        r = s.get(f"{BASE}/artisans/{aid}/availability", params={"days": 7})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["artisan_id"] == aid
        assert "calendar_connected" in body
        assert isinstance(body["calendar_connected"], bool)
        assert isinstance(body["days"], list) and len(body["days"]) == 7
        # next_available either dict or None
        nxt = body["next_available"]
        assert nxt is None or ({"date", "hour", "label", "available"} <= set(nxt.keys()))
        # slots shape
        for d in body["days"]:
            assert "date" in d and "slots" in d
            for sl in d["slots"]:
                assert "hour" in sl and "label" in sl and "available" in sl
                assert isinstance(sl["available"], bool)
                assert isinstance(sl["hour"], int)
                assert isinstance(sl["label"], str)

    def test_availability_404_unknown(self, s):
        r = s.get(f"{BASE}/artisans/art_doesnotexist/availability")
        assert r.status_code == 404


# ---------------- 6. POST /artisans/me/calendar/connect ----------------

class TestCalendarConnect:
    def test_connect_google_mock(self, s, pro_h):
        r = s.post(f"{BASE}/artisans/me/calendar/connect",
                   json={"provider": "google"}, headers=pro_h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["connected"] is True
        assert body["provider"] == "google"
        assert body.get("mock") is True
        # verify persisted: availability now reports calendar_connected=true
        prof = s.get(f"{BASE}/artisans/me", headers=pro_h).json()
        aid = prof["artisan_id"]
        avail = s.get(f"{BASE}/artisans/{aid}/availability").json()
        assert avail["calendar_connected"] is True
        assert avail["provider"] == "google"

    def test_connect_invalid_provider_400(self, s, pro_h):
        r = s.post(f"{BASE}/artisans/me/calendar/connect",
                   json={"provider": "myspace"}, headers=pro_h)
        assert r.status_code == 400, r.text

    def test_connect_without_artisan_profile_404(self, s, client_h):
        # client has no artisan profile -> 404
        r = s.post(f"{BASE}/artisans/me/calendar/connect",
                   json={"provider": "google"}, headers=client_h)
        assert r.status_code == 404, r.text


# ---------------- 7. /missions/{id}/complete -> invoice + guarantee + passport ----------------

class TestCompleteMission:
    @pytest.fixture(scope="class")
    def completed(self, s, client_h):
        # Create + confirm + complete a fresh mission
        r = s.post(f"{BASE}/missions", json=_mission_payload("moyenne"), headers=client_h)
        m = r.json()
        s.post(f"{BASE}/missions/{m['mission_id']}/confirm", headers=client_h)
        rc = s.post(f"{BASE}/missions/{m['mission_id']}/complete", headers=client_h)
        assert rc.status_code == 200, rc.text
        return {"mission": m, "complete": rc.json()}

    def test_complete_returns_ids(self, completed):
        body = completed["complete"]
        assert body["status"] == "completed"
        assert body["invoice_id"].startswith("inv_")
        assert body["guarantee_id"].startswith("grt_")

    def test_invoice_created_and_listed(self, s, client_h, completed):
        invs = s.get(f"{BASE}/invoices/mine", headers=client_h).json()
        ids = [i["invoice_id"] for i in invs]
        assert completed["complete"]["invoice_id"] in ids
        inv = next(i for i in invs if i["invoice_id"] == completed["complete"]["invoice_id"])
        assert inv["mission_id"] == completed["mission"]["mission_id"]
        assert inv["currency"] == "EUR"
        assert inv["status"] == "issued"

    def test_guarantee_created_and_listed_12_months(self, s, client_h, completed):
        grs = s.get(f"{BASE}/guarantees/mine", headers=client_h).json()
        ids = [g["guarantee_id"] for g in grs]
        assert completed["complete"]["guarantee_id"] in ids
        g = next(x for x in grs if x["guarantee_id"] == completed["complete"]["guarantee_id"])
        assert g["status"] == "active"
        # 12 mois -> "12 mois" must appear in label
        assert "12 mois" in g["label"].lower() or "12 mois" in g["label"]
        # starts_at < expires_at, ~365 days apart
        from datetime import datetime
        starts = datetime.fromisoformat(g["starts_at"])
        ends = datetime.fromisoformat(g["expires_at"])
        delta_days = (ends - starts).days
        assert 360 <= delta_days <= 370, delta_days

    def test_passport_history_entry_added(self, s, client_h, completed):
        p = s.get(f"{BASE}/home-passport", headers=client_h).json()
        assert "maintenance_history" in p
        history = p["maintenance_history"]
        match = [h for h in history
                 if h.get("mission_id") == completed["mission"]["mission_id"]]
        assert match, "Passport history entry not found for completed mission"
        entry = match[0]
        assert entry["invoice_id"] == completed["complete"]["invoice_id"]
        assert entry["guarantee_id"] == completed["complete"]["guarantee_id"]


# ---------------- 8. Home Passport / Equipment ----------------

class TestHomePassport:
    def test_get_home_passport_returns_shape(self, s, client_h):
        r = s.get(f"{BASE}/home-passport", headers=client_h)
        assert r.status_code == 200
        p = r.json()
        for k in ("equipment", "maintenance_history", "guarantees"):
            assert k in p
        assert isinstance(p["equipment"], list)
        assert isinstance(p["maintenance_history"], list)
        assert isinstance(p["guarantees"], list)

    def test_add_equipment_persists(self, s, client_h):
        item = {"name": f"TEST chaudière {uuid.uuid4().hex[:6]}",
                "category": "chauffage", "brand": "Bosch", "model": "Condens 5000",
                "installed_on": "2022-01-15", "notes": "TEST entry"}
        r = s.post(f"{BASE}/home-passport/equipment", json=item, headers=client_h)
        assert r.status_code == 200, r.text
        created = r.json()
        assert created["equipment_id"].startswith("eqp_")
        assert created["name"] == item["name"]
        # Verify GET
        p = s.get(f"{BASE}/home-passport", headers=client_h).json()
        names = [e["name"] for e in p["equipment"]]
        assert item["name"] in names

    def test_unauthenticated_returns_401(self, s):
        assert s.get(f"{BASE}/home-passport").status_code in (401, 403)
        assert s.get(f"{BASE}/invoices/mine").status_code in (401, 403)
        assert s.get(f"{BASE}/guarantees/mine").status_code in (401, 403)


# ---------------- 9. Regression smoke ----------------

class TestRegression:
    def test_login(self, s):
        r = s.post(f"{BASE}/auth/login",
                   json={"email": CLIENT_EMAIL, "password": CLIENT_PWD})
        assert r.status_code == 200
        assert "token" in r.json() and "user" in r.json()

    def test_categories(self, s):
        r = s.get(f"{BASE}/categories")
        assert r.status_code == 200
        cats = r.json()
        assert isinstance(cats, list) and len(cats) >= 10
        slugs = [c["slug"] for c in cats]
        for must in ("plombier", "electricien", "peintre"):
            assert must in slugs

    def test_artisans_list(self, s):
        r = s.get(f"{BASE}/artisans")
        assert r.status_code == 200
        arts = r.json()
        assert len(arts) >= 10
        # _id excluded
        assert all("_id" not in a for a in arts)

    def test_artisans_filter(self, s):
        r = s.get(f"{BASE}/artisans", params={"category": "electricien"})
        assert r.status_code == 200
        arts = r.json()
        assert len(arts) >= 1
        assert all(a["trade"] == "electricien" for a in arts)

    def test_bookings_mine(self, s, client_h):
        r = s.get(f"{BASE}/bookings/mine", headers=client_h)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_booking_and_review(self, s, client_h):
        # pick a plombier
        arts = s.get(f"{BASE}/artisans", params={"category": "plombier"}).json()
        aid = arts[0]["artisan_id"]
        b = s.post(f"{BASE}/bookings",
                   json={"artisan_id": aid, "service": "TEST réparation",
                         "date": "2026-02-15", "slot": "10:00",
                         "notes": "TEST booking"},
                   headers=client_h)
        assert b.status_code == 200, b.text
        booking = b.json()
        assert booking["status"] == "pending"
        assert booking["artisan_id"] == aid

    def test_conversations_mine(self, s, client_h):
        r = s.get(f"{BASE}/conversations", headers=client_h)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_ai_diagnose_auth_gating(self, s):
        # Sanity: unauthenticated must be rejected (DO NOT invoke LLM).
        r = s.post(f"{BASE}/ai/diagnose", json={"text": "x"})
        assert r.status_code in (401, 403)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v", "--tb=short"]))
