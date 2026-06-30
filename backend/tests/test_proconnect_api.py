"""ProConnect backend API tests"""
import os, uuid, pytest, requests

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://handyman-hub-342.preview.emergentagent.com").rstrip("/") + "/api"

@pytest.fixture(scope="session")
def s():
    return requests.Session()

@pytest.fixture(scope="session")
def client_auth(s):
    r = s.post(f"{BASE}/auth/login", json={"email":"client.test@proconnect.fr","password":"test1234"})
    if r.status_code != 200:
        r = s.post(f"{BASE}/auth/register", json={"email":"client.test@proconnect.fr","password":"test1234","name":"Client Test","role":"client"})
    assert r.status_code == 200, r.text
    return r.json()

@pytest.fixture(scope="session")
def artisan_auth(s):
    r = s.post(f"{BASE}/auth/login", json={"email":"pro.test@proconnect.fr","password":"test1234"})
    if r.status_code != 200:
        r = s.post(f"{BASE}/auth/register", json={"email":"pro.test@proconnect.fr","password":"test1234","name":"Pro Test","role":"artisan"})
    assert r.status_code == 200, r.text
    return r.json()

# ---------------- Auth ----------------
def test_root(s):
    r = s.get(f"{BASE}/")
    assert r.status_code == 200

def test_register_duplicate(s, client_auth):
    r = s.post(f"{BASE}/auth/register", json={"email":"client.test@proconnect.fr","password":"x","name":"x","role":"client"})
    assert r.status_code == 400

def test_login_ok(s):
    r = s.post(f"{BASE}/auth/login", json={"email":"client.test@proconnect.fr","password":"test1234"})
    assert r.status_code == 200 and "token" in r.json()

def test_login_bad(s):
    r = s.post(f"{BASE}/auth/login", json={"email":"client.test@proconnect.fr","password":"wrong"})
    assert r.status_code == 401

def test_me_with_token(s, client_auth):
    r = s.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {client_auth['token']}"})
    assert r.status_code == 200
    assert r.json()["email"] == "client.test@proconnect.fr"

def test_me_no_token(s):
    r = s.get(f"{BASE}/auth/me")
    assert r.status_code == 401

def test_protected_no_token(s):
    assert s.get(f"{BASE}/bookings/mine").status_code == 401
    assert s.get(f"{BASE}/artisans/me").status_code == 401
    assert s.post(f"{BASE}/artisans/me/subscribe").status_code == 401

# ---------------- Public ----------------
def test_categories(s):
    r = s.get(f"{BASE}/categories")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 12
    assert any(c["slug"] == "plombier" for c in data)

def test_top_artisans(s):
    r = s.get(f"{BASE}/artisans/top")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) > 0
    assert "trade_name" in data[0] and "_id" not in data[0]

def test_filter_category(s):
    r = s.get(f"{BASE}/artisans", params={"category":"plombier"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    assert all(a["trade"] == "plombier" for a in data)

def test_search_q(s):
    r = s.get(f"{BASE}/artisans", params={"q":"Paris"})
    assert r.status_code == 200
    assert any("paris" in (a.get("city","").lower()) for a in r.json())

def test_get_artisan_by_id(s):
    top = s.get(f"{BASE}/artisans/top").json()
    aid = top[0]["artisan_id"]
    r = s.get(f"{BASE}/artisans/{aid}")
    assert r.status_code == 200 and r.json()["artisan_id"] == aid

def test_get_artisan_404(s):
    assert s.get(f"{BASE}/artisans/nope").status_code == 404

# ---------------- Artisan profile ----------------
def test_client_cannot_create_profile(s, client_auth):
    h = {"Authorization": f"Bearer {client_auth['token']}"}
    r = s.post(f"{BASE}/artisans/me", json={"trade":"peintre","title":"x"}, headers=h)
    assert r.status_code == 403

def test_artisan_profile_flow(s, artisan_auth):
    h = {"Authorization": f"Bearer {artisan_auth['token']}"}
    payload = {"trade":"peintre","title":"Peintre pro","bio":"bio","city":"Paris","hourly_rate":45}
    r = s.post(f"{BASE}/artisans/me", json=payload, headers=h)
    assert r.status_code == 200
    assert r.json()["trade"] == "peintre"
    # GET me
    r2 = s.get(f"{BASE}/artisans/me", headers=h)
    assert r2.status_code == 200 and r2.json()["title"] == "Peintre pro"
    # Subscribe
    r3 = s.post(f"{BASE}/artisans/me/subscribe", headers=h)
    assert r3.status_code == 200 and r3.json()["ok"] is True
    # Now visible in list
    r4 = s.get(f"{BASE}/artisans", params={"category":"peintre"})
    assert any(a.get("user_id") == artisan_auth["user"]["user_id"] for a in r4.json())

# ---------------- Booking flow ----------------
def test_booking_full_flow(s, client_auth, artisan_auth):
    ch = {"Authorization": f"Bearer {client_auth['token']}"}
    ah = {"Authorization": f"Bearer {artisan_auth['token']}"}
    # ensure artisan profile + subscribe
    s.post(f"{BASE}/artisans/me", json={"trade":"peintre","title":"Peintre pro","city":"Paris","hourly_rate":45}, headers=ah)
    s.post(f"{BASE}/artisans/me/subscribe", headers=ah)
    me_art = s.get(f"{BASE}/artisans/me", headers=ah).json()
    aid = me_art["artisan_id"]
    # create booking
    r = s.post(f"{BASE}/bookings", json={"artisan_id":aid,"date":"2026-02-15","slot":"10:00","description":"TEST_booking"}, headers=ch)
    assert r.status_code == 200
    bid = r.json()["booking_id"]
    assert r.json()["status"] == "pending"
    # mine
    mine = s.get(f"{BASE}/bookings/mine", headers=ch).json()
    assert any(b["booking_id"] == bid for b in mine)
    # received
    recv = s.get(f"{BASE}/bookings/received", headers=ah).json()
    assert any(b["booking_id"] == bid for b in recv)
    # accept
    r2 = s.patch(f"{BASE}/bookings/{bid}", json={"status":"accepted"}, headers=ah)
    assert r2.status_code == 200 and r2.json()["status"] == "accepted"
    # invalid status
    r3 = s.patch(f"{BASE}/bookings/{bid}", json={"status":"foo"}, headers=ah)
    assert r3.status_code == 400

def test_booking_invalid_artisan(s, client_auth):
    h = {"Authorization": f"Bearer {client_auth['token']}"}
    r = s.post(f"{BASE}/bookings", json={"artisan_id":"nope","date":"2026-02-15","slot":"10:00"}, headers=h)
    assert r.status_code == 404

def test_logout(s):
    r = s.post(f"{BASE}/auth/login", json={"email":"client.test@proconnect.fr","password":"test1234"})
    tok = r.json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert s.post(f"{BASE}/auth/logout", headers=h).status_code == 200
    assert s.get(f"{BASE}/auth/me", headers=h).status_code == 401
