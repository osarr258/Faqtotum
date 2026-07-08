"""Pro Hub sprint — backend test suite.

Covers services/pro_hub.py pure module + 17 new endpoints exposed in server.py:
- /pro/dashboard, /pro/profile, /pro/coach, /pro/insights
- /community/feed, /community/posts (+like/bookmark/comments/follow/bookmarks/mine)
- /academy/categories, /academy/cards
- /marketing/modules, /marketing/{key}/interest
- PATCH /artisans/me/gallery/{project_id}
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://reviens-app.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

PRO_EMAIL = "pro.test@auxora.fr"
CLIENT_EMAIL = "client.test@auxora.fr"
PASSWORD = "Test1234!"

# Import the pure module for direct assertions
import sys
sys.path.insert(0, "/app/backend")
from services import pro_hub  # noqa: E402


# --------------------------- fixtures ------------------------------

def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["token"]

@pytest.fixture(scope="session")
def pro_token():
    return _login(PRO_EMAIL, PASSWORD)

@pytest.fixture(scope="session")
def client_token():
    return _login(CLIENT_EMAIL, PASSWORD)

@pytest.fixture(scope="session")
def pro_headers(pro_token):
    return {"Authorization": f"Bearer {pro_token}", "Content-Type": "application/json"}

@pytest.fixture(scope="session")
def client_headers(client_token):
    return {"Authorization": f"Bearer {client_token}", "Content-Type": "application/json"}

@pytest.fixture(scope="session")
def pro_user_id(pro_headers):
    r = requests.get(f"{API}/auth/me", headers=pro_headers, timeout=15)
    assert r.status_code == 200
    return r.json()["user_id"]

@pytest.fixture(scope="session")
def client_user_id(client_headers):
    r = requests.get(f"{API}/auth/me", headers=client_headers, timeout=15)
    assert r.status_code == 200
    return r.json()["user_id"]


# --------------------------- pure module ---------------------------

class TestProHubModule:
    def test_academy_categories_shape(self):
        cats = pro_hub.ACADEMY_CATEGORIES
        assert len(cats) == 7
        for c in cats:
            assert set(c.keys()) >= {"key", "label", "icon"}
            assert c["icon"] and c["label"] and c["key"]

    def test_academy_cards_all_coming_soon(self):
        cards = pro_hub.ACADEMY_CARDS
        assert len(cards) == 7
        assert all(c["status"] == "coming_soon" for c in cards)
        cat_keys = {c["key"] for c in pro_hub.ACADEMY_CATEGORIES}
        assert all(c["category"] in cat_keys for c in cards)

    def test_marketing_modules_count(self):
        assert len(pro_hub.MARKETING_MODULES) == 5
        assert all(m["status"] == "coming_soon" for m in pro_hub.MARKETING_MODULES)

    def test_coach_returns_max_6_sorted_by_impact_desc(self):
        breakdown = {k: 0.3 for k in pro_hub.COACH_RECOMMENDATIONS.keys()}  # all low
        recos = pro_hub.coach_recommendations(breakdown, badges=[], jobs_done=0, trust_score=50)
        assert len(recos) <= 6
        impacts = [r["impact"] for r in recos]
        assert impacts == sorted(impacts, reverse=True), impacts

    def test_coach_adds_milestone_for_next_badge(self):
        recos = pro_hub.coach_recommendations({}, [], jobs_done=10, trust_score=95)
        ms = [r for r in recos if r["key"] == "next_badge"]
        assert len(ms) == 1
        assert ms[0]["target"] == 25 and ms[0]["current"] == 10

    def test_coach_milestone_100(self):
        recos = pro_hub.coach_recommendations({}, [], jobs_done=50, trust_score=95)
        ms = [r for r in recos if r["key"] == "next_badge"]
        assert ms and ms[0]["target"] == 100

    def test_coach_milestone_500(self):
        recos = pro_hub.coach_recommendations({}, [], jobs_done=200, trust_score=95)
        ms = [r for r in recos if r["key"] == "next_badge"]
        assert ms and ms[0]["target"] == 500

    def test_coach_milestone_1000(self):
        recos = pro_hub.coach_recommendations({}, [], jobs_done=800, trust_score=95)
        ms = [r for r in recos if r["key"] == "next_badge"]
        assert ms and ms[0]["target"] == 1000

    def test_coach_no_milestone_beyond_1000(self):
        recos = pro_hub.coach_recommendations({}, [], jobs_done=1500, trust_score=95)
        assert not any(r["key"] == "next_badge" for r in recos)

    def test_coach_adds_trust_90_when_below(self):
        recos = pro_hub.coach_recommendations({}, [], jobs_done=5000, trust_score=80)
        t = [r for r in recos if r["key"] == "trust_90"]
        assert len(t) == 1 and t[0]["target"] == 90 and t[0]["current"] == 80

    def test_coach_omits_trust_90_when_already_high(self):
        recos = pro_hub.coach_recommendations({}, [], jobs_done=5000, trust_score=95)
        assert not any(r["key"] == "trust_90" for r in recos)

    def test_coach_ignores_high_scoring_factors(self):
        breakdown = {k: 0.9 for k in pro_hub.COACH_RECOMMENDATIONS.keys()}
        recos = pro_hub.coach_recommendations(breakdown, [], jobs_done=5000, trust_score=95)
        assert not any(r.get("kind") == "improvement" for r in recos)

    def test_profile_completion_bounds_and_shape(self):
        empty = pro_hub.profile_completion({})
        assert set(empty.keys()) == {"completion_pct", "missing", "checks_count", "checks_ok"}
        assert 0 <= empty["completion_pct"] <= 100
        assert empty["completion_pct"] == 0
        assert empty["checks_count"] == 13
        assert empty["checks_ok"] == 0
        assert len(empty["missing"]) == 13

    def test_profile_completion_full(self):
        full = {
            "logo": "u", "cover": "u", "bio": "hi", "services": ["a"],
            "areas_covered": ["Paris"], "opening_hours": {"mon": "9-18"},
            "certifications": ["Qualibat"], "insurance_verified": True,
            "identity_verified": True, "business_registered": True,
            "languages": ["fr"], "website": "https://x", "hourly_rate": 50,
        }
        r = pro_hub.profile_completion(full)
        assert r["completion_pct"] == 100
        assert r["missing"] == []
        assert r["checks_ok"] == r["checks_count"]


# --------------------------- Pro Dashboard -------------------------

class TestProDashboard:
    def test_dashboard_ok_for_pro(self, pro_headers):
        r = requests.get(f"{API}/pro/dashboard", headers=pro_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        required = {"today_jobs", "upcoming_jobs", "revenue_cents", "monthly_revenue_cents",
                    "growth_pct", "trust_score", "trust_level", "pro_level",
                    "customer_satisfaction", "response_rate", "avg_response_min",
                    "profile_completion", "pending_documents", "unread_messages",
                    "badges", "top_coach_reco"}
        missing = required - set(d.keys())
        assert not missing, f"missing keys: {missing}"
        assert set(d["pro_level"].keys()) >= {"key", "label", "progress_pct"}
        pc = d["profile_completion"]
        assert set(pc.keys()) >= {"completion_pct", "missing", "checks_count", "checks_ok"}
        assert len(d["top_coach_reco"]) <= 3
        assert isinstance(d["badges"], list)

    def test_dashboard_forbidden_for_client(self, client_headers):
        r = requests.get(f"{API}/pro/dashboard", headers=client_headers, timeout=30)
        assert r.status_code == 403


# --------------------------- Pro Profile ---------------------------

class TestProProfileEnrichment:
    def test_patch_profile_enriches_and_computes_completion(self, pro_headers):
        payload = {
            "logo": "https://cdn/x/logo.png",
            "cover": "https://cdn/x/cover.png",
            "services": ["Débouchage", "Détection de fuite"],
            "areas_covered": ["Paris 11", "Paris 20"],
            "opening_hours": {"mon": "9-18", "tue": "9-18"},
            "certifications": ["Qualibat 2026"],
            "languages": ["fr", "en"],
            "website": "https://plombier-paris.fr",
            "social": {"instagram": "@pro_test"},
        }
        r = requests.patch(f"{API}/pro/profile", headers=pro_headers, json=payload, timeout=30)
        assert r.status_code == 200, r.text
        prof = r.json()
        assert prof.get("logo") == payload["logo"]
        assert prof.get("services") == payload["services"]
        assert "profile_completion" in prof
        pc = prof["profile_completion"]
        assert 0 <= pc["completion_pct"] <= 100
        # after enrichment must be substantially higher than baseline (>= 60)
        assert pc["completion_pct"] >= 60

    def test_patch_profile_forbidden_for_client(self, client_headers):
        r = requests.patch(f"{API}/pro/profile", headers=client_headers, json={"logo": "u"}, timeout=15)
        assert r.status_code == 403


# --------------------------- Coach --------------------------------

class TestProCoach:
    def test_coach_endpoint_shape(self, pro_headers):
        r = requests.get(f"{API}/pro/coach", headers=pro_headers, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(d.keys()) >= {"trust_score", "confidence_level", "recommendations", "profile_completion"}
        assert isinstance(d["recommendations"], list)
        assert len(d["recommendations"]) <= 6
        impacts = [x["impact"] for x in d["recommendations"]]
        assert impacts == sorted(impacts, reverse=True)

    def test_coach_forbidden_for_client(self, client_headers):
        r = requests.get(f"{API}/pro/coach", headers=client_headers, timeout=15)
        assert r.status_code == 403


# --------------------------- Insights ------------------------------

class TestProInsights:
    def test_insights_shape(self, pro_headers):
        r = requests.get(f"{API}/pro/insights", headers=pro_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        required = {"revenue_evolution", "customer_growth", "unique_clients",
                    "repeat_clients", "avg_job_value_cents", "acceptance_rate",
                    "cancellation_rate", "completion_rate", "top_cities"}
        assert required.issubset(d.keys()), required - set(d.keys())
        assert isinstance(d["revenue_evolution"], list) and len(d["revenue_evolution"]) <= 12
        assert isinstance(d["top_cities"], list) and len(d["top_cities"]) <= 5

    def test_insights_forbidden_for_client(self, client_headers):
        r = requests.get(f"{API}/pro/insights", headers=client_headers, timeout=15)
        assert r.status_code == 403


# --------------------------- Community -----------------------------

class TestCommunity:
    def test_feed_returns_liked_bookmarked_flags(self, pro_headers):
        r = requests.get(f"{API}/community/feed", headers=pro_headers, timeout=20)
        assert r.status_code == 200
        posts = r.json()
        assert isinstance(posts, list)
        for p in posts:
            assert "liked_by_me" in p and "bookmarked_by_me" in p

    def test_feed_kind_invalid_400(self, pro_headers):
        r = requests.get(f"{API}/community/feed?kind=random", headers=pro_headers, timeout=15)
        assert r.status_code == 400

    def test_feed_kind_valid_ok(self, pro_headers):
        r = requests.get(f"{API}/community/feed?kind=tip", headers=pro_headers, timeout=15)
        assert r.status_code == 200
        assert all(p["kind"] == "tip" for p in r.json())

    def test_client_cannot_create_post(self, client_headers):
        r = requests.post(f"{API}/community/posts", headers=client_headers,
                          json={"kind": "tip", "title": "TEST_x", "body": "y"}, timeout=15)
        assert r.status_code == 403

    def test_create_post_invalid_kind(self, pro_headers):
        r = requests.post(f"{API}/community/posts", headers=pro_headers,
                          json={"kind": "invalid", "title": "TEST_x", "body": "y"}, timeout=15)
        assert r.status_code == 400

    def test_create_post_ok_with_author_enrichment_and_caps(self, pro_headers):
        payload = {
            "kind": "project",
            "title": f"TEST_{uuid.uuid4().hex[:6]}",
            "body": "Rénovation salle de bain complète",
            "photos": [f"p{i}" for i in range(10)],
            "tags":   [f"t{i}" for i in range(10)],
        }
        r = requests.post(f"{API}/community/posts", headers=pro_headers, json=payload, timeout=15)
        assert r.status_code == 200, r.text
        post = r.json()
        assert post["author_name"]
        assert post["author_trade"] is not None
        assert len(post["photos"]) == 6
        assert len(post["tags"]) == 5
        assert post["likes_count"] == 0 and post["comments_count"] == 0

    @pytest.fixture
    def sample_post_id(self, pro_headers):
        r = requests.post(f"{API}/community/posts", headers=pro_headers,
                          json={"kind": "tip", "title": f"TEST_{uuid.uuid4().hex[:6]}", "body": "hello"},
                          timeout=15)
        assert r.status_code == 200
        return r.json()["post_id"]

    def test_like_toggle_idempotent_updates_count(self, pro_headers, sample_post_id):
        # first like
        r1 = requests.post(f"{API}/community/posts/{sample_post_id}/like", headers=pro_headers, timeout=15)
        assert r1.status_code == 200 and r1.json()["liked"] is True
        feed = requests.get(f"{API}/community/feed", headers=pro_headers, timeout=15).json()
        after_like = next(p for p in feed if p["post_id"] == sample_post_id)
        assert after_like["likes_count"] == 1
        assert after_like["liked_by_me"] is True
        # unlike
        r2 = requests.post(f"{API}/community/posts/{sample_post_id}/like", headers=pro_headers, timeout=15)
        assert r2.status_code == 200 and r2.json()["liked"] is False
        feed2 = requests.get(f"{API}/community/feed", headers=pro_headers, timeout=15).json()
        after_unlike = next(p for p in feed2 if p["post_id"] == sample_post_id)
        assert after_unlike["likes_count"] == 0
        assert after_unlike["liked_by_me"] is False

    def test_bookmark_toggle_idempotent(self, pro_headers, sample_post_id):
        r1 = requests.post(f"{API}/community/posts/{sample_post_id}/bookmark", headers=pro_headers, timeout=15)
        assert r1.status_code == 200 and r1.json()["bookmarked"] is True
        mine = requests.get(f"{API}/community/bookmarks/mine", headers=pro_headers, timeout=15).json()
        assert any(p["post_id"] == sample_post_id for p in mine)
        r2 = requests.post(f"{API}/community/posts/{sample_post_id}/bookmark", headers=pro_headers, timeout=15)
        assert r2.status_code == 200 and r2.json()["bookmarked"] is False
        mine2 = requests.get(f"{API}/community/bookmarks/mine", headers=pro_headers, timeout=15).json()
        assert not any(p["post_id"] == sample_post_id for p in mine2)

    def test_comments_increment_count_and_ordered(self, pro_headers, sample_post_id):
        c1 = requests.post(f"{API}/community/posts/{sample_post_id}/comments",
                           headers=pro_headers, json={"body": "TEST_c1"}, timeout=15)
        c2 = requests.post(f"{API}/community/posts/{sample_post_id}/comments",
                           headers=pro_headers, json={"body": "TEST_c2"}, timeout=15)
        assert c1.status_code == 200 and c2.status_code == 200
        listed = requests.get(f"{API}/community/posts/{sample_post_id}/comments",
                              headers=pro_headers, timeout=15).json()
        assert [c["body"] for c in listed[-2:]] == ["TEST_c1", "TEST_c2"]
        feed = requests.get(f"{API}/community/feed", headers=pro_headers, timeout=15).json()
        post = next(p for p in feed if p["post_id"] == sample_post_id)
        assert post["comments_count"] >= 2

    def test_follow_self_400(self, pro_headers, pro_user_id):
        r = requests.post(f"{API}/community/follow/{pro_user_id}", headers=pro_headers, timeout=15)
        assert r.status_code == 400

    def test_follow_toggle_idempotent(self, pro_headers, client_user_id):
        r1 = requests.post(f"{API}/community/follow/{client_user_id}", headers=pro_headers, timeout=15)
        assert r1.status_code == 200
        assert "following" in r1.json()
        first = r1.json()["following"]
        r2 = requests.post(f"{API}/community/follow/{client_user_id}", headers=pro_headers, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["following"] != first


# --------------------------- Academy -------------------------------

class TestAcademy:
    def test_categories_endpoint(self, pro_headers):
        r = requests.get(f"{API}/academy/categories", headers=pro_headers, timeout=15)
        assert r.status_code == 200
        cats = r.json()
        assert len(cats) == 7
        assert all({"key", "label", "icon"} <= set(c.keys()) for c in cats)

    def test_cards_endpoint(self, pro_headers):
        r = requests.get(f"{API}/academy/cards", headers=pro_headers, timeout=15)
        assert r.status_code == 200
        cards = r.json()
        assert len(cards) == 7
        assert all(c["status"] == "coming_soon" for c in cards)

    def test_cards_category_filter(self, pro_headers):
        r = requests.get(f"{API}/academy/cards?category=business", headers=pro_headers, timeout=15)
        assert r.status_code == 200
        cards = r.json()
        assert cards and all(c["category"] == "business" for c in cards)

    def test_cards_unknown_category_empty(self, pro_headers):
        r = requests.get(f"{API}/academy/cards?category=unknown_x", headers=pro_headers, timeout=15)
        assert r.status_code == 200
        assert r.json() == []


# --------------------------- Marketing -----------------------------

class TestMarketing:
    def test_modules_returns_5(self, pro_headers):
        r = requests.get(f"{API}/marketing/modules", headers=pro_headers, timeout=15)
        assert r.status_code == 200
        mods = r.json()
        assert len(mods) == 5
        assert all(m["status"] == "coming_soon" for m in mods)

    def test_interest_unknown_module_400(self, pro_headers):
        r = requests.post(f"{API}/marketing/nonexistent_module/interest", headers=pro_headers, timeout=15)
        assert r.status_code == 400

    def test_interest_upsert_idempotent(self, pro_headers):
        r1 = requests.post(f"{API}/marketing/promotion/interest", headers=pro_headers, timeout=15)
        r2 = requests.post(f"{API}/marketing/promotion/interest", headers=pro_headers, timeout=15)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json().get("status") == "waitlist_registered"


# --------------------------- Gallery patch -------------------------

class TestGalleryPatch:
    def test_patch_gallery_project(self, pro_headers):
        # create a gallery project first
        c = requests.post(f"{API}/artisans/me/gallery", headers=pro_headers,
                          json={"title": f"TEST_{uuid.uuid4().hex[:6]}", "photos": ["u1"]},
                          timeout=20)
        if c.status_code != 200:
            pytest.skip(f"gallery create not available: {c.status_code} {c.text[:200]}")
        pid = c.json().get("project_id")
        assert pid
        payload = {
            "description": "Rénovation complète cuisine",
            "city": "Paris",
            "duration_hours": 12.5,
            "completed_at": "2026-01-05",
            "review_id": "rev_test",
        }
        r = requests.patch(f"{API}/artisans/me/gallery/{pid}", headers=pro_headers,
                           json=payload, timeout=15)
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["description"] == payload["description"]
        assert p["city"] == "Paris"
        assert p["duration_hours"] == 12.5
        assert p["review_id"] == "rev_test"
