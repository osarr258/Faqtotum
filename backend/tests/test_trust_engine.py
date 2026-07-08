"""Trust Engine backend tests — Sprint 8."""
import os
import pytest
import requests
from services import trust_engine

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://reviens-app.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CLIENT = {"email": "client.test@auxora.fr", "password": "Test1234!"}
PRO = {"email": "pro.test@auxora.fr", "password": "Test1234!"}


# -------------------- fixtures --------------------
@pytest.fixture(scope="session")
def s():
    return requests.Session()


def _login(s, creds):
    r = s.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def client_token(s):
    return _login(s, CLIENT)


@pytest.fixture(scope="session")
def pro_token(s):
    return _login(s, PRO)


@pytest.fixture(scope="session")
def seed_artisan_id(s):
    r = s.get(f"{API}/artisans", params={"category": "plombier"}, timeout=15)
    assert r.status_code == 200
    arr = r.json()
    assert len(arr) >= 1
    # Prefer top-rated for badge/premium tests
    arr.sort(key=lambda a: a.get("rating", 0), reverse=True)
    return arr[0]["artisan_id"]


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


# -------------------- Unit: engine invariants --------------------
class TestEngineInvariants:
    def test_weights_sum_to_100(self):
        assert abs(sum(trust_engine.WEIGHTS.values()) - 100.0) < 0.01

    def test_all_20_factors_present(self):
        assert len(trust_engine.WEIGHTS) == 20
        assert len(trust_engine.FEATURES) == 20
        assert set(trust_engine.WEIGHTS.keys()) == set(trust_engine.FEATURES.keys())

    def test_compute_shape_and_bounds(self):
        a = {"rating": 4.9, "reviews_count": 128, "jobs_done": 128,
             "acceptance_rate": 95, "completion_rate": 98, "response_min": 10,
             "identity_verified": True, "insurance_verified": True, "business_registered": True,
             "years_experience": 10, "punctuality_rate": 98, "satisfaction_rate": 96,
             "cancellation_rate": 1, "avg_arrival_min": 25, "emergency_capable": True,
             "background_checked": True, "member_since": "2022-01-01T00:00:00+00:00",
             "last_active_at": "2026-01-01T00:00:00+00:00"}
        out = trust_engine.compute(a)
        assert isinstance(out["trust_score"], int)
        assert 0 <= out["trust_score"] <= 100
        assert set(out["breakdown"].keys()) == set(trust_engine.WEIGHTS.keys())
        assert set(out["contributions"].keys()) == set(trust_engine.WEIGHTS.keys())
        for v in out["breakdown"].values():
            assert 0.0 <= v <= 1.0
        assert "penalties_applied" in out
        assert out["confidence_level"] in ("excellent", "strong", "solid", "developing")
        assert "computed_at" in out

    def test_deterministic(self):
        a = {"rating": 4.7, "jobs_done": 50, "response_min": 12}
        o1 = trust_engine.compute(a)
        o2 = trust_engine.compute(a)
        assert o1["trust_score"] == o2["trust_score"]
        assert o1["breakdown"] == o2["breakdown"]
        assert o1["contributions"] == o2["contributions"]

    def test_invalid_severity_ignored_in_helper(self):
        # helper falls back to minor for unknown severity
        p = trust_engine.dispute_penalty("bogus")
        assert p["severity"] == "bogus"
        # but score_delta must equal minor
        assert p["score_delta"] == trust_engine.DISPUTE_SEVERITY["minor"]["score_delta"]


