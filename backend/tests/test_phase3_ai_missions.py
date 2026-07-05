"""Phase 3 backend tests: AI diagnose/transcribe + Missions matching/tracking lifecycle.

NOTE: /api/ai/diagnose calls a real LLM (Emergent universal key) -> we keep the LLM
calls to a STRICT MINIMUM (2 successful calls + 1 unauth call). Mission lifecycle
tests do not consume LLM credits and run with a stub diagnosis dict.
"""
import os
import json
import base64
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"

ALLOWED_TRADES = {"plombier","electricien","chauffagiste","climaticien","peintre",
                  "serrurier","menuisier","macon","carreleur","jardinier","vitrier","couvreur"}
ALLOWED_URGENCY = {"faible","moyenne","elevee","urgence"}


@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def client_tok(s):
    r = s.post(f"{BASE}/auth/login", json={"email": "client.test@proconnect.fr", "password": "test1234"})
    if r.status_code != 200:
        r = s.post(f"{BASE}/auth/register", json={"email": "client.test@proconnect.fr",
                                                  "password": "test1234", "name": "Client Test", "role": "client"})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def client_headers(client_tok):
    return {"Authorization": f"Bearer {client_tok['token']}"}


@pytest.fixture(scope="module")
def other_client_tok(s):
    """A second client used for ownership checks."""
    email = "other.client.test@proconnect.fr"
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": "test1234"})
    if r.status_code != 200:
        r = s.post(f"{BASE}/auth/register", json={"email": email, "password": "test1234",
                                                  "name": "Other Client", "role": "client"})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- AI Diagnose ----------------

@pytest.fixture(scope="module")
def diag_result(s, client_headers):
    """Run ONE LLM diagnose call and share its result across tests."""
    payload = {"text": "ma chaudière fuit et ne chauffe plus", "lat": 48.8566, "lng": 2.3522}
    r = s.post(f"{BASE}/ai/diagnose", json=payload, headers=client_headers, timeout=90)
    assert r.status_code == 200, r.text
    return r.json()


def test_diagnose_unauthenticated(s):
    r = s.post(f"{BASE}/ai/diagnose", json={"text": "fuite"})
    assert r.status_code in (401, 403)


def test_diagnose_text_only_returns_valid_schema(diag_result):
    d = diag_result
    # required keys
    for k in ("problem", "trade", "trade_label", "trade_icon", "urgency",
              "duration_min", "duration_max", "price_min", "price_max",
              "materials", "confidence", "advice"):
        assert k in d, f"missing key {k} in {d}"
    assert d["trade"] in ALLOWED_TRADES, d["trade"]
    assert d["urgency"] in ALLOWED_URGENCY, d["urgency"]
    assert isinstance(d["duration_min"], (int, float))
    assert isinstance(d["duration_max"], (int, float))
    assert isinstance(d["price_min"], (int, float))
    assert isinstance(d["price_max"], (int, float))
    assert isinstance(d["materials"], list)
    assert isinstance(d["confidence"], (int, float))
    assert 0 <= d["confidence"] <= 100
    assert isinstance(d["problem"], str) and len(d["problem"]) > 0
    assert isinstance(d["advice"], str)


def test_diagnose_picks_relevant_trade(diag_result):
    # Boiler problem should map to plombier or chauffagiste
    assert diag_result["trade"] in ("plombier", "chauffagiste"), diag_result["trade"]


# ---------------- AI Transcribe ----------------

def test_transcribe_unauthenticated(s):
    r = s.post(f"{BASE}/ai/transcribe", json={"audio_base64": "AAAA", "ext": "wav"})
    assert r.status_code in (401, 403)


# ---------------- Missions: matching, refuse, confirm, GET (interp), complete ----------------

