"""Sprint-specific new features:
- /api/ai/diagnose now returns `causes` (2-3 strings) [ONE LLM call]
- /api/missions returns `top_matches` (up to 3 enriched cards, ranked)
- /api/missions/{id}/book sets status en_route + artisan card + eta_minutes
- Booking unknown artisan -> 404; booking someone else's mission -> 404
"""
import os, pytest, requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


def _login_or_register(s, email, name, role="client"):
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": "test1234"})
    if r.status_code != 200:
        r = s.post(f"{BASE}/auth/register",
                   json={"email": email, "password": "test1234", "name": name, "role": role})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def client_h(s):
    return {"Authorization": f"Bearer {_login_or_register(s, 'client.test@proconnect.fr', 'Client Test')}"}


@pytest.fixture(scope="module")
def other_h(s):
    return {"Authorization": f"Bearer {_login_or_register(s, 'other.client.test@proconnect.fr', 'Other Client')}"}


# --- /api/ai/diagnose: causes (ONE LLM call) ---

def test_diagnose_returns_causes_array(s, client_h):
    r = s.post(f"{BASE}/ai/diagnose",
               json={"text": "ma chaudière fuit et ne chauffe plus", "lat": 48.8566, "lng": 2.3522},
               headers=client_h, timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "causes" in d, f"missing 'causes' in response: {d}"
    assert isinstance(d["causes"], list)
    assert 2 <= len(d["causes"]) <= 3, f"expected 2-3 causes, got {len(d['causes'])}"
    assert all(isinstance(c, str) and len(c) > 0 for c in d["causes"])


# --- /api/missions: top_matches ---

@pytest.fixture(scope="module")
def mission(s, client_h):
    r = s.post(f"{BASE}/missions",
               json={"trade": "plombier", "urgency": "elevee", "diagnosis": {"problem": "fuite"},
                     "lat": 48.8566, "lng": 2.3522, "price_min": 80, "price_max": 200},
               headers=client_h)
    assert r.status_code == 200, r.text
    return r.json()


def test_top_matches_present_and_ranked(mission):
    m = mission
    assert "top_matches" in m and isinstance(m["top_matches"], list)
    tm = m["top_matches"]
    assert 1 <= len(tm) <= 3, f"expected 1-3 top_matches, got {len(tm)}"
    for c in tm:
        for k in ("artisan_id", "name", "rating", "reviews_count", "trust_score",
                  "acceptance_rate", "response_min", "distance_km", "eta_minutes"):
            assert k in c, f"top_match missing {k}: {c}"
        assert isinstance(c["eta_minutes"], int) and c["eta_minutes"] >= 1
    # artisan == top_matches[0]
    assert m["artisan"]["artisan_id"] == tm[0]["artisan_id"]


# --- /api/missions/{id}/book ---

def test_book_specific_artisan_sets_en_route(s, client_h, mission):
    # pick the 2nd match if available, else the 1st
    tm = mission["top_matches"]
    chosen = tm[1] if len(tm) > 1 else tm[0]
    r = s.post(f"{BASE}/missions/{mission['mission_id']}/book",
               json={"artisan_id": chosen["artisan_id"]}, headers=client_h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "en_route"
    assert isinstance(body["eta_minutes"], int) and body["eta_minutes"] >= 1
    assert body["artisan"]["artisan_id"] == chosen["artisan_id"]
    # verify persisted via GET
    r2 = s.get(f"{BASE}/missions/{mission['mission_id']}", headers=client_h)
    assert r2.status_code == 200
    g = r2.json()
    assert g["status"] in ("en_route", "arrived")
    assert g["artisan"]["artisan_id"] == chosen["artisan_id"]


def test_book_unknown_artisan_returns_404(s, client_h):
    # create fresh mission for isolation
    r = s.post(f"{BASE}/missions",
               json={"trade": "plombier", "urgency": "moyenne", "diagnosis": {},
                     "lat": 48.8566, "lng": 2.3522, "price_min": 50, "price_max": 150},
               headers=client_h)
    mid = r.json()["mission_id"]
    rb = s.post(f"{BASE}/missions/{mid}/book",
                json={"artisan_id": "art_doesnotexist_xyz"}, headers=client_h)
    assert rb.status_code == 404


def test_book_someone_elses_mission_returns_404(s, client_h, other_h):
    r = s.post(f"{BASE}/missions",
               json={"trade": "plombier", "urgency": "moyenne", "diagnosis": {},
                     "lat": 48.8566, "lng": 2.3522, "price_min": 50, "price_max": 150},
               headers=client_h)
    m = r.json()
    target_aid = m["top_matches"][0]["artisan_id"]
    rb = s.post(f"{BASE}/missions/{m['mission_id']}/book",
                json={"artisan_id": target_aid}, headers=other_h)
    assert rb.status_code == 404


# --- Regression smoke ---

def test_login_smoke(s):
    r = s.post(f"{BASE}/auth/login", json={"email": "client.test@proconnect.fr", "password": "test1234"})
    assert r.status_code == 200 and "token" in r.json()


def test_artisans_plombier(s):
    r = s.get(f"{BASE}/artisans", params={"category": "plombier"})
    assert r.status_code == 200
    arts = r.json()
    assert len(arts) > 0 and all(a["trade"] == "plombier" for a in arts)


def test_bookings_mine(s, client_h):
    r = s.get(f"{BASE}/bookings/mine", headers=client_h)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