# -------------------- API: trust endpoints --------------------
class TestTrustEndpoints:
    def test_get_trust(self, s, seed_artisan_id):
        r = s.get(f"{API}/artisans/{seed_artisan_id}/trust", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert 0 <= d["trust_score"] <= 100
        assert len(d["breakdown"]) == 20
        assert d["artisan_id"] == seed_artisan_id
        assert d["confidence_level"] in ("excellent", "strong", "solid", "developing")

    def test_trust_404(self, s):
        r = s.get(f"{API}/artisans/art_does_not_exist/trust", timeout=10)
        assert r.status_code == 404

    def test_confidence_card(self, s, seed_artisan_id):
        r = s.get(f"{API}/artisans/{seed_artisan_id}/confidence-card", timeout=10)
        assert r.status_code == 200
        d = r.json()
        for k in ["verified", "insured", "business_registered", "background_checked",
                  "avg_response_min", "avg_arrival_min", "completion_rate", "satisfaction_rate",
                  "jobs_done", "years_experience", "emergency_capable", "reasons", "badges"]:
            assert k in d, f"missing key {k}"
        assert isinstance(d["reasons"], list) and len(d["reasons"]) >= 1
        assert isinstance(d["badges"], list)
        # client-safe — should NOT expose raw contributions/breakdown
        assert "contributions" not in d
        assert "breakdown" not in d

    def test_badges_top_rated_gold(self, s, seed_artisan_id):
        # Pick the highest rated seed (>=4.8) -> should include top_rated gold
        r = s.get(f"{API}/artisans/{seed_artisan_id}", timeout=10)
        assert r.status_code == 200
        rating = r.json().get("rating", 0)
        rb = s.get(f"{API}/artisans/{seed_artisan_id}/badges", timeout=10).json()
        badges = rb["badges"]
        keys = {b["key"] for b in badges}
        if rating >= 4.8:
            assert "top_rated" in keys
            top = next(b for b in badges if b["key"] == "top_rated")
            assert top["tier"] == "gold"

    def test_badges_jobs_tiers_exclusive(self):
        # bronze/silver/gold/platinum are mutually exclusive
        for jobs, expected in [(30, "jobs_bronze"), (150, "jobs_silver"),
                               (600, "jobs_gold"), (1500, "jobs_platinum")]:
            a = {"rating": 4.5, "jobs_done": jobs, "identity_verified": True,
                 "insurance_verified": True}
            keys = {b["key"] for b in trust_engine.badges(a, 80)}
            tier_keys = keys & {"jobs_bronze", "jobs_silver", "jobs_gold", "jobs_platinum"}
            assert tier_keys == {expected}, f"jobs={jobs} got {tier_keys}"

    def test_artisan_get_enriched(self, s, seed_artisan_id):
        r = s.get(f"{API}/artisans/{seed_artisan_id}", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "trust_score" in d and "badges" in d and "confidence_card" in d

    def test_recompute_trust_idempotent(self, s, seed_artisan_id, client_token):
        r1 = s.post(f"{API}/artisans/{seed_artisan_id}/recompute-trust",
                    headers=h(client_token), timeout=10).json()
        r2 = s.post(f"{API}/artisans/{seed_artisan_id}/recompute-trust",
                    headers=h(client_token), timeout=10).json()
        assert r1["trust_score"] == r2["trust_score"]
        assert r1["breakdown"] == r2["breakdown"]

    def test_recompute_404(self, s, client_token):
        r = s.post(f"{API}/artisans/art_missing/recompute-trust", headers=h(client_token), timeout=10)
        assert r.status_code == 404


# -------------------- API: scoreboard (artisan only) --------------------
class TestScoreboard:
    def test_scoreboard_pro(self, s, pro_token):
        r = s.get(f"{API}/artisans/me/scoreboard", headers=h(pro_token), timeout=10)
        assert r.status_code == 200
        d = r.json()
        for k in ["trust_score", "confidence_level", "penalties", "strengths",
                  "improvements", "badges"]:
            assert k in d
        assert len(d["strengths"]) <= 5
        assert len(d["improvements"]) <= 5
        for imp in d["improvements"]:
            assert {"factor", "label", "current", "potential_pts", "recommendation"} <= set(imp)

    def test_scoreboard_client_404(self, s, client_token):
        r = s.get(f"{API}/artisans/me/scoreboard", headers=h(client_token), timeout=10)
        assert r.status_code == 404


# -------------------- API: disputes --------------------
class TestDisputes:
    def test_invalid_severity_400(self, s, client_token, seed_artisan_id):
        r = s.post(f"{API}/disputes",
                   headers=h(client_token),
                   json={"artisan_id": seed_artisan_id, "reason": "TEST_bogus", "severity": "bogus"},
                   timeout=10)
        assert r.status_code == 400

    def test_minor_dispute_bumps_resolved(self, s, client_token, seed_artisan_id):
        before = s.get(f"{API}/artisans/{seed_artisan_id}", timeout=10).json()
        before_res = before.get("disputes_resolved", 0) or 0
        r = s.post(f"{API}/disputes",
                   headers=h(client_token),
                   json={"artisan_id": seed_artisan_id, "reason": "TEST_minor", "severity": "minor"},
                   timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["dispute"]["status"] == "auto_penalized"
        assert d["dispute"]["requires_manual_review"] is False
        after = s.get(f"{API}/artisans/{seed_artisan_id}", timeout=10).json()
        assert (after.get("disputes_resolved", 0) or 0) == before_res + 1

    def test_severe_dispute_manual_review_no_ban(self, s, client_token, seed_artisan_id):
        r = s.post(f"{API}/disputes",
                   headers=h(client_token),
                   json={"artisan_id": seed_artisan_id, "reason": "TEST_severe", "severity": "severe",
                         "description": "Grave"},
                   timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["dispute"]["requires_manual_review"] is True
        assert d["dispute"]["status"] == "open"
        # Never auto-ban: artisan still returned by GET
        a = s.get(f"{API}/artisans/{seed_artisan_id}", timeout=10)
        assert a.status_code == 200

    def test_moderate_lowers_score(self, s, client_token, seed_artisan_id):
        before = s.get(f"{API}/artisans/{seed_artisan_id}/trust", timeout=10).json()["trust_score"]
        r = s.post(f"{API}/disputes",
                   headers=h(client_token),
                   json={"artisan_id": seed_artisan_id, "reason": "TEST_moderate", "severity": "moderate"},
                   timeout=10)
        assert r.status_code == 200
        after = s.get(f"{API}/artisans/{seed_artisan_id}/trust", timeout=10).json()["trust_score"]
        assert after <= before, f"score should not increase: {before}->{after}"

    def test_disputes_mine_client(self, s, client_token):
        r = s.get(f"{API}/disputes/mine", headers=h(client_token), timeout=10)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        # We created some earlier
        assert any(row.get("reason", "").startswith("TEST_") for row in rows)

    def test_disputes_mine_artisan(self, s, pro_token):
        r = s.get(f"{API}/disputes/mine", headers=h(pro_token), timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# -------------------- API: smart recos --------------------
class TestSmartRecos:
    def test_smart_alternatives(self, s, client_token, seed_artisan_id):
        r = s.post(f"{API}/matching/smart-recommendations",
                   headers=h(client_token),
                   json={"picked_artisan_id": seed_artisan_id, "trade": "plombier"},
                   timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "alternatives" in d
        assert isinstance(d["alternatives"], list)
        allowed_keys = {"higher_rated", "faster", "closer", "cheaper", "earlier_slot"}
        for alt in d["alternatives"]:
            assert alt["key"] in allowed_keys
            assert alt["artisan_id"] != seed_artisan_id
        assert len(d["alternatives"]) <= 5


# -------------------- Startup persistence --------------------
class TestStartupPersistence:
    def test_all_seeds_have_trust_persisted(self, s):
        r = s.get(f"{API}/artisans", timeout=15)
        assert r.status_code == 200
        arr = r.json()
        assert len(arr) >= 12
        for a in arr:
            assert isinstance(a.get("trust_score"), int)
            assert 0 <= a["trust_score"] <= 100
            for k in ["identity_verified", "insurance_verified", "business_registered",
                      "years_experience", "avg_arrival_min", "punctuality_rate",
                      "satisfaction_rate", "member_since", "last_active_at",
                      "disputes_unresolved", "disputes_resolved", "emergency_capable"]:
                assert k in a, f"backfill missing {k} on {a.get('artisan_id')}"
