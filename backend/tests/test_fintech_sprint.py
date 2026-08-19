"""
Sprint FinTech (Stripe Connect + Escrow + Subscriptions + Admin) — backend tests.

⚠️ LEGACY MOCK-MODE tests. These tests were written against the payments
mock (`sk_test_emergent` placeholder) and rely on `acct_mock_*`, `pi_mock_*`
and the `/payments/{id}/mock-confirm` endpoint. Once real Stripe keys are
configured (Sprint 1, June 2026) `payments.MOCK_MODE` becomes `False` and
the whole file is skipped — a proper live-test-mode integration suite is
planned for the next hardening sprint.
"""
import os
import uuid
import pytest
import requests

from services import payments as _payments

pytestmark = pytest.mark.skipif(
    not _payments.MOCK_MODE,
    reason="Legacy mock-mode integration tests — see test_stripe_boot_validation.py for the live-mode contract.",
)

BASE = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://reviens-app.preview.emergentagent.com").rstrip("/") + "/api"
WEBHOOK_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://reviens-app.preview.emergentagent.com").rstrip("/") + "/api/stripe/webhooks"

CLIENT_EMAIL = "client.test@auxora.fr"
ARTISAN_EMAIL = "pro.test@auxora.fr"
PASSWORD = "Test1234!"


# --------------------------- Fixtures ---------------------------

@pytest.fixture(scope="session")
def s():
    return requests.Session()


def _login(s, email, password, role=None, name="Test"):
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        payload = {"email": email, "password": password, "name": name}
        if role:
            payload["role"] = role
        r = s.post(f"{BASE}/auth/register", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="session")
def client_auth(s):
    return _login(s, CLIENT_EMAIL, PASSWORD, role="client", name="Client Test")


@pytest.fixture(scope="session")
def artisan_auth(s):
    return _login(s, ARTISAN_EMAIL, PASSWORD, role="artisan", name="Pro Test")


@pytest.fixture(scope="session")
def other_client_auth(s):
    email = f"TEST_other_{uuid.uuid4().hex[:6]}@auxora.fr"
    return _login(s, email, PASSWORD, role="client", name="Other Client")


def H(auth):
    return {"Authorization": f"Bearer {auth['token']}"}


# --------------------------- 1. Subscription plans (public) ---------------------------



# --------------------------- 2. Future features stub ---------------------------



# --------------------------- 3. Connect onboarding ---------------------------

def test_connect_onboard_non_artisan_403(s, client_auth):
    r = s.post(f"{BASE}/connect/onboard", headers=H(client_auth), json={})
    assert r.status_code == 403


def test_connect_onboard_artisan_ok_and_reuse(s, artisan_auth):
    r1 = s.post(f"{BASE}/connect/onboard", headers=H(artisan_auth), json={})
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert "onboarding_url" in d1 and "expires_at" in d1
    assert d1["stripe_account_id"].startswith("acct_mock_"), "MOCK_MODE must yield acct_mock_ prefix"
    assert d1["mock_mode"] is True

    # Second call reuses existing stripe_account_id (no duplicate)
    r2 = s.post(f"{BASE}/connect/onboard", headers=H(artisan_auth), json={})
    assert r2.status_code == 200
    assert r2.json()["stripe_account_id"] == d1["stripe_account_id"]


def test_connect_status_shapes(s, client_auth, artisan_auth):
    # Client has no stripe account
    rc = s.get(f"{BASE}/connect/status", headers=H(client_auth))
    assert rc.status_code == 200
    assert rc.json()["connected"] is False

    ra = s.get(f"{BASE}/connect/status", headers=H(artisan_auth))
    assert ra.status_code == 200
    j = ra.json()
    assert j["connected"] is True
    for k in ["charges_enabled", "payouts_enabled", "details_submitted", "requirements", "stripe_account_id"]:
        assert k in j


# --------------------------- 4. Booking + payment intent + mock-confirm ---------------------------

