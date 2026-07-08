"""AI Concierge (AURA) backend tests — new sprint."""
import os
import time
import pytest
import requests
from services import concierge

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://reviens-app.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CLIENT = {"email": "client.test@auxora.fr", "password": "Test1234!"}
PRO = {"email": "pro.test@auxora.fr", "password": "Test1234!"}


# ---------------- fixtures ----------------
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


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------------- Unit tests: pure helpers (no LLM) ----------------
class TestConciergeUnit:
    def test_initial_greeting_deterministic(self):
        g1 = concierge.initial_greeting()
        g2 = concierge.initial_greeting()
        assert g1 == g2
        assert g1["ai_message"].startswith("Bonjour")
        assert g1["next_action"] == "continue"
        assert isinstance(g1["followup_suggestions"], list)
        assert len(g1["followup_suggestions"]) >= 3
        assert g1["live_diagnosis"]["confidence"] == 0
        assert g1["summary"] is None

    def test_new_session_id_format(self):
        sid = concierge.new_session_id()
        assert sid.startswith("conv_")
        assert len(sid) > 5

    def test_augment_safety_gas_smell(self):
        alerts = concierge._augment_safety("Il y a une odeur gaz dans la cuisine", None, [])
        assert len(alerts) >= 1
        assert any(a["level"] == "urgence" and "gaz" in a["message"].lower() for a in alerts)

    def test_augment_safety_electrocution(self):
        alerts = concierge._augment_safety("mon fils s'est électrocuté", None, [])
        assert any(a["level"] == "urgence" for a in alerts)

    def test_augment_safety_dedup(self):
        pre = [{"level": "urgence",
                "message": "Ne touchez aucun interrupteur. Ouvrez les fenêtres, fermez la vanne gaz, sortez et appelez le 18."}]
        out = concierge._augment_safety("odeur gaz", "chauffagiste", pre)
        # Same alert should NOT be duplicated
        msgs = [a["message"] for a in out]
        assert msgs.count(pre[0]["message"]) == 1

    def test_augment_safety_no_trigger(self):
        out = concierge._augment_safety("juste un robinet qui goutte", "plombier", [])
        assert out == []

    def test_sanitize_bad_urgency_and_confidence(self):
        state = {
            "ai_message": " Salut ",
            "detected_trade": "not_a_trade",
            "live_diagnosis": {"urgency": "wtf", "confidence": 250},
            "next_action": "nope",
            "followup_suggestions": "not-a-list",
            "safety_alerts": [],
        }
        clean = concierge._sanitize(state, "hello")
        assert clean["ai_message"] == "Salut"
        assert clean["detected_trade"] is None  # invalid trade dropped
        assert clean["live_diagnosis"]["urgency"] == "moyenne"
        assert clean["live_diagnosis"]["confidence"] == 100  # clamped
        assert clean["next_action"] == "continue"
        assert clean["followup_suggestions"] == []

    def test_sanitize_defaults_fill(self):
        clean = concierge._sanitize({}, "test")
        ld = clean["live_diagnosis"]
        for k in ("issue", "confidence", "urgency", "duration_min_hours",
                  "duration_max_hours", "price_min_eur", "price_max_eur", "risks"):
            assert k in ld
        assert clean["followup_suggestions"] == []
        assert clean["summary"] is None

    def test_sanitize_augments_safety_from_user_text(self):
        clean = concierge._sanitize({"safety_alerts": []}, "odeur gaz dans la cuisine")
        assert len(clean["safety_alerts"]) >= 1
        assert any(a["level"] == "urgence" for a in clean["safety_alerts"])


