"""Phase 2 features: messaging, reviews, filters, booking annotations"""
import os, pytest, requests

from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")
BASE = os.environ["EXPO_PUBLIC_BACKEND_URL"].rstrip("/") + "/api"

@pytest.fixture(scope="module")
def s():
    return requests.Session()

@pytest.fixture(scope="module")
def client_tok(s):
    r = s.post(f"{BASE}/auth/login", json={"email":"client.test@proconnect.fr","password":"test1234"})
    if r.status_code != 200:
        r = s.post(f"{BASE}/auth/register", json={"email":"client.test@proconnect.fr","password":"test1234","name":"Client Test","role":"client"})
    assert r.status_code == 200
    return r.json()

@pytest.fixture(scope="module")
def artisan_tok(s):
    r = s.post(f"{BASE}/auth/login", json={"email":"pro.test@proconnect.fr","password":"test1234"})
    if r.status_code != 200:
        r = s.post(f"{BASE}/auth/register", json={"email":"pro.test@proconnect.fr","password":"test1234","name":"Pro Test","role":"artisan"})
    assert r.status_code == 200
    auth = r.json()
    # Ensure profile + subscription
    ah = {"Authorization": f"Bearer {auth['token']}"}
    s.post(f"{BASE}/artisans/me", json={"trade":"peintre","title":"Peintre pro","city":"Paris 11e","hourly_rate":45}, headers=ah)
    s.post(f"{BASE}/artisans/me/subscribe", headers=ah)
    return auth

@pytest.fixture(scope="module")
def booked(s, client_tok, artisan_tok):
    """Create one booking that we will mark completed, plus return ids."""
    ch = {"Authorization": f"Bearer {client_tok['token']}"}
    ah = {"Authorization": f"Bearer {artisan_tok['token']}"}
    me_art = s.get(f"{BASE}/artisans/me", headers=ah).json()
    aid = me_art["artisan_id"]
    r = s.post(f"{BASE}/bookings", json={"artisan_id":aid,"date":"2026-03-10","slot":"11:00","description":"TEST_phase2"}, headers=ch)
    assert r.status_code == 200, r.text
    b = r.json()
    assert "conversation_id" in b and b["conversation_id"].startswith("conv_")
    # accept + complete
    s.patch(f"{BASE}/bookings/{b['booking_id']}", json={"status":"accepted"}, headers=ah)
    rc = s.patch(f"{BASE}/bookings/{b['booking_id']}", json={"status":"completed"}, headers=ah)
    assert rc.status_code == 200
    return {"booking_id": b["booking_id"], "conversation_id": b["conversation_id"], "artisan_id": aid}

# ---------------- Messaging ----------------

def test_booking_creates_conversation(booked):
    assert booked["conversation_id"]

def test_list_conversations_client(s, client_tok, booked):
    h = {"Authorization": f"Bearer {client_tok['token']}"}
    r = s.get(f"{BASE}/conversations", headers=h)
    assert r.status_code == 200
    convs = r.json()
    target = [c for c in convs if c["conversation_id"] == booked["conversation_id"]]
    assert len(target) == 1
    assert "other_name" in target[0]  # the artisan name

def test_list_conversations_artisan(s, artisan_tok, booked):
    h = {"Authorization": f"Bearer {artisan_tok['token']}"}
    r = s.get(f"{BASE}/conversations", headers=h)
    assert r.status_code == 200
    convs = r.json()
    target = [c for c in convs if c["conversation_id"] == booked["conversation_id"]]
    assert len(target) == 1
    assert target[0]["other_name"]  # the client name (Client Test)