def _get_artisan_id(s, artisan_auth):
    r = s.get(f"{BASE}/artisans/me", headers=H(artisan_auth))
    assert r.status_code == 200, r.text
    return r.json()["artisan_id"]


def _make_booking(s, client_auth, artisan_id):
    r = s.post(f"{BASE}/bookings", headers=H(client_auth), json={
        "artisan_id": artisan_id, "date": "2026-02-15", "slot": "10:00-12:00",
        "description": "TEST_fintech_booking",
    })
    assert r.status_code == 200, r.text
    return r.json()["booking_id"]


@pytest.fixture(scope="session")
def artisan_id(s, artisan_auth):
    return _get_artisan_id(s, artisan_auth)


def test_payment_intent_and_duplicate(s, client_auth, artisan_id):
    booking_id = _make_booking(s, client_auth, artisan_id)
    r = s.post(f"{BASE}/payments/create-intent", headers=H(client_auth), json={"booking_id": booking_id})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["amount_cents"] >= 2000
    assert d["payment_id"].startswith("pay_mock_")
    pid = d["payment_id"]

    # Duplicate -> same payment_id, no dup escrow
    r2 = s.post(f"{BASE}/payments/create-intent", headers=H(client_auth), json={"booking_id": booking_id})
    assert r2.status_code == 200
    assert r2.json()["payment_id"] == pid


def test_mock_confirm_moves_state(s, client_auth, artisan_id):
    booking_id = _make_booking(s, client_auth, artisan_id)
    intent = s.post(f"{BASE}/payments/create-intent", headers=H(client_auth), json={"booking_id": booking_id}).json()
    pid = intent["payment_id"]
    r = s.post(f"{BASE}/payments/{pid}/mock-confirm", headers=H(client_auth))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "succeeded"

    escrows = s.get(f"{BASE}/escrows/mine", headers=H(client_auth)).json()
    e = next((x for x in escrows if x["booking_id"] == booking_id), None)
    assert e is not None and e["state"] == "held"


# --------------------------- 5. Escrow release + commission precedence ---------------------------

def _held_booking(s, client_auth, artisan_id):
    booking_id = _make_booking(s, client_auth, artisan_id)
    pid = s.post(f"{BASE}/payments/create-intent", headers=H(client_auth), json={"booking_id": booking_id}).json()["payment_id"]
    s.post(f"{BASE}/payments/{pid}/mock-confirm", headers=H(client_auth)).raise_for_status()
    return booking_id


