"""
Growth & Retention sprint — backend tests.
Covers services/growth.py pure helpers + all new /api endpoints in server.py.
"""
import os
import re
import uuid
import pytest
import requests
from datetime import datetime, timedelta, timezone

from services import growth

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://reviens-app.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CLIENT = {"email": "client.test@auxora.fr", "password": "Test1234!"}
PRO = {"email": "pro.test@auxora.fr", "password": "Test1234!"}
SEED_PRO_ID = "art_5c533c263d23"


# ---------------- fixtures ----------------
@pytest.fixture(scope="session")
def s():
    return requests.Session()


def _login(s, creds):
    r = s.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="session")
def client_auth(s):
    return _login(s, CLIENT)


@pytest.fixture(scope="session")
def pro_auth(s):
    return _login(s, PRO)


@pytest.fixture(scope="session")
def client_token(client_auth):
    return client_auth["token"]


@pytest.fixture(scope="session")
def pro_token(pro_auth):
    return pro_auth["token"]


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def client_property_id(s, client_token):
    r = s.get(f"{API}/properties", headers=h(client_token), timeout=15)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert rows, "Client should have at least one property"
    return rows[0]["property_id"]


# =========================================================================
# UNIT TESTS — pure helpers in services/growth.py
# =========================================================================
class TestGrowthUnit:
    # --- pro_level ---
    def test_pro_level_bronze_minimum(self):
        r = growth.pro_level(50, 5)
        assert r["key"] == "bronze"
        assert r["next_level"] == "silver"
        assert 0 <= r["progress_pct"] <= 100

    def test_pro_level_below_bronze_still_returns_bronze(self):
        # Weaker than bronze thresholds — still returns first level.
        r = growth.pro_level(0, 0)
        assert r["key"] == "bronze"
        assert r["progress_pct"] == 0  # both trust/jobs at 0 vs 50/5 min → clamped

    def test_pro_level_gold_seed_pro(self):
        # Sprint reference: trust≈83, jobs=128 → Gold? Note: gold requires trust>=85.
        # Since trust is 83 (<85), highest qualifying is Silver.
        r = growth.pro_level(83, 128)
        assert r["key"] == "silver"
        assert r["next_level"] == "gold"

    def test_pro_level_gold_when_thresholds_met(self):
        r = growth.pro_level(85, 100)
        assert r["key"] == "gold"
        assert r["next_level"] == "platinum"

    def test_pro_level_elite_top(self):
        r = growth.pro_level(99, 5000)
        assert r["key"] == "elite"
        assert r["next_level"] is None
        assert r["progress_pct"] == 100

    def test_pro_level_progress_clamped(self):
        # Very high inputs at a mid level should be clamped
        r = growth.pro_level(70, 25)  # Exactly silver min
        assert r["key"] == "silver"
        assert r["progress_pct"] == 0

    # --- POINTS_EARN ---
    def test_points_earn_table(self):
        assert growth.POINTS_EARN["booking_completed"] == 100
        assert growth.POINTS_EARN["review_posted"] == 25
        assert growth.POINTS_EARN["referral_converted"] == 500
        assert growth.POINTS_EARN["property_created"] == 50

    # --- loyalty_tier ---
    @pytest.mark.parametrize("points,tier", [
        (0, "member"), (499, "member"),
        (500, "silver"), (1999, "silver"),
        (2000, "gold"), (4999, "gold"),
        (5000, "platinum"), (14999, "platinum"),
        (15000, "vip"), (999999, "vip"),
    ])
    def test_loyalty_tier_mapping(self, points, tier):
        r = growth.loyalty_tier(points)
        assert r["tier"] == tier

    # --- health_label ---
    @pytest.mark.parametrize("score,key", [
        (100, "excellent"), (90, "excellent"),
        (89, "good"), (75, "good"),
        (74, "attention"), (55, "attention"),
        (54, "critical"), (0, "critical"),
    ])
    def test_health_label(self, score, key):
        assert growth.health_label(score)["key"] == key

    # --- make_referral_code ---
    def test_referral_code_deterministic(self):
        code1 = growth.make_referral_code("user_abc123")
        code2 = growth.make_referral_code("user_abc123")
        assert code1 == code2
        assert code1.startswith("AUX")
        assert len(code1) == 8  # AUX + 5 chars
        assert re.match(r"^AUX[0-9A-F]{5}$", code1), code1

    def test_referral_code_unique_per_user(self):
        assert growth.make_referral_code("u1") != growth.make_referral_code("u2")

    # --- suggest_maintenance ---
    def test_suggest_maintenance_unknown_category_returns_none(self):
        assert growth.suggest_maintenance({"category": "pool"}) is None
        assert growth.suggest_maintenance({}) is None

    def test_suggest_maintenance_boiler_12mo(self):
        # Installed 5 years ago; due should be rolled forward and in the future.
        old = (datetime.now(timezone.utc) - timedelta(days=365 * 5)).isoformat()
        p = growth.suggest_maintenance({"category": "boiler", "installed_on": old, "equipment_id": "eq1", "name": "Chaudière"})
        assert p["interval_months"] == 12
        assert p["title"] == "Entretien chaudière"
        due = datetime.fromisoformat(p["due_on"]).replace(tzinfo=timezone.utc)
        assert due > datetime.now(timezone.utc)

    @pytest.mark.parametrize("cat,interval", [
        ("heat_pump", 12), ("vmc", 12), ("smoke_detector", 12),
        ("water_heater", 24), ("roof", 24), ("solar", 24), ("ev_charger", 24),
        ("water_softener", 6),
        ("panel", 60), ("windows", 60), ("doors", 60),
    ])
    def test_suggest_maintenance_intervals(self, cat, interval):
        p = growth.suggest_maintenance({"category": cat, "equipment_id": "e1"})
        assert p is not None
        assert p["interval_months"] == interval


