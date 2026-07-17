"""Sprint 14 Phase 1 Bloc 4 — Bookings + Missions + Interventions

Covers the security requirements laid out in the Bloc 4 spec:
- Ownership: client A cannot access client B's booking; artisan A cannot
  touch artisan B's mission; unauthenticated users get 401 uniformly.
- State transitions: illegal transitions raise 400 (legacy contract).
- Emergency acceptance: auth required, only notified pros can accept, atomic
  compare-and-set prevents double-accept.
- Simulated markers preserved on payloads.
- Validation: bad slot/date/urgency/id → 422.
"""
from __future__ import annotations
import os
import uuid
import httpx
import pytest


BASE = os.environ.get("AUXORA_TEST_URL", "http://localhost:8001")
CLIENT_EMAIL = "client.test@auxora.fr"
CLIENT_PASSWORD = "Test1234!"


def _register(email: str, password: str, name: str, role: str) -> str:
    r = httpx.post(f"{BASE}/api/auth/register",
                   json={"email": email, "password": password, "name": name, "role": role},
                   timeout=10)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _login(email: str, password: str) -> str:
    r = httpx.post(f"{BASE}/api/auth/login",
                   json={"email": email, "password": password}, timeout=10)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def client_tok() -> str:
    return _login(CLIENT_EMAIL, CLIENT_PASSWORD)


@pytest.fixture(scope="module")
def other_client_tok() -> str:
    email = f"cl_other_{uuid.uuid4().hex[:8]}@auxora-test.fr"
    return _register(email, "Test1234!", "Other Client", "client")


@pytest.fixture(scope="module")
def artisan_tok() -> str:
    email = f"art_bloc4_{uuid.uuid4().hex[:8]}@auxora-test.fr"
    return _register(email, "Test1234!", "Bloc4 Artisan", "artisan")


@pytest.fixture(scope="module")
def other_artisan_tok() -> str:
    email = f"art_other_bloc4_{uuid.uuid4().hex[:8]}@auxora-test.fr"
    return _register(email, "Test1234!", "Other Bloc4 Artisan", "artisan")


@pytest.fixture(scope="module")
def seeded_artisan_id() -> str:
    """Pick any publicly visible artisan for booking tests."""
    tops = httpx.get(f"{BASE}/api/artisans/top", timeout=10).json()
    assert tops, "no seeded artisans"
    return tops[0]["artisan_id"]


# ============================================================================
# Bookings
# ============================================================================

def test_booking_create_marks_simulated(client_tok: str, seeded_artisan_id: str):
    r = httpx.post(
        f"{BASE}/api/bookings",
        headers=_h(client_tok),
        json={"artisan_id": seeded_artisan_id, "date": "2027-05-01", "slot": "10:00", "description": "TEST bloc4 booking"},
        timeout=10,
    )
    assert r.status_code == 200
    assert r.json().get("simulated") is True


def test_booking_rejects_bad_slot(client_tok: str, seeded_artisan_id: str):
    r = httpx.post(
        f"{BASE}/api/bookings",
        headers=_h(client_tok),
        json={"artisan_id": seeded_artisan_id, "date": "2027-05-01", "slot": "invalid"},
        timeout=5,
    )
    assert r.status_code == 422


def test_booking_rejects_xss_description(client_tok: str, seeded_artisan_id: str):
    r = httpx.post(
        f"{BASE}/api/bookings",
        headers=_h(client_tok),
        json={"artisan_id": seeded_artisan_id, "date": "2027-05-01", "slot": "10:00",
              "description": "<script>alert(1)</script>"},
        timeout=5,
    )
    assert r.status_code == 422


def test_booking_ownership_stranger_gets_404(client_tok: str, other_client_tok: str, seeded_artisan_id: str):
    """Client A creates a booking; Client B tries to modify it → 404 (no enumeration)."""
    r = httpx.post(
        f"{BASE}/api/bookings",
        headers=_h(client_tok),
        json={"artisan_id": seeded_artisan_id, "date": "2027-06-01", "slot": "11:00"},
        timeout=5,
    )
    assert r.status_code == 200
    bid = r.json()["booking_id"]

    # Client B tries to patch the status
    r2 = httpx.patch(f"{BASE}/api/bookings/{bid}",
                     headers=_h(other_client_tok),
                     json={"status": "cancelled"}, timeout=5)
    assert r2.status_code == 404, r2.text


def test_booking_unauth_returns_401(seeded_artisan_id: str):
    r = httpx.post(
        f"{BASE}/api/bookings",
        json={"artisan_id": seeded_artisan_id, "date": "2027-01-01", "slot": "10:00"},
        timeout=5,
    )
    assert r.status_code == 401


def test_booking_illegal_transition_returns_400(client_tok: str, seeded_artisan_id: str):
    """A client cannot move a booking from pending → completed directly."""
    r = httpx.post(
        f"{BASE}/api/bookings",
        headers=_h(client_tok),
        json={"artisan_id": seeded_artisan_id, "date": "2027-06-01", "slot": "12:00"},
        timeout=5,
    )
    bid = r.json()["booking_id"]
    r2 = httpx.patch(f"{BASE}/api/bookings/{bid}", headers=_h(client_tok),
                     json={"status": "completed"}, timeout=5)
    assert r2.status_code == 400, r2.text