@pytest.fixture(scope="module")
def mission(s, client_headers):
    payload = {
        "trade": "plombier",
        "urgency": "elevee",
        "diagnosis": {"problem": "fuite WC", "trade": "plombier", "confidence": 80},
        "lat": 48.8566, "lng": 2.3522,
        "price_min": 80, "price_max": 200,
    }
    r = s.post(f"{BASE}/missions", json=payload, headers=client_headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_create_mission_shape(mission):
    m = mission
    assert m["status"] == "proposed"
    assert m["mission_id"].startswith("msn_")
    a = m["artisan"]
    for k in ("artisan_id", "rating", "trust_score", "acceptance_rate", "response_min"):
        assert k in a, f"artisan card missing {k}"
    # distance available because lat/lng provided
    assert a.get("distance_km") is not None
    cands = m["candidates"]
    assert isinstance(cands, list) and len(cands) > 0
    # first candidate matches best artisan
    assert cands[0] == a["artisan_id"]


def test_mission_refuse_advances_and_exhausts(s, client_headers):
    # create separate mission to exhaust without affecting main flow
    payload = {"trade": "plombier", "urgency": "moyenne", "diagnosis": {},
               "lat": 48.8566, "lng": 2.3522, "price_min": 50, "price_max": 150}
    r = s.post(f"{BASE}/missions", json=payload, headers=client_headers)
    assert r.status_code == 200
    m0 = r.json()
    n = len(m0["candidates"])
    first_id = m0["artisan"]["artisan_id"]

    # Refuse once -> if more candidates remain, status proposed + different artisan
    r2 = s.post(f"{BASE}/missions/{m0['mission_id']}/refuse", headers=client_headers)
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    if n > 1:
        assert body2["status"] == "proposed"
        assert body2["artisan"]["artisan_id"] != first_id
    # Refuse until exhausted
    for _ in range(n + 2):
        rr = s.post(f"{BASE}/missions/{m0['mission_id']}/refuse", headers=client_headers)
        assert rr.status_code == 200
        if rr.json()["status"] == "no_pro":
            break
    final = s.post(f"{BASE}/missions/{m0['mission_id']}/refuse", headers=client_headers).json()
    assert final["status"] == "no_pro"


def test_mission_confirm_sets_en_route(s, client_headers, mission):
    r = s.post(f"{BASE}/missions/{mission['mission_id']}/confirm", headers=client_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "en_route"
    assert isinstance(body["eta_minutes"], int) and body["eta_minutes"] >= 1


def test_mission_get_returns_live_position(s, client_headers, mission):
    r = s.get(f"{BASE}/missions/{mission['mission_id']}", headers=client_headers)
    assert r.status_code == 200
    m = r.json()
    # Status is either en_route (still tracking) or arrived (if ETA was tiny and elapsed)
    assert m["status"] in ("en_route", "arrived")
    assert "current_lat" in m and "current_lng" in m
    assert isinstance(m["current_lat"], (int, float))
    assert isinstance(m["current_lng"], (int, float))
    assert "eta_remaining" in m
    assert isinstance(m["eta_remaining"], (int, float))


def test_mission_complete(s, client_headers, mission):
    r = s.post(f"{BASE}/missions/{mission['mission_id']}/complete", headers=client_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "completed"
    # verify persisted
    r2 = s.get(f"{BASE}/missions/{mission['mission_id']}", headers=client_headers)
    assert r2.status_code == 200
    assert r2.json()["status"] == "completed"


def test_missions_mine_lists_own(s, client_headers, mission):
    r = s.get(f"{BASE}/missions/mine", headers=client_headers)
    assert r.status_code == 200
    ms = r.json()
    assert any(x["mission_id"] == mission["mission_id"] for x in ms)


# ---------------- Ownership ----------------

def test_other_user_cannot_get_mission(s, mission, other_client_tok):
    h = {"Authorization": f"Bearer {other_client_tok['token']}"}
    r = s.get(f"{BASE}/missions/{mission['mission_id']}", headers=h)
    assert r.status_code == 404


def test_other_user_cannot_confirm_mission(s, mission, other_client_tok):
    h = {"Authorization": f"Bearer {other_client_tok['token']}"}
    r = s.post(f"{BASE}/missions/{mission['mission_id']}/confirm", headers=h)
    assert r.status_code == 404


def test_other_user_cannot_refuse_mission(s, mission, other_client_tok):
    h = {"Authorization": f"Bearer {other_client_tok['token']}"}
    r = s.post(f"{BASE}/missions/{mission['mission_id']}/refuse", headers=h)
    assert r.status_code == 404


# ---------------- Regression smoke ----------------

def test_login_smoke(s):
    r = s.post(f"{BASE}/auth/login", json={"email": "client.test@proconnect.fr", "password": "test1234"})
    assert r.status_code == 200
    assert "token" in r.json()


def test_artisans_filter_plombier(s):
    r = s.get(f"{BASE}/artisans", params={"category": "plombier"})
    assert r.status_code == 200
    arts = r.json()
    assert len(arts) > 0
    assert all(a.get("trade") == "plombier" for a in arts)
    # trust_score now present
    assert all("trust_score" in a for a in arts)
    assert all(isinstance(a["trust_score"], (int, float)) for a in arts)