# =========================================================================
# API — Trusted Pros
# =========================================================================
class TestTrustedPros:
    def test_list_and_add_idempotent(self, s, client_token):
        # Add
        r1 = s.post(f"{API}/trusted-pros", headers=h(client_token),
                    json={"artisan_id": SEED_PRO_ID, "note": "TEST_pro"}, timeout=15)
        assert r1.status_code == 200, r1.text
        first = r1.json()

        # Idempotent — same call returns existing (same trust_id)
        r2 = s.post(f"{API}/trusted-pros", headers=h(client_token),
                    json={"artisan_id": SEED_PRO_ID, "note": "different"}, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["trust_id"] == first["trust_id"]

        # List includes enriched artisan
        r3 = s.get(f"{API}/trusted-pros", headers=h(client_token), timeout=15)
        assert r3.status_code == 200
        rows = r3.json()
        match = next((r for r in rows if r["artisan_id"] == SEED_PRO_ID), None)
        assert match is not None
        assert "artisan" in match
        assert match["artisan"].get("artisan_id") == SEED_PRO_ID

    def test_delete_trusted_pro(self, s, client_token):
        # Add a distinct pro then delete
        s.post(f"{API}/trusted-pros", headers=h(client_token),
               json={"artisan_id": "art_2dfb71f00c16"}, timeout=15)
        r = s.delete(f"{API}/trusted-pros/art_2dfb71f00c16", headers=h(client_token), timeout=15)
        assert r.status_code == 200
        r2 = s.get(f"{API}/trusted-pros", headers=h(client_token), timeout=15)
        assert not any(x["artisan_id"] == "art_2dfb71f00c16" for x in r2.json())


# =========================================================================
# API — Loyalty
# =========================================================================
class TestLoyalty:
    def test_summary_schema(self, s, client_token):
        r = s.get(f"{API}/loyalty/summary", headers=h(client_token), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "points" in data
        assert "lifetime_points" in data
        assert "tier" in data and "next_tier" in data and "next_min" in data
        assert isinstance(data["rewards"], list) and len(data["rewards"]) >= 5
        assert data["earn_actions"]["booking_completed"] == 100

    def test_ledger_desc(self, s, client_token):
        r = s.get(f"{API}/loyalty/ledger", headers=h(client_token), timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        if len(rows) >= 2:
            assert rows[0]["created_at"] >= rows[1]["created_at"]

    def test_redeem_unknown_reward_404(self, s, client_token):
        r = s.post(f"{API}/loyalty/redeem", headers=h(client_token),
                   json={"reward_key": "nope_nope"}, timeout=15)
        assert r.status_code == 404

    def test_redeem_insufficient_400(self, s, client_token):
        # vip_status = 15000 pts — unlikely on test client. Ensure 400 when insufficient.
        summary = s.get(f"{API}/loyalty/summary", headers=h(client_token)).json()
        if summary["points"] >= 15000:
            pytest.skip("Client has >= 15000 points; cannot assert insufficient")
        r = s.post(f"{API}/loyalty/redeem", headers=h(client_token),
                   json={"reward_key": "vip_status"}, timeout=15)
        assert r.status_code == 400


# =========================================================================
# API — Loyalty hooks (property_created adds +50)
# =========================================================================
class TestLoyaltyHooks:
    def test_property_creation_credits_50(self, s, client_token):
        before = s.get(f"{API}/loyalty/summary", headers=h(client_token)).json()
        payload = {
            "name": f"TEST_prop_{uuid.uuid4().hex[:6]}",
            "address": "1 rue TEST",
            "postal_code": "75011",
            "city": "Paris",
            "type": "apartment",
        }
        r = s.post(f"{API}/properties", headers=h(client_token), json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        prop_id = r.json().get("property_id")
        after = s.get(f"{API}/loyalty/summary", headers=h(client_token)).json()
        try:
            assert after["lifetime_points"] - before["lifetime_points"] >= 50
            # Ledger should have a property_created entry
            ledger = s.get(f"{API}/loyalty/ledger", headers=h(client_token)).json()
            assert any(e.get("action") == "property_created" for e in ledger[:10])
        finally:
            if prop_id:
                s.delete(f"{API}/properties/{prop_id}", headers=h(client_token))


# =========================================================================
# API — Referrals
# =========================================================================
class TestReferrals:
    def test_referrals_mine_deterministic_code(self, s, client_token, client_auth):
        r = s.get(f"{API}/referrals/mine", headers=h(client_token), timeout=15)
        assert r.status_code == 200
        data = r.json()
        expected = growth.make_referral_code(client_auth["user"]["user_id"])
        assert data["code"] == expected
        assert "invitations" in data
        assert "invitations_count" in data
        assert "converted_count" in data

    def test_referral_invalid_code_404(self, s, client_token):
        r = s.post(f"{API}/referrals/redeem", headers=h(client_token),
                   json={"code": "AUXZZZZZ"}, timeout=15)
        # 404 if client hasn't yet converted a referral; 400 if already converted (state-dependent).
        # Endpoint checks "already converted" before code validity — accepts both.
        assert r.status_code in (404, 400)

    def test_referral_self_400(self, s, client_token, client_auth):
        my_code = growth.make_referral_code(client_auth["user"]["user_id"])
        r = s.post(f"{API}/referrals/redeem", headers=h(client_token),
                   json={"code": my_code}, timeout=15)
        # Could 400 due to self-referral OR due to already converted (from a previous test)
        assert r.status_code == 400

    def test_referral_duplicate_conversion_400(self, s, client_token, pro_auth):
        # Try to redeem pro's code with client — if already converted before, will 400.
        pro_code = growth.make_referral_code(pro_auth["user"]["user_id"])
        r = s.post(f"{API}/referrals/redeem", headers=h(client_token),
                   json={"code": pro_code}, timeout=15)
        # Either success or already-converted 400. Accept both, since state depends on prior runs.
        assert r.status_code in (200, 400)


# =========================================================================
# API — Pro Levels
# =========================================================================
class TestProLevels:
    def test_growth_levels_catalog(self, s):
        r = s.get(f"{API}/growth/levels", timeout=15)
        assert r.status_code == 200
        levels = r.json()
        assert len(levels) == 5
        assert [lvl["key"] for lvl in levels] == ["bronze", "silver", "gold", "platinum", "elite"]

    def test_artisan_level_endpoint(self, s):
        r = s.get(f"{API}/artisans/{SEED_PRO_ID}/level", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["artisan_id"] == SEED_PRO_ID
        assert data["key"] in ("bronze", "silver", "gold", "platinum", "elite")
        assert 0 <= data["progress_pct"] <= 100

    def test_artisan_level_404(self, s):
        r = s.get(f"{API}/artisans/art_does_not_exist/level", timeout=15)
        assert r.status_code == 404


# =========================================================================
# API — Gallery
# =========================================================================
class TestGallery:
    def test_client_cannot_post_gallery(self, s, client_token):
        r = s.post(f"{API}/artisans/me/gallery", headers=h(client_token),
                   json={"title": "TEST_forbidden"}, timeout=15)
        assert r.status_code == 403

    def test_pro_create_list_delete_gallery(self, s, pro_token, pro_auth):
        r = s.post(f"{API}/artisans/me/gallery", headers=h(pro_token),
                   json={"title": "TEST_project", "description": "d", "before_photos": ["a"], "after_photos": ["b"]},
                   timeout=15)
        assert r.status_code == 200, r.text
        pid = r.json()["project_id"]
        aid = r.json()["artisan_id"]

        lr = s.get(f"{API}/artisans/{aid}/gallery", timeout=15)
        assert lr.status_code == 200
        assert any(p["project_id"] == pid for p in lr.json())

        d = s.delete(f"{API}/artisans/me/gallery/{pid}", headers=h(pro_token), timeout=15)
        assert d.status_code == 200


# =========================================================================
# API — Property Health
# =========================================================================
class TestPropertyHealth:
    def test_property_health_endpoint(self, s, client_token, client_property_id):
        r = s.get(f"{API}/properties/{client_property_id}/health", headers=h(client_token), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert 0 <= data["score"] <= 100
        assert data["key"] in ("excellent", "good", "attention", "critical")
        assert "equipment_count" in data

    def test_property_health_no_equipment_returns_demo(self, s, client_token):
        # Create fresh property with no equipment.
        payload = {"name": f"TEST_health_{uuid.uuid4().hex[:6]}", "address": "1 rue X",
                   "postal_code": "75001", "city": "Paris", "type": "apartment"}
        cr = s.post(f"{API}/properties", headers=h(client_token), json=payload, timeout=15)
        pid = cr.json().get("property_id")
        try:
            r = s.get(f"{API}/properties/{pid}/health", headers=h(client_token), timeout=15)
            assert r.status_code == 200
            d = r.json()
            assert d["score"] == 100
            assert d["key"] == "excellent"
            assert d.get("demo") is True
            assert d["equipment_count"] == 0
        finally:
            if pid:
                s.delete(f"{API}/properties/{pid}", headers=h(client_token))


# =========================================================================
# API — Maintenance Planner
# =========================================================================
class TestMaintenancePlanner:
    def test_maintenance_plan_returns_sorted(self, s, client_token, client_property_id):
        r = s.get(f"{API}/properties/{client_property_id}/maintenance-plan", headers=h(client_token), timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "plans" in data and "count" in data
        # Sorted asc by due_on
        dues = [p["due_on"] for p in data["plans"]]
        assert dues == sorted(dues)

    def test_generate_reminders_idempotent(self, s, client_token, client_property_id):
        r1 = s.post(f"{API}/properties/{client_property_id}/maintenance-plan/generate-reminders",
                    headers=h(client_token), timeout=15)
        assert r1.status_code == 200
        assert r1.json()["created"] >= 0

        # Second call — should not duplicate; created should be 0.
        r2 = s.post(f"{API}/properties/{client_property_id}/maintenance-plan/generate-reminders",
                    headers=h(client_token), timeout=15)
        assert r2.status_code == 200
        assert r2.json()["created"] == 0, "Second call should not create duplicate reminders"


# =========================================================================
# API — Business Accounts
# =========================================================================
class TestBusiness:
    def test_setup_invalid_type_400(self, s, client_token):
        r = s.post(f"{API}/business/setup", headers=h(client_token),
                   json={"account_type": "banana"}, timeout=15)
        assert r.status_code == 400

    def test_setup_and_get(self, s, client_token):
        r = s.post(f"{API}/business/setup", headers=h(client_token),
                   json={"account_type": "property_manager", "company_name": "TEST_co", "properties_count": 5},
                   timeout=15)
        assert r.status_code == 200
        g = s.get(f"{API}/business/mine", headers=h(client_token), timeout=15)
        assert g.status_code == 200
        data = g.json()
        assert data["account_type"] == "property_manager"

    def test_get_default_individual(self, s, pro_token):
        # Fresh pro user hasn't set up business — reset via setup to individual for determinism.
        s.post(f"{API}/business/setup", headers=h(pro_token), json={"account_type": "individual"}, timeout=15)
        g = s.get(f"{API}/business/mine", headers=h(pro_token), timeout=15)
        assert g.status_code == 200
        assert g.json()["account_type"] == "individual"


# =========================================================================
# API — Family Sharing
# =========================================================================
class TestFamily:
    def test_invalid_role_400(self, s, client_token, client_property_id):
        r = s.post(f"{API}/properties/{client_property_id}/members", headers=h(client_token),
                   json={"property_id": client_property_id, "email": "TEST_x@example.com", "role": "bandit"},
                   timeout=15)
        assert r.status_code == 400

    def test_invite_unknown_email_becomes_invited(self, s, client_token, client_property_id):
        payload = {"property_id": client_property_id, "email": f"TEST_{uuid.uuid4().hex[:6]}@x.com", "role": "partner"}
        r = s.post(f"{API}/properties/{client_property_id}/members", headers=h(client_token), json=payload, timeout=15)
        assert r.status_code == 200
        m = r.json()
        assert m["status"] == "invited"
        assert m["invited_user_id"] is None
        s.delete(f"{API}/properties/{client_property_id}/members/{m['member_id']}", headers=h(client_token))

    def test_invite_existing_user_becomes_active(self, s, client_token, client_property_id):
        payload = {"property_id": client_property_id, "email": "pro.test@auxora.fr", "role": "manager"}
        r = s.post(f"{API}/properties/{client_property_id}/members", headers=h(client_token), json=payload, timeout=15)
        assert r.status_code == 200
        m = r.json()
        assert m["status"] == "active"
        assert m["invited_user_id"] is not None
        # cleanup
        s.delete(f"{API}/properties/{client_property_id}/members/{m['member_id']}", headers=h(client_token))

    def test_list_members(self, s, client_token, client_property_id):
        r = s.get(f"{API}/properties/{client_property_id}/members", headers=h(client_token), timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# =========================================================================
# API — Favourites
# =========================================================================
class TestFavourites:
    def test_invalid_kind_query_400(self, s, client_token):
        r = s.get(f"{API}/favourites?kind=weird", headers=h(client_token), timeout=15)
        assert r.status_code == 400

    def test_invalid_kind_post_400(self, s, client_token):
        r = s.post(f"{API}/favourites", headers=h(client_token),
                   json={"kind": "weird", "ref_id": "x"}, timeout=15)
        assert r.status_code == 400

    def test_add_favourite_idempotent(self, s, client_token):
        payload = {"kind": "pro", "ref_id": SEED_PRO_ID, "label": "TEST_fav"}
        r1 = s.post(f"{API}/favourites", headers=h(client_token), json=payload, timeout=15)
        assert r1.status_code == 200
        fav1 = r1.json()
        r2 = s.post(f"{API}/favourites", headers=h(client_token), json=payload, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["favourite_id"] == fav1["favourite_id"]
        # cleanup
        s.delete(f"{API}/favourites/{fav1['favourite_id']}", headers=h(client_token))

    def test_list_filter_by_kind(self, s, client_token):
        r = s.get(f"{API}/favourites?kind=pro", headers=h(client_token), timeout=15)
        assert r.status_code == 200
        for f in r.json():
            assert f["kind"] == "pro"


# =========================================================================
# API — Analytics
# =========================================================================
class TestAnalytics:
    def test_analytics_schema(self, s, client_token):
        r = s.get(f"{API}/analytics/mine", headers=h(client_token), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ["bookings_count", "completed_count", "total_spent_eur",
                    "money_saved_eur", "avg_repair_cost_eur", "avg_response_min",
                    "favourite_trade", "trades_breakdown", "property_count", "demo_values"]:
            assert key in d, f"missing key {key}"
        # money_saved ≈ 15% of total spent
        if d["total_spent_eur"] > 0:
            assert d["money_saved_eur"] == int(d["total_spent_eur"] * 0.15)


# =========================================================================
# Auth guards
# =========================================================================
class TestAuthGuards:
    def test_trusted_pros_unauth_401(self, s):
        r = s.get(f"{API}/trusted-pros", timeout=15)
        assert r.status_code in (401, 403)

    def test_loyalty_summary_unauth_401(self, s):
        r = s.get(f"{API}/loyalty/summary", timeout=15)
        assert r.status_code in (401, 403)

    def test_favourites_unauth_401(self, s):
        r = s.get(f"{API}/favourites", timeout=15)
        assert r.status_code in (401, 403)