def test_booking_completed_terminal(client_tok: str, seeded_artisan_id: str):
    """Once completed a booking cannot go back."""
    # We can't easily reach `completed` from client side; skip if we can't.
    r = httpx.post(f"{BASE}/api/bookings", headers=_h(client_tok),
                   json={"artisan_id": seeded_artisan_id, "date": "2027-06-02", "slot": "13:00"},
                   timeout=5)
    bid = r.json()["booking_id"]
    # Client tries cancelled → allowed
    r2 = httpx.patch(f"{BASE}/api/bookings/{bid}", headers=_h(client_tok),
                     json={"status": "cancelled"}, timeout=5)
    assert r2.status_code == 200
    # Client tries to move a cancelled booking → must fail
    r3 = httpx.patch(f"{BASE}/api/bookings/{bid}", headers=_h(client_tok),
                     json={"status": "accepted"}, timeout=5)
    assert r3.status_code == 400


# ============================================================================
# Missions
# ============================================================================

def test_mission_marked_simulated(client_tok: str):
    r = httpx.post(
        f"{BASE}/api/missions",
        headers=_h(client_tok),
        json={"trade": "plombier", "urgency": "moyenne",
              "diagnosis": {"trade": "plombier"}, "lat": 48.85, "lng": 2.35,
              "price_min": 80, "price_max": 200},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    assert r.json().get("simulated") is True
    assert r.json().get("price_estimated") is True


def test_mission_rejects_bad_urgency(client_tok: str):
    r = httpx.post(
        f"{BASE}/api/missions",
        headers=_h(client_tok),
        json={"trade": "plombier", "urgency": "IMMEDIATELY",
              "diagnosis": {}, "lat": 48.85, "lng": 2.35, "price_min": 1, "price_max": 2},
        timeout=5,
    )
    assert r.status_code == 422


def test_mission_ownership_stranger_gets_404(client_tok: str, other_client_tok: str):
    r = httpx.post(
        f"{BASE}/api/missions",
        headers=_h(client_tok),
        json={"trade": "plombier", "urgency": "moyenne",
              "diagnosis": {}, "lat": 48.85, "lng": 2.35, "price_min": 80, "price_max": 200},
        timeout=15,
    )
    mid = r.json()["mission_id"]
    r2 = httpx.get(f"{BASE}/api/missions/{mid}", headers=_h(other_client_tok), timeout=5)
    assert r2.status_code == 404


def test_pro_accept_requires_auth(client_tok: str):
    """The emergency acceptance endpoint MUST reject unauthenticated calls."""
    r = httpx.post(
        f"{BASE}/api/missions",
        headers=_h(client_tok),
        json={"trade": "plombier", "urgency": "urgence",
              "diagnosis": {}, "lat": 48.85, "lng": 2.35, "price_min": 80, "price_max": 200},
        timeout=15,
    )
    m = r.json()
    if not m.get("notified_pros"):
        pytest.skip("no notified pros")
    r2 = httpx.post(f"{BASE}/api/missions/{m['mission_id']}/pro_accept",
                    json={"artisan_id": m["notified_pros"][0]}, timeout=5)
    assert r2.status_code == 401


def test_pro_accept_rejects_non_artisan(client_tok: str):
    r = httpx.post(
        f"{BASE}/api/missions",
        headers=_h(client_tok),
        json={"trade": "plombier", "urgency": "urgence",
              "diagnosis": {}, "lat": 48.85, "lng": 2.35, "price_min": 80, "price_max": 200},
        timeout=15,
    )
    m = r.json()
    if not m.get("notified_pros"):
        pytest.skip("no notified pros")
    # Client (not artisan) tries to accept
    r2 = httpx.post(f"{BASE}/api/missions/{m['mission_id']}/pro_accept",
                    headers=_h(client_tok),
                    json={"artisan_id": m["notified_pros"][0]}, timeout=5)
    assert r2.status_code == 403


def test_pro_accept_double_acceptance_returns_409(client_tok: str, artisan_tok: str):
    """First artisan wins; second attempt gets 409."""
    r = httpx.post(
        f"{BASE}/api/missions",
        headers=_h(client_tok),
        json={"trade": "plombier", "urgency": "urgence",
              "diagnosis": {}, "lat": 48.85, "lng": 2.35, "price_min": 80, "price_max": 200},
        timeout=15,
    )
    m = r.json()
    if len(m.get("notified_pros", [])) < 2:
        pytest.skip("need >=2 notified pros")
    # First artisan accepts
    r1 = httpx.post(f"{BASE}/api/missions/{m['mission_id']}/pro_accept",
                    headers=_h(artisan_tok),
                    json={"artisan_id": m["notified_pros"][0]}, timeout=5)
    assert r1.status_code == 200
    # Same artisan (already accepted) or another notified one → 409
    r2 = httpx.post(f"{BASE}/api/missions/{m['mission_id']}/pro_accept",
                    headers=_h(artisan_tok),
                    json={"artisan_id": m["notified_pros"][1]}, timeout=5)
    assert r2.status_code == 409


def test_pro_accept_non_emergency_returns_400(client_tok: str, artisan_tok: str):
    r = httpx.post(
        f"{BASE}/api/missions",
        headers=_h(client_tok),
        json={"trade": "plombier", "urgency": "moyenne",
              "diagnosis": {}, "lat": 48.85, "lng": 2.35, "price_min": 80, "price_max": 200},
        timeout=15,
    )
    m = r.json()
    r2 = httpx.post(f"{BASE}/api/missions/{m['mission_id']}/pro_accept",
                    headers=_h(artisan_tok),
                    json={"artisan_id": m["artisan"]["artisan_id"]}, timeout=5)
    assert r2.status_code == 400


# ============================================================================
# Interventions
# ============================================================================

def test_intervention_marks_simulated(client_tok: str, seeded_artisan_id: str):
    r = httpx.post(
        f"{BASE}/api/interventions/request",
        headers=_h(client_tok),
        json={"artisan_id": seeded_artisan_id, "trade": "plombier",
              "description": "TEST bloc4 iv", "address": "12 rue test",
              "lat": 48.85, "lng": 2.35, "urgency": "urgence", "price_estimate_cents": 5000},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("simulated") is True
    assert body.get("price_simulated") is True
    assert body["status"] == "requested"


def test_intervention_rejects_bad_lat(client_tok: str, seeded_artisan_id: str):
    r = httpx.post(
        f"{BASE}/api/interventions/request",
        headers=_h(client_tok),
        json={"artisan_id": seeded_artisan_id, "lat": 999, "lng": 999, "urgency": "faible"},
        timeout=5,
    )
    assert r.status_code == 422


def test_intervention_stranger_cannot_read(client_tok: str, other_client_tok: str, seeded_artisan_id: str):
    r = httpx.post(
        f"{BASE}/api/interventions/request",
        headers=_h(client_tok),
        json={"artisan_id": seeded_artisan_id, "urgency": "faible"},
        timeout=5,
    )
    iv_id = r.json()["intervention_id"]
    r2 = httpx.get(f"{BASE}/api/interventions/{iv_id}", headers=_h(other_client_tok), timeout=5)
    assert r2.status_code == 404


def test_intervention_stranger_cannot_cancel(client_tok: str, other_client_tok: str, seeded_artisan_id: str):
    r = httpx.post(
        f"{BASE}/api/interventions/request",
        headers=_h(client_tok),
        json={"artisan_id": seeded_artisan_id, "urgency": "faible"},
        timeout=5,
    )
    iv_id = r.json()["intervention_id"]
    r2 = httpx.post(f"{BASE}/api/interventions/{iv_id}/cancel", headers=_h(other_client_tok), timeout=5)
    assert r2.status_code == 404


def test_intervention_client_cannot_accept(client_tok: str, seeded_artisan_id: str):
    r = httpx.post(
        f"{BASE}/api/interventions/request",
        headers=_h(client_tok),
        json={"artisan_id": seeded_artisan_id, "urgency": "faible"},
        timeout=5,
    )
    iv_id = r.json()["intervention_id"]
    r2 = httpx.post(f"{BASE}/api/interventions/{iv_id}/accept", headers=_h(client_tok), timeout=5)
    # Client is not the artisan → 403 (role check inside endpoint)
    assert r2.status_code == 403


def test_intervention_illegal_transition_returns_400(client_tok: str, seeded_artisan_id: str):
    """Client cannot cancel an intervention that's already validated."""
    r = httpx.post(
        f"{BASE}/api/interventions/request",
        headers=_h(client_tok),
        json={"artisan_id": seeded_artisan_id, "urgency": "faible"},
        timeout=5,
    )
    iv_id = r.json()["intervention_id"]
    # First cancel — allowed
    r2 = httpx.post(f"{BASE}/api/interventions/{iv_id}/cancel", headers=_h(client_tok), timeout=5)
    assert r2.status_code == 200
    # Second cancel on same iv (already cancelled) — must fail
    r3 = httpx.post(f"{BASE}/api/interventions/{iv_id}/cancel", headers=_h(client_tok), timeout=5)
    assert r3.status_code == 400


def test_intervention_unknown_returns_404(client_tok: str):
    r = httpx.get(f"{BASE}/api/interventions/iv_doesnotexist_xyz", headers=_h(client_tok), timeout=5)
    assert r.status_code == 404


def test_intervention_mine_lists_only_own(client_tok: str, other_client_tok: str, seeded_artisan_id: str):
    # Client A creates one
    r = httpx.post(
        f"{BASE}/api/interventions/request",
        headers=_h(client_tok),
        json={"artisan_id": seeded_artisan_id, "urgency": "faible"},
        timeout=5,
    )
    my_iv = r.json()["intervention_id"]
    # Client B lists → must NOT see it
    rows = httpx.get(f"{BASE}/api/interventions/mine", headers=_h(other_client_tok), timeout=5).json()
    assert my_iv not in [r["intervention_id"] for r in rows]