def test_commission_precedence_global_then_promo_then_exemption(s, client_auth, artisan_auth, artisan_id):
    # Ensure artisan is onboarded (fixture guarantees but idempotent)
    s.post(f"{BASE}/connect/onboard", headers=H(artisan_auth), json={})

    # 1) Global bps = 1500 (15%)
    r = s.put(f"{BASE}/admin/commissions", headers=H(client_auth), json={"global_bps": 1500, "min_cents": 200})
    assert r.status_code == 200
    # Clean up any active promos / exemptions from prior runs to isolate
    cfg = s.get(f"{BASE}/admin/commissions", headers=H(client_auth)).json()
    for rule in cfg.get("rules", []):
        if rule.get("active") and rule.get("kind") in ("promo", "exemption", "trade"):
            s.delete(f"{BASE}/admin/commission-rules/{rule['rule_id']}", headers=H(client_auth))

    b1 = _held_booking(s, client_auth, artisan_id)
    rel1 = s.post(f"{BASE}/escrow/{b1}/release", headers=H(client_auth))
    assert rel1.status_code == 200, rel1.text
    d1 = rel1.json()
    expected_fee1 = max(int(round(d1["gross_cents"] * 1500 / 10000)), 200)
    assert d1["commission_cents"] == expected_fee1, f"global bps=1500 expected fee {expected_fee1}, got {d1['commission_cents']}"
    assert d1["transfer_id"].startswith("tr_mock_")

    # 2) Add active promo 500 bps -> should win over global 1500
    promo = s.post(f"{BASE}/admin/commission-rules", headers=H(client_auth), json={
        "kind": "promo", "bps": 500,
        "start_at": "2000-01-01T00:00:00+00:00", "end_at": "2099-01-01T00:00:00+00:00",
        "label": "TEST_promo_500",
    })
    assert promo.status_code == 200, promo.text
    promo_id = promo.json()["rule_id"]

    b2 = _held_booking(s, client_auth, artisan_id)
    rel2 = s.post(f"{BASE}/escrow/{b2}/release", headers=H(client_auth)).json()
    expected_fee2 = max(int(round(rel2["gross_cents"] * 500 / 10000)), 200)
    assert rel2["commission_cents"] == expected_fee2, f"promo bps=500 should win: expected {expected_fee2}, got {rel2['commission_cents']}"

    # 3) Add exemption for this artisan bps=0 -> should win over promo
    exempt = s.post(f"{BASE}/admin/commission-rules", headers=H(client_auth), json={
        "kind": "exemption", "bps": 0, "artisan_id": artisan_id, "label": "TEST_exempt_0",
    })
    assert exempt.status_code == 200
    exempt_id = exempt.json()["rule_id"]

    b3 = _held_booking(s, client_auth, artisan_id)
    rel3 = s.post(f"{BASE}/escrow/{b3}/release", headers=H(client_auth)).json()
    # commission floors at min_cents=200 (2€) even if bps=0
    assert rel3["commission_cents"] == 200, f"exemption bps=0 should apply floor 200, got {rel3['commission_cents']}"

    # Cleanup: deactivate promo + exemption
    s.delete(f"{BASE}/admin/commission-rules/{promo_id}", headers=H(client_auth))
    s.delete(f"{BASE}/admin/commission-rules/{exempt_id}", headers=H(client_auth))


def test_release_state_machine_only_held(s, client_auth, artisan_id):
    # Fresh booking, no confirm -> escrow is 'pending', not releasable
    booking_id = _make_booking(s, client_auth, artisan_id)
    s.post(f"{BASE}/payments/create-intent", headers=H(client_auth), json={"booking_id": booking_id})
    r = s.post(f"{BASE}/escrow/{booking_id}/release", headers=H(client_auth))
    assert r.status_code == 400


# --------------------------- 6. Freeze + refund ---------------------------

def test_freeze_authorization(s, client_auth, other_client_auth, artisan_id):
    booking_id = _held_booking(s, client_auth, artisan_id)
    # Non-owner client -> 403
    r = s.post(f"{BASE}/escrow/freeze", headers=H(other_client_auth), json={"booking_id": booking_id, "reason": "TEST_unauth"})
    assert r.status_code == 403
    # Owner client -> 200
    r2 = s.post(f"{BASE}/escrow/freeze", headers=H(client_auth), json={"booking_id": booking_id, "reason": "TEST_freeze"})
    assert r2.status_code == 200
    assert r2.json()["state"] == "frozen"
    # Second freeze not held anymore -> 400
    r3 = s.post(f"{BASE}/escrow/freeze", headers=H(client_auth), json={"booking_id": booking_id, "reason": "again"})
    assert r3.status_code == 400
    # Refund from frozen -> ok
    rf = s.post(f"{BASE}/escrow/{booking_id}/refund", headers=H(client_auth), json={"reason": "TEST_refund"})
    assert rf.status_code == 200
    assert rf.json()["refund_id"].startswith("re_mock_")


def test_refund_from_held(s, client_auth, artisan_id):
    booking_id = _held_booking(s, client_auth, artisan_id)
    r = s.post(f"{BASE}/escrow/{booking_id}/refund", headers=H(client_auth), json={"reason": "TEST_refund_held"})
    assert r.status_code == 200
    # Double refund -> escrow now refunded, 400
    r2 = s.post(f"{BASE}/escrow/{booking_id}/refund", headers=H(client_auth), json={})
    assert r2.status_code == 400


# --------------------------- 7. Subscriptions ---------------------------