def test_get_conversation_ok(s, client_tok, booked):
    h = {"Authorization": f"Bearer {client_tok['token']}"}
    r = s.get(f"{BASE}/conversations/{booked['conversation_id']}", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert "conversation" in data and "messages" in data

def test_get_conversation_forbidden_for_outsider(s, booked):
    # register a 3rd party
    email = "outsider.test@proconnect.fr"
    r = s.post(f"{BASE}/auth/login", json={"email":email,"password":"test1234"})
    if r.status_code != 200:
        r = s.post(f"{BASE}/auth/register", json={"email":email,"password":"test1234","name":"Outsider","role":"client"})
    tok = r.json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    r2 = s.get(f"{BASE}/conversations/{booked['conversation_id']}", headers=h)
    assert r2.status_code == 403

def test_send_message_updates_last_message(s, client_tok, artisan_tok, booked):
    ch = {"Authorization": f"Bearer {client_tok['token']}"}
    ah = {"Authorization": f"Bearer {artisan_tok['token']}"}
    r = s.post(f"{BASE}/conversations/{booked['conversation_id']}/messages", json={"text":"Bonjour TEST"}, headers=ch)
    assert r.status_code == 200
    assert r.json()["text"] == "Bonjour TEST"
    # artisan reply
    r2 = s.post(f"{BASE}/conversations/{booked['conversation_id']}/messages", json={"text":"Reponse TEST"}, headers=ah)
    assert r2.status_code == 200
    # verify list shows last_message
    convs = s.get(f"{BASE}/conversations", headers=ch).json()
    target = [c for c in convs if c["conversation_id"] == booked["conversation_id"]][0]
    assert target["last_message"] == "Reponse TEST"
    # verify messages retrievable
    d = s.get(f"{BASE}/conversations/{booked['conversation_id']}", headers=ch).json()
    texts = [m["text"] for m in d["messages"]]
    assert "Bonjour TEST" in texts and "Reponse TEST" in texts

def test_send_message_forbidden(s, booked):
    r = s.post(f"{BASE}/auth/login", json={"email":"outsider.test@proconnect.fr","password":"test1234"})
    tok = r.json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    r2 = s.post(f"{BASE}/conversations/{booked['conversation_id']}/messages", json={"text":"hack"}, headers=h)
    assert r2.status_code == 403

# ---------------- Reviews ----------------

def test_review_requires_completed(s, client_tok, artisan_tok):
    """Creating a review on a NON-completed booking returns 400."""
    ch = {"Authorization": f"Bearer {client_tok['token']}"}
    ah = {"Authorization": f"Bearer {artisan_tok['token']}"}
    me_art = s.get(f"{BASE}/artisans/me", headers=ah).json()
    aid = me_art["artisan_id"]
    r = s.post(f"{BASE}/bookings", json={"artisan_id":aid,"date":"2026-04-01","slot":"09:00","description":"TEST_not_completed"}, headers=ch)
    bid = r.json()["booking_id"]
    rr = s.post(f"{BASE}/reviews", json={"booking_id":bid,"rating":5,"comment":"x"}, headers=ch)
    assert rr.status_code == 400

def test_client_reviews_artisan_and_rating_updates(s, client_tok, artisan_tok, booked):
    ch = {"Authorization": f"Bearer {client_tok['token']}"}
    # Check rating before
    before = s.get(f"{BASE}/artisans/{booked['artisan_id']}").json()
    before_count = before["reviews_count"]
    r = s.post(f"{BASE}/reviews", json={"booking_id":booked["booking_id"],"rating":4,"comment":"TEST avis client"}, headers=ch)
    assert r.status_code == 200, r.text
    # duplicate -> 400
    rdup = s.post(f"{BASE}/reviews", json={"booking_id":booked["booking_id"],"rating":5,"comment":"dup"}, headers=ch)
    assert rdup.status_code == 400
    # rating recompute
    after = s.get(f"{BASE}/artisans/{booked['artisan_id']}").json()
    assert after["reviews_count"] == before_count + 1
    # artisan reviews list contains it
    revs = s.get(f"{BASE}/reviews/artisan/{booked['artisan_id']}").json()
    assert any(rv["booking_id"] == booked["booking_id"] and rv["rating"] == 4 for rv in revs)

def test_artisan_reviews_client_mutual(s, artisan_tok, booked):
    ah = {"Authorization": f"Bearer {artisan_tok['token']}"}
    r = s.post(f"{BASE}/reviews", json={"booking_id":booked["booking_id"],"rating":5,"comment":"TEST avis artisan"}, headers=ah)
    assert r.status_code == 200
    assert r.json()["to_role"] == "client"

def test_bookings_mine_includes_reviewed_and_conv_id(s, client_tok, booked):
    h = {"Authorization": f"Bearer {client_tok['token']}"}
    mine = s.get(f"{BASE}/bookings/mine", headers=h).json()
    target = [b for b in mine if b["booking_id"] == booked["booking_id"]][0]
    assert "reviewed" in target and target["reviewed"] is True
    assert target.get("conversation_id") == booked["conversation_id"]

def test_bookings_received_includes_reviewed_and_conv_id(s, artisan_tok, booked):
    h = {"Authorization": f"Bearer {artisan_tok['token']}"}
    recv = s.get(f"{BASE}/bookings/received", headers=h).json()
    target = [b for b in recv if b["booking_id"] == booked["booking_id"]][0]
    assert "reviewed" in target
    assert target.get("conversation_id") == booked["conversation_id"]

# ---------------- Filters ----------------

def test_filter_max_rate(s):
    r = s.get(f"{BASE}/artisans", params={"max_rate":45})
    assert r.status_code == 200
    arts = r.json()
    assert all(a.get("hourly_rate", 0) <= 45 for a in arts)
    assert len(arts) > 0

def test_filter_min_rating(s):
    r = s.get(f"{BASE}/artisans", params={"min_rating":4.8})
    assert r.status_code == 200
    arts = r.json()
    assert all(a.get("rating", 0) >= 4.8 for a in arts)

def test_filter_sort_rate_asc(s):
    r = s.get(f"{BASE}/artisans", params={"sort":"rate_asc"})
    assert r.status_code == 200
    arts = r.json()
    rates = [a.get("hourly_rate", 0) for a in arts]
    assert rates == sorted(rates)

def test_filter_distance(s):
    # Lyon coords; radius 50km should include Lyon artisans
    r = s.get(f"{BASE}/artisans", params={"lat":45.76,"lng":4.85,"radius":50,"sort":"distance"})
    assert r.status_code == 200
    arts = r.json()
    assert len(arts) > 0
    # All must have distance_km <= 50
    for a in arts:
        assert a.get("distance_km") is not None and a["distance_km"] <= 50
    # Sorted ascending by distance
    distances = [a["distance_km"] for a in arts]
    assert distances == sorted(distances)

def test_filter_available(s):
    r = s.get(f"{BASE}/artisans", params={"available":"true"})
    assert r.status_code == 200
    arts = r.json()
    assert all(a.get("available", True) is True for a in arts)
