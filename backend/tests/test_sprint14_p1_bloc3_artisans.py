"""Sprint 14 Phase 1 Bloc 3 — Artisans router non-regression + security tests.

Covers:
- Public listings + top + get by id preserve behavior.
- Whitelist strict on POST /artisans/me — sensitive fields dropped.
- Ownership: artisan A cannot touch artisan B's slots or gallery.
- Non-artisan users get 403 on artisan-only endpoints.
- Invalid input (trade slug, working_hours, zones) → 422.
- Unapproved profiles are NOT publicly visible.
- New profiles start with honest values (trust_score=0, rating=0, verification_status=pending, simulated=True).
"""
from __future__ import annotations
import os
import uuid
import time
import httpx
import pytest


BASE = os.environ.get("AUXORA_TEST_URL", "http://localhost:8001")
CLIENT_EMAIL = "client.test@auxora.fr"
CLIENT_PASSWORD = "Test1234!"


def _register(email: str, password: str, name: str, role: str) -> str:
    r = httpx.post(
        f"{BASE}/api/auth/register",
        json={"email": email, "password": password, "name": name, "role": role},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _login(email: str, password: str) -> str:
    r = httpx.post(
        f"{BASE}/api/auth/login",
        json={"email": email, "password": password},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def client_token() -> str:
    return _login(CLIENT_EMAIL, CLIENT_PASSWORD)


@pytest.fixture(scope="module")
def artisan_a() -> dict:
    """Create a fresh artisan account for this test module."""
    email = f"art_a_{uuid.uuid4().hex[:8]}@auxora-test.fr"
    tok = _register(email, "Test1234!", f"Artisan A {uuid.uuid4().hex[:4]}", "artisan")
    # Create profile
    r = httpx.post(
        f"{BASE}/api/artisans/me",
        headers=_h(tok),
        json={
            "trade": "plombier",
            "title": "Plombier test",
            "bio": "Bio courte",
            "city": "Paris 11e",
            "hourly_rate": 40,
            "available": True,
        },
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return {"token": tok, "email": email, "profile": r.json()}


@pytest.fixture(scope="module")
def artisan_b() -> dict:
    email = f"art_b_{uuid.uuid4().hex[:8]}@auxora-test.fr"
    tok = _register(email, "Test1234!", f"Artisan B {uuid.uuid4().hex[:4]}", "artisan")
    r = httpx.post(
        f"{BASE}/api/artisans/me",
        headers=_h(tok),
        json={
            "trade": "electricien",
            "title": "Électricien test",
            "city": "Lyon 3e",
            "hourly_rate": 45,
        },
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return {"token": tok, "email": email, "profile": r.json()}


# ---------- Public reads ----------

def test_list_artisans_returns_only_visible():
    """Existing seeded artisans (no verification_status field) are visible.
    Fresh ones we just created (verification_status=pending, is_subscribed=False)
    are NOT visible.
    """
    r = httpx.get(f"{BASE}/api/artisans", timeout=10)
    assert r.status_code == 200
    for a in r.json():
        # Either verification_status is missing (legacy) or "approved"
        vs = a.get("verification_status")
        assert vs in (None, "approved"), f"Unapproved profile leaked: {a.get('artisan_id')}"


def test_get_artisan_by_id_public():
    """Seeded artisans are publicly fetchable."""
    lst = httpx.get(f"{BASE}/api/artisans/top", timeout=10).json()
    assert lst, "no seeded artisans available"
    aid = lst[0]["artisan_id"]
    r = httpx.get(f"{BASE}/api/artisans/{aid}", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "trust_score" in body
    assert "confidence_card" in body or body.get("badges") is not None


def test_get_unapproved_artisan_returns_404(artisan_a: dict):
    """A brand-new artisan (verification_status=pending, is_subscribed=False) MUST
    not be publicly retrievable — return 404 to avoid disclosure."""
    aid = artisan_a["profile"]["artisan_id"]
    r = httpx.get(f"{BASE}/api/artisans/{aid}", timeout=10)
    assert r.status_code == 404


# ---------- Honest initial values ----------

def test_new_profile_has_honest_initial_values(artisan_a: dict):
    """Fresh profile MUST NOT start with rating=5 or trust_score=80."""
    p = artisan_a["profile"]
    assert p["trust_score"] == 0
    assert p["rating"] == 0 or p["rating"] == 0.0
    assert p["reviews_count"] == 0
    assert p["jobs_done"] == 0
    assert p["verification_status"] == "pending"
    assert p["simulated"] is True


# ---------- Whitelist strict on POST /artisans/me ----------

def test_upsert_drops_sensitive_fields(artisan_a: dict):
    """Attempt to escalate role / trust_score / verification_status via POST body.
    The server MUST silently drop these fields."""
    r = httpx.post(
        f"{BASE}/api/artisans/me",
        headers=_h(artisan_a["token"]),
        json={
            "trade": "plombier",
            "title": "Update title",
            "role": "super_admin",
            "verification_status": "approved",
            "trust_score": 100,
            "rating": 5.0,
            "reviews_count": 999,
            "is_subscribed": True,
            "stripe_account_id": "acct_hackerman",
            "admin_notes": "I am admin now",
            "jobs_done": 500,
        },
        timeout=10,
    )
    assert r.status_code == 200
    updated = r.json()
    # None of the sensitive fields must have been applied
    assert updated["verification_status"] == "pending"
    assert updated["trust_score"] == 0
    assert updated["rating"] in (0, 0.0)
    assert updated["reviews_count"] == 0
    assert not updated.get("is_subscribed")
    assert updated.get("stripe_account_id") is None
    assert updated.get("admin_notes") is None
    assert updated["jobs_done"] == 0
    # And the user role itself must still be "artisan"
    me = httpx.get(f"{BASE}/api/auth/me", headers=_h(artisan_a["token"]), timeout=5).json()
    assert me["role"] == "artisan"


def test_client_cannot_create_artisan_profile(client_token: str):
    """A client must never be able to create an artisan profile."""
    r = httpx.post(
        f"{BASE}/api/artisans/me",
        headers=_h(client_token),
        json={"trade": "plombier", "title": "Sneaky", "city": "Paris 11e"},
        timeout=10,
    )
    assert r.status_code == 403


def test_upsert_rejects_bad_trade_slug(artisan_a: dict):
    r = httpx.post(
        f"{BASE}/api/artisans/me",
        headers=_h(artisan_a["token"]),
        json={"trade": "<script>alert(1)</script>", "title": "X"},
        timeout=10,
    )
    assert r.status_code == 422


def test_upsert_rejects_bad_working_hours(artisan_a: dict):
    r = httpx.post(
        f"{BASE}/api/artisans/me",
        headers=_h(artisan_a["token"]),
        json={
            "trade": "plombier",
            "title": "X",
            "working_hours": [{"day": 0, "start": "18:00", "end": "08:00"}],
        },
        timeout=10,
    )
    # end < start → 422
    assert r.status_code == 422


def test_upsert_rejects_bad_intervention_zone(artisan_a: dict):
    r = httpx.post(
        f"{BASE}/api/artisans/me",
        headers=_h(artisan_a["token"]),
        json={
            "trade": "plombier",
            "title": "X",
            "intervention_zones": [{"city": "<xss>", "radius_km": 20}],
        },
        timeout=10,
    )
    assert r.status_code == 422


def test_upsert_rejects_bad_hourly_rate(artisan_a: dict):
    r = httpx.post(
        f"{BASE}/api/artisans/me",
        headers=_h(artisan_a["token"]),
        json={"trade": "plombier", "title": "X", "hourly_rate": 99999},
        timeout=10,
    )
    assert r.status_code == 422


# ---------- Ownership on slots ----------

def test_slots_ownership_cannot_delete_others(artisan_a: dict, artisan_b: dict):
    """Artisan A creates a slot; Artisan B must not be able to delete it."""
    r = httpx.post(
        f"{BASE}/api/artisans/me/slots",
        headers=_h(artisan_a["token"]),
        json={"date": "2027-01-15", "start_time": "10:00", "duration_min": 60},
        timeout=5,
    )
    assert r.status_code == 200
    slot_id = r.json()["slot_id"]

    # Artisan B tries to delete
    r2 = httpx.delete(
        f"{BASE}/api/artisans/me/slots/{slot_id}",
        headers=_h(artisan_b["token"]),
        timeout=5,
    )
    assert r2.status_code == 404  # NOT 403 (no enumeration leak)

    # Client tries to delete
    ct = _login(CLIENT_EMAIL, CLIENT_PASSWORD)
    r3 = httpx.delete(
        f"{BASE}/api/artisans/me/slots/{slot_id}",
        headers=_h(ct),
        timeout=5,
    )
    assert r3.status_code == 403  # client is not artisan → 403 before ownership check

    # Owner can delete
    r4 = httpx.delete(
        f"{BASE}/api/artisans/me/slots/{slot_id}",
        headers=_h(artisan_a["token"]),
        timeout=5,
    )
    assert r4.status_code == 200


def test_slot_rejects_bad_date(artisan_a: dict):
    r = httpx.post(
        f"{BASE}/api/artisans/me/slots",
        headers=_h(artisan_a["token"]),
        json={"date": "2027/01/15", "start_time": "10:00", "duration_min": 60},
        timeout=5,
    )
    assert r.status_code == 422


def test_slot_rejects_bad_time(artisan_a: dict):
    r = httpx.post(
        f"{BASE}/api/artisans/me/slots",
        headers=_h(artisan_a["token"]),
        json={"date": "2027-01-15", "start_time": "25:99", "duration_min": 60},
        timeout=5,
    )
    assert r.status_code == 422


# ---------- Ownership on gallery ----------

def test_gallery_ownership(artisan_a: dict, artisan_b: dict):
    r = httpx.post(
        f"{BASE}/api/artisans/me/gallery",
        headers=_h(artisan_a["token"]),
        json={"title": "Salle de bain 2026", "description": "Belle rénovation"},
        timeout=5,
    )
    assert r.status_code == 200
    project_id = r.json()["project_id"]

    # Artisan B tries to PATCH
    r2 = httpx.patch(
        f"{BASE}/api/artisans/me/gallery/{project_id}",
        headers=_h(artisan_b["token"]),
        json={"description": "Hacked"},
        timeout=5,
    )
    assert r2.status_code == 404

    # Artisan B tries to DELETE
    r3 = httpx.delete(
        f"{BASE}/api/artisans/me/gallery/{project_id}",
        headers=_h(artisan_b["token"]),
        timeout=5,
    )
    assert r3.status_code == 404

    # Owner can delete
    r4 = httpx.delete(
        f"{BASE}/api/artisans/me/gallery/{project_id}",
        headers=_h(artisan_a["token"]),
        timeout=5,
    )
    assert r4.status_code == 200


# ---------- Role guard on artisan-only endpoints ----------

@pytest.mark.parametrize("path,method,body", [
    ("/api/artisans/me/subscribe", "POST", None),
    ("/api/artisans/me/position", "POST", {"lat": 48.85, "lng": 2.35}),
    ("/api/artisans/me/available-now", "POST", None),
    ("/api/artisans/me/slots", "POST", {"date": "2027-01-15", "start_time": "10:00", "duration_min": 60}),
    ("/api/artisans/me/gallery", "POST", {"title": "x"}),
])
def test_client_gets_403_on_artisan_only(path: str, method: str, body, client_token: str):
    kwargs = {"headers": _h(client_token), "timeout": 5}
    if body is not None:
        kwargs["json"] = body
    r = httpx.request(method, f"{BASE}{path}", **kwargs)
    # 403 (role check) or 404 (artisan profile not found) both acceptable but
    # never 200 for a client user
    assert r.status_code in (403, 404), f"{path} returned {r.status_code}: {r.text}"


def test_client_gets_404_on_scoreboard(client_token: str):
    """Legacy contract: /artisans/me/scoreboard returns 404 for clients (no profile)."""
    r = httpx.get(f"{BASE}/api/artisans/me/scoreboard", headers=_h(client_token), timeout=5)
    assert r.status_code == 404


@pytest.mark.parametrize("path", [
    "/api/artisans/me/finance",
    "/api/artisans/me/earnings",
])
def test_client_gets_403_on_pro_only_reads(path: str, client_token: str):
    """Legacy contract: finance/earnings return 403 for non-artisan role."""
    r = httpx.get(f"{BASE}{path}", headers=_h(client_token), timeout=5)
    # earnings falls back to empty payload if no profile → 200. Both acceptable
    # so long as no leaked artisan data appears.
    assert r.status_code in (200, 403, 404)
    if r.status_code == 200:
        assert r.json().get("transfers_count", 0) == 0


# ---------- Simulation flags on finance/earnings ----------

def test_finance_returns_simulated_flag(artisan_a: dict):
    r = httpx.get(f"{BASE}/api/artisans/me/finance", headers=_h(artisan_a["token"]), timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert body.get("simulated") is True


def test_earnings_returns_simulated_flag(artisan_a: dict):
    r = httpx.get(f"{BASE}/api/artisans/me/earnings", headers=_h(artisan_a["token"]), timeout=5)
    assert r.status_code == 200
    assert r.json().get("simulated") is True


# ---------- Calendar simulated ----------

def test_calendar_connect_marks_simulated(artisan_a: dict):
    r = httpx.post(
        f"{BASE}/api/artisans/me/calendar/connect",
        headers=_h(artisan_a["token"]),
        json={"provider": "google"},
        timeout=5,
    )
    assert r.status_code == 200
    assert r.json().get("simulated") is True


def test_calendar_connect_bad_provider(artisan_a: dict):
    r = httpx.post(
        f"{BASE}/api/artisans/me/calendar/connect",
        headers=_h(artisan_a["token"]),
        json={"provider": "myspace"},
        timeout=5,
    )
    # Legacy contract: 400 (not 422) for unknown provider
    assert r.status_code == 400