# --------------------------- 8. Artisan finance ---------------------------

def test_artisan_finance_shape(s, artisan_auth):
    r = s.get(f"{BASE}/artisans/me/finance", headers=H(artisan_auth))
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ["revenue_cents", "gross_cents", "commissions_cents", "pending_cents",
              "transfers_count", "monthly_evolution", "recent_transfers"]:
        assert k in d
    assert len(d["monthly_evolution"]) <= 6


def test_artisan_finance_client_403(s, client_auth):
    r = s.get(f"{BASE}/artisans/me/finance", headers=H(client_auth))
    assert r.status_code == 403


# --------------------------- 9. Admin gating ---------------------------

def test_admin_endpoints_non_admin_403(s, artisan_auth):
    for path in ["/admin/finance/overview", "/admin/commissions", "/admin/audit-logs"]:
        r = s.get(f"{BASE}{path}", headers=H(artisan_auth))
        assert r.status_code == 403, f"{path} should be 403 for non-admin"


def test_admin_finance_overview(s, client_auth):
    r = s.get(f"{BASE}/admin/finance/overview", headers=H(client_auth))
    assert r.status_code == 200
    d = r.json()
    for k in ["gross_cents", "payments_count", "commission_cents", "refunds_cents",
              "mrr_cents", "pending_payouts_cents", "failed_payments", "top_trades"]:
        assert k in d


def test_admin_commissions_get_and_put(s, client_auth):
    put = s.put(f"{BASE}/admin/commissions", headers=H(client_auth), json={"global_bps": 1000, "min_cents": 200})
    assert put.status_code == 200
    g = s.get(f"{BASE}/admin/commissions", headers=H(client_auth)).json()
    assert g["global_bps"] == 1000
    assert isinstance(g.get("rules"), list)


def test_admin_commission_rule_invalid_kind(s, client_auth):
    r = s.post(f"{BASE}/admin/commission-rules", headers=H(client_auth),
               json={"kind": "invalid_xxx", "bps": 100})
    assert r.status_code == 400


def test_admin_commission_rule_create_and_deactivate(s, client_auth):
    r = s.post(f"{BASE}/admin/commission-rules", headers=H(client_auth),
               json={"kind": "trade", "bps": 800, "trade": "TEST_trade_x", "label": "TEST_rule"})
    assert r.status_code == 200
    rid = r.json()["rule_id"]
    d = s.delete(f"{BASE}/admin/commission-rules/{rid}", headers=H(client_auth))
    assert d.status_code == 200
    # Verify inactive
    rules = s.get(f"{BASE}/admin/commissions", headers=H(client_auth)).json()["rules"]
    match = next((x for x in rules if x["rule_id"] == rid), None)
    assert match is not None and match["active"] is False


def test_admin_audit_logs(s, client_auth):
    r = s.get(f"{BASE}/admin/audit-logs?limit=20", headers=H(client_auth))
    assert r.status_code == 200
    logs = r.json()
    assert isinstance(logs, list) and len(logs) > 0
    # descending by created_at
    if len(logs) >= 2:
        assert logs[0]["created_at"] >= logs[1]["created_at"]


# --------------------------- 10. Webhook idempotency ---------------------------

def test_webhook_idempotency(s):
    ev_id = f"evt_test_{uuid.uuid4().hex[:8]}"
    body = {"id": ev_id, "type": "payment_intent.succeeded",
            "data": {"object": {"id": "pi_mock_nonexistent"}}}
    r1 = s.post(WEBHOOK_URL, json=body)
    assert r1.status_code == 200
    assert r1.json().get("received") is True
    r2 = s.post(WEBHOOK_URL, json=body)
    assert r2.status_code == 200
    assert r2.json().get("duplicate") is True


# --------------------------- 11. Matching (no subscription bias) ---------------------------





# --------------------------- 12. Regression ---------------------------

def test_regression_properties_list(s, client_auth):
    r = s.get(f"{BASE}/properties", headers=H(client_auth))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