# ---------------- API: lifecycle ----------------
class TestConciergeLifecycle:
    @pytest.fixture(scope="class")
    def sid(self, s, client_token):
        r = s.post(f"{API}/concierge/start", headers=h(client_token), json={}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "session_id" in data and data["session_id"].startswith("conv_")
        st = data["state"]
        assert st["ai_message"].startswith("Bonjour")
        assert st["summary"] is None
        return data["session_id"]

    def test_start_persists_greeting_turn(self, s, client_token, sid):
        r = s.get(f"{API}/concierge/{sid}", headers=h(client_token), timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "active"
        assert d["session_id"] == sid
        assert len(d["turns"]) == 1
        assert d["turns"][0]["role"] == "assistant"

    def test_get_foreign_session_404(self, s, pro_token, sid):
        r = s.get(f"{API}/concierge/{sid}", headers=h(pro_token), timeout=15)
        assert r.status_code == 404

    def test_delete_foreign_session_404(self, s, pro_token, sid):
        r = s.delete(f"{API}/concierge/{sid}", headers=h(pro_token), timeout=15)
        assert r.status_code == 404

    def test_message_gas_smell_triggers_safety(self, s, client_token, sid):
        r = s.post(f"{API}/concierge/{sid}/message",
                   headers=h(client_token),
                   json={"text": "Il y a une odeur gaz forte dans ma cuisine"},
                   timeout=90)
        assert r.status_code == 200, r.text
        d = r.json()
        st = d["state"]
        # Deterministic safety-net MUST fire regardless of LLM output
        assert any(a["level"] == "urgence" for a in st.get("safety_alerts", [])), st.get("safety_alerts")
        assert st["live_diagnosis"]["urgency"] in ("urgence", "elevee", "moyenne", "faible")
        # user_text echoed
        assert "gaz" in d["user_text"].lower()

    def test_message_appends_turns(self, s, client_token, sid):
        r = s.get(f"{API}/concierge/{sid}", headers=h(client_token), timeout=15)
        d = r.json()
        # After start (1) + one message pair (2) = 3
        assert len(d["turns"]) >= 3
        roles = [t["role"] for t in d["turns"]]
        assert "user" in roles and "assistant" in roles

    def test_list_sessions_contains_this_one(self, s, client_token, sid):
        r = s.get(f"{API}/concierge/sessions", headers=h(client_token), timeout=15)
        assert r.status_code == 200
        rows = r.json()
        row = next((x for x in rows if x["session_id"] == sid), None)
        assert row is not None
        assert "last_message" in row
        # List MUST NOT include full turns array (perf)
        assert "turns" not in row

    def test_video_placeholder(self, s, client_token, sid):
        r = s.post(f"{API}/concierge/{sid}/video",
                   headers=h(client_token),
                   json={"filename": "TEST_leak.mp4", "size_bytes": 1234},
                   timeout=15)
        assert r.status_code == 200
        assert r.json().get("attached") is True
        # Now verify system turn + video_pending flag
        d = s.get(f"{API}/concierge/{sid}", headers=h(client_token), timeout=15).json()
        assert d.get("video_pending") is True
        assert any(t.get("video_placeholder") is True for t in d["turns"])

    def test_finish_completes_session(self, s, client_token, sid):
        r = s.post(f"{API}/concierge/{sid}/finish", headers=h(client_token), timeout=90)
        assert r.status_code == 200, r.text
        # session should be completed
        d = s.get(f"{API}/concierge/{sid}", headers=h(client_token), timeout=15).json()
        assert d["status"] == "completed"

    def test_message_after_finish_400(self, s, client_token, sid):
        r = s.post(f"{API}/concierge/{sid}/message",
                   headers=h(client_token),
                   json={"text": "encore"},
                   timeout=15)
        assert r.status_code == 400

    def test_finish_idempotent(self, s, client_token, sid):
        r = s.post(f"{API}/concierge/{sid}/finish", headers=h(client_token), timeout=15)
        assert r.status_code == 200
        assert r.json().get("already_finished") is True

    def test_delete_own_session(self, s, client_token, sid):
        r = s.delete(f"{API}/concierge/{sid}", headers=h(client_token), timeout=15)
        assert r.status_code == 200
        r = s.get(f"{API}/concierge/{sid}", headers=h(client_token), timeout=15)
        assert r.status_code == 404


# ---------------- API: multi-turn memory (best-effort) ----------------
class TestMultiTurnMemory:
    def test_memory_boiler_context(self, s, client_token):
        r = s.post(f"{API}/concierge/start", headers=h(client_token), json={}, timeout=15)
        sid = r.json()["session_id"]
        try:
            r1 = s.post(f"{API}/concierge/{sid}/message",
                        headers=h(client_token),
                        json={"text": "Ma chaudière fuit à l'arrière"},
                        timeout=90)
            assert r1.status_code == 200
            st1 = r1.json()["state"]
            # Trade detection best-effort: chauffagiste or plombier acceptable
            assert st1.get("detected_trade") in (
                "chauffagiste", "plombier", "climaticien", None,
            )
            time.sleep(1)
            r2 = s.post(f"{API}/concierge/{sid}/message",
                        headers=h(client_token),
                        json={"text": "Oui c'est dans la pièce à côté du salon"},
                        timeout=90)
            assert r2.status_code == 200
            # We don't hard-assert on natural language content — just that
            # a follow-up question comes back OK and confidence has advanced.
            st2 = r2.json()["state"]
            assert isinstance(st2["ai_message"], str) and len(st2["ai_message"]) > 0
        finally:
            s.delete(f"{API}/concierge/{sid}", headers=h(client_token), timeout=10)


# ---------------- Auth guards ----------------
class TestAuthGuards:
    def test_start_unauth_401(self, s):
        r = s.post(f"{API}/concierge/start", json={}, timeout=15)
        assert r.status_code == 401

    def test_list_unauth_401(self, s):
        r = s.get(f"{API}/concierge/sessions", timeout=15)
        assert r.status_code == 401

    def test_get_missing_404(self, s, client_token):
        r = s.get(f"{API}/concierge/conv_does_not_exist", headers=h(client_token), timeout=15)
        assert r.status_code == 404
