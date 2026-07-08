"""
Enterprise / B2B sprint — backend tests.
Covers services/enterprise.py pure module + all 24 new /api endpoints in server.py.

Uses:
  - Client owner: client.test@auxora.fr (owns org_2d79cd03d073)
  - Pro (manager): pro.test@auxora.fr
  - Property: prop_b0858d7dc142
  - Work order: wo_787eb7df847a
"""
import os
import uuid
import pytest
import requests

from services import enterprise

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://reviens-app.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CLIENT = {"email": "client.test@auxora.fr", "password": "Test1234!"}
PRO = {"email": "pro.test@auxora.fr", "password": "Test1234!"}

SEED_ORG_ID = "org_2d79cd03d073"
SEED_PROP_ID = "prop_b0858d7dc142"
SEED_WO_ID = "wo_787eb7df847a"


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
def iso_org_id(s, client_token):
    """A pristine org where PRO is never invited — used for non-member 403 assertions."""
    name = f"TEST_iso_{uuid.uuid4().hex[:6]}"
    r = s.post(f"{API}/organizations",
               json={"name": name, "org_type": "warehouse"},
               headers=h(client_token), timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["organization_id"]


# ==========================================================
# PURE MODULE — services/enterprise.py
# ==========================================================
class TestEnterpriseModule:
    def test_account_types_length(self):
        assert len(enterprise.ACCOUNT_TYPES) == 6
        assert set(enterprise.ACCOUNT_TYPES) == {
            "personal", "professional", "business", "property_manager", "admin", "super_admin"
        }

    def test_org_types_length(self):
        assert len(enterprise.ORG_TYPES) == 12

    def test_team_roles_length(self):
        assert len(enterprise.TEAM_ROLES) == 7

    def test_permissions_owner_largest(self):
        owner = enterprise.PERMISSIONS["owner"]
        for role in ["manager", "supervisor", "maintenance_manager", "finance", "employee", "viewer"]:
            assert len(owner) >= len(enterprise.PERMISSIONS[role])
        assert len(owner) >= 20

    def test_permissions_viewer_empty(self):
        assert enterprise.PERMISSIONS["viewer"] == set()

    def test_work_order_statuses(self):
        assert len(enterprise.WORK_ORDER_STATUSES) == 7

    def test_work_order_transitions(self):
        t = enterprise.WORK_ORDER_TRANSITIONS
        assert t["draft"] == {"pending_approval", "cancelled"}
        assert t["pending_approval"] == {"approved", "rejected", "cancelled"}
        assert t["approved"] == {"in_progress", "cancelled"}
        assert t["in_progress"] == {"completed", "cancelled"}
        assert t["completed"] == set()
        assert t["rejected"] == set()
        assert t["cancelled"] == set()

    def test_has_permission(self):
        assert enterprise.has_permission("owner", "org.delete") is True
        assert enterprise.has_permission("viewer", "org.delete") is False
        assert enterprise.has_permission("employee", "work_order.create") is True
        assert enterprise.has_permission("employee", "work_order.approve") is False


# ==========================================================
# ENTERPRISE meta endpoints
# ==========================================================
class TestEnterpriseMeta:
    def test_roles_capabilities(self, s):
        r = s.get(f"{API}/enterprise/roles", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert set(data.keys()) == set(enterprise.TEAM_ROLES)
        assert len(data["owner"]) >= 20
        assert len(data["employee"]) == 2
        assert data["viewer"] == []
        # sorted
        for role, caps in data.items():
            assert caps == sorted(caps)

    def test_account_types(self, s):
        r = s.get(f"{API}/enterprise/account-types", timeout=15)
        assert r.status_code == 200
        assert len(r.json()) == 6


# ==========================================================
# ORGANIZATIONS CRUD + membership
# ==========================================================
class TestOrganizationsCRUD:
    def test_create_org_invalid_type_400(self, s, client_token):
        r = s.post(f"{API}/organizations",
                   json={"name": "Bad", "org_type": "not_a_type"},
                   headers=h(client_token), timeout=15)
        assert r.status_code == 400, r.text

    def test_create_org_valid_and_persists(self, s, client_token, client_auth):
        name = f"TEST_org_{uuid.uuid4().hex[:6]}"
        r = s.post(f"{API}/organizations",
                   json={"name": name, "org_type": "restaurant"},
                   headers=h(client_token), timeout=15)
        assert r.status_code == 200, r.text
        org = r.json()
        assert org["name"] == name
        assert org["org_type"] == "restaurant"
        assert org["owner_id"] == client_auth["user"]["user_id"]
        pytest.new_org_id = org["organization_id"]

        # Verify GET /organizations/mine returns it with my_role=owner
        r = s.get(f"{API}/organizations/mine", headers=h(client_token), timeout=15)
        assert r.status_code == 200
        listed = r.json()
        match = [o for o in listed if o["organization_id"] == pytest.new_org_id]
        assert match, "Newly created org not in mine"
        assert match[0]["my_role"] == "owner"

    def test_seed_org_owner_role(self, s, client_token):
        r = s.get(f"{API}/organizations/mine", headers=h(client_token), timeout=15)
        assert r.status_code == 200
        match = [o for o in r.json() if o["organization_id"] == SEED_ORG_ID]
        assert match, "Seed org not owned by client"
        assert match[0]["my_role"] == "owner"

    def test_patch_org_invalid_type_400(self, s, client_token):
        r = s.patch(f"{API}/organizations/{pytest.new_org_id}",
                    json={"org_type": "invalid"},
                    headers=h(client_token), timeout=15)
        assert r.status_code == 400

    def test_patch_org_updates_only_allowed_fields(self, s, client_token):
        r = s.patch(f"{API}/organizations/{pytest.new_org_id}",
                    json={"industry": "F&B", "malicious": "x", "owner_id": "hax"},
                    headers=h(client_token), timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("industry") == "F&B"
        assert data.get("owner_id") != "hax"
        assert "malicious" not in data

    def test_patch_org_non_owner_403(self, s, pro_token):
        # pro is not member of pytest.new_org_id
        r = s.patch(f"{API}/organizations/{pytest.new_org_id}",
                    json={"industry": "Illegal"},
                    headers=h(pro_token), timeout=15)
        assert r.status_code == 403


# ==========================================================
# MEMBERS
# ==========================================================
class TestOrgMembers:
    def test_list_members_forbids_non_member(self, s, pro_token):
        r = s.get(f"{API}/organizations/{pytest.new_org_id}/members",
                  headers=h(pro_token), timeout=15)
        assert r.status_code == 403

    def test_list_members_owner_ok(self, s, client_token):
        r = s.get(f"{API}/organizations/{pytest.new_org_id}/members",
                  headers=h(client_token), timeout=15)
        assert r.status_code == 200
        members = r.json()
        assert any(m["role"] == "owner" for m in members)

    def test_invite_invalid_role_400(self, s, client_token):
        r = s.post(f"{API}/organizations/{pytest.new_org_id}/members",
                   json={"email": "x@y.z", "role": "not_a_role"},
                   headers=h(client_token), timeout=15)
        assert r.status_code == 400

    def test_invite_owner_role_400(self, s, client_token):
        r = s.post(f"{API}/organizations/{pytest.new_org_id}/members",
                   json={"email": "x@y.z", "role": "owner"},
                   headers=h(client_token), timeout=15)
        assert r.status_code == 400

    def test_invite_known_email_becomes_active(self, s, client_token, pro_auth):
        r = s.post(f"{API}/organizations/{pytest.new_org_id}/members",
                   json={"email": PRO["email"], "role": "manager"},
                   headers=h(client_token), timeout=15)
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["status"] == "active"
        assert m["user_id"] == pro_auth["user"]["user_id"]
        assert m["role"] == "manager"
        pytest.pro_member_id = m["member_id"]

    def test_invite_unknown_email_becomes_invited(self, s, client_token):
        r = s.post(f"{API}/organizations/{pytest.new_org_id}/members",
                   json={"email": f"unknown_{uuid.uuid4().hex[:6]}@example.com", "role": "employee"},
                   headers=h(client_token), timeout=15)
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["status"] == "invited"
        assert m["user_id"] is None
        pytest.invited_member_id = m["member_id"]

    def test_invite_without_permission_403(self, s, pro_token):
        # Pro is now a MANAGER — manager HAS team.invite. So test with employee role via a
        # role_downgrade: we downgrade pro to viewer, then verify viewer cannot invite.
        # But first save state - we'll re-promote after.
        pass  # covered by next test flow

    def test_update_role_invalid_400(self, s, client_token):
        r = s.patch(f"{API}/organizations/{pytest.new_org_id}/members/{pytest.pro_member_id}",
                    json={"role": "boss"}, headers=h(client_token), timeout=15)
        assert r.status_code == 400

    def test_update_role_owner_400(self, s, client_token):
        r = s.patch(f"{API}/organizations/{pytest.new_org_id}/members/{pytest.pro_member_id}",
                    json={"role": "owner"}, headers=h(client_token), timeout=15)
        assert r.status_code == 400

    def test_update_role_downgrade_to_viewer(self, s, client_token):
        r = s.patch(f"{API}/organizations/{pytest.new_org_id}/members/{pytest.pro_member_id}",
                    json={"role": "viewer"}, headers=h(client_token), timeout=15)
        assert r.status_code == 200
        assert r.json()["role"] == "viewer"

    def test_viewer_cannot_invite_403(self, s, pro_token):
        r = s.post(f"{API}/organizations/{pytest.new_org_id}/members",
                   json={"email": "someone@x.y", "role": "employee"},
                   headers=h(pro_token), timeout=15)
        assert r.status_code == 403

    def test_viewer_cannot_update_role_403(self, s, pro_token):
        r = s.patch(f"{API}/organizations/{pytest.new_org_id}/members/{pytest.invited_member_id}",
                    json={"role": "supervisor"}, headers=h(pro_token), timeout=15)
        assert r.status_code == 403

    def test_viewer_cannot_remove_member_403(self, s, pro_token):
        r = s.delete(f"{API}/organizations/{pytest.new_org_id}/members/{pytest.invited_member_id}",
                     headers=h(pro_token), timeout=15)
        assert r.status_code == 403

    def test_owner_can_remove(self, s, client_token):
        r = s.delete(f"{API}/organizations/{pytest.new_org_id}/members/{pytest.invited_member_id}",
                     headers=h(client_token), timeout=15)
        assert r.status_code == 200


# ==========================================================
# PROPERTIES linkage
# ==========================================================
class TestOrgProperties:
    def test_link_property_not_owned_404(self, s, client_token):
        r = s.post(f"{API}/organizations/{pytest.new_org_id}/properties/link",
                   json={"property_id": "prop_fake_000000"},
                   headers=h(client_token), timeout=15)
        assert r.status_code == 404

    def test_link_property_without_permission_403(self, s, pro_token):
        # pro is viewer now — no property.add
        r = s.post(f"{API}/organizations/{pytest.new_org_id}/properties/link",
                   json={"property_id": SEED_PROP_ID},
                   headers=h(pro_token), timeout=15)
        assert r.status_code == 403

    def test_seed_org_lists_property(self, s, client_token):
        r = s.get(f"{API}/organizations/{SEED_ORG_ID}/properties",
                  headers=h(client_token), timeout=15)
        assert r.status_code == 200
        props = r.json()
        assert any(p["property_id"] == SEED_PROP_ID for p in props)


# ==========================================================
# WORK ORDERS
# ==========================================================
class TestWorkOrders:
    def test_create_wo_invalid_priority_400(self, s, client_token):
        r = s.post(f"{API}/work-orders",
                   json={"organization_id": SEED_ORG_ID, "title": "T", "priority": "boss"},
                   headers=h(client_token), timeout=15)
        assert r.status_code == 400

    def test_create_wo_no_permission_403(self, s, pro_token):
        # pro is viewer in pytest.new_org_id
        r = s.post(f"{API}/work-orders",
                   json={"organization_id": pytest.new_org_id, "title": "TEST", "priority": "normal"},
                   headers=h(pro_token), timeout=15)
        assert r.status_code == 403

    def test_owner_creates_in_draft(self, s, client_token):
        r = s.post(f"{API}/work-orders",
                   json={"organization_id": SEED_ORG_ID, "title": "TEST_wo_draft",
                         "priority": "normal", "trade": "plombier"},
                   headers=h(client_token), timeout=15)
        assert r.status_code == 200, r.text
        wo = r.json()
        assert wo["status"] == "draft"
        assert len(wo["history"]) == 1
        assert wo["history"][0]["status"] == "draft"
        pytest.owner_wo_id = wo["work_order_id"]

    def test_employee_creates_in_pending_approval(self, s, client_token, pro_token, pro_auth):
        # Update pro's existing membership in new_org to 'employee' via PATCH
        lst = s.get(f"{API}/organizations/{pytest.new_org_id}/members",
                    headers=h(client_token), timeout=15).json()
        pro_ms = [m for m in lst if m.get("user_id") == pro_auth["user"]["user_id"]]
        assert pro_ms, "Pro is not a member of the new org"
        # Update ALL pro memberships to employee (should be exactly one)
        for m in pro_ms:
            r = s.patch(f"{API}/organizations/{pytest.new_org_id}/members/{m['member_id']}",
                        json={"role": "employee"}, headers=h(client_token), timeout=15)
            assert r.status_code == 200

        # Now pro creates a WO in the new org
        r2 = s.post(f"{API}/work-orders",
                    json={"organization_id": pytest.new_org_id, "title": "TEST_wo_pa",
                          "priority": "high"},
                    headers=h(pro_token), timeout=15)
        assert r2.status_code == 200, r2.text
        wo = r2.json()
        assert wo["status"] == "pending_approval"
        assert wo["history"][0]["status"] == "pending_approval"

    def test_list_all_my_orgs_no_filter(self, s, client_token):
        r = s.get(f"{API}/work-orders", headers=h(client_token), timeout=15)
        assert r.status_code == 200
        wos = r.json()
        assert isinstance(wos, list)
        # Should include SEED_WO_ID from seed org
        assert any(w["work_order_id"] == SEED_WO_ID for w in wos)

    def test_list_status_invalid_400(self, s, client_token):
        r = s.get(f"{API}/work-orders?status=broken",
                  headers=h(client_token), timeout=15)
        assert r.status_code == 400

    def test_list_filter_org_not_member_403(self, s, pro_token, iso_org_id):
        r = s.get(f"{API}/work-orders?organization_id={iso_org_id}",
                  headers=h(pro_token), timeout=15)
        assert r.status_code == 403

    def test_get_wo_404(self, s, client_token):
        r = s.get(f"{API}/work-orders/wo_does_not_exist",
                  headers=h(client_token), timeout=15)
        assert r.status_code == 404

    def test_get_wo_non_member_403(self, s, pro_token, client_token, iso_org_id):
        # Create a WO in iso org (owner=client), then verify pro (non-member) gets 403
        r = s.post(f"{API}/work-orders",
                   json={"organization_id": iso_org_id, "title": "TEST_iso_wo", "priority": "normal"},
                   headers=h(client_token), timeout=15)
        assert r.status_code == 200, r.text
        iso_wo = r.json()["work_order_id"]
        r = s.get(f"{API}/work-orders/{iso_wo}", headers=h(pro_token), timeout=15)
        assert r.status_code == 403

    def test_transition_invalid_status_400(self, s, client_token):
        r = s.post(f"{API}/work-orders/{pytest.owner_wo_id}/transition",
                   json={"to_status": "banana"},
                   headers=h(client_token), timeout=15)
        assert r.status_code == 400

    def test_transition_disallowed_by_workflow_400(self, s, client_token):
        # From "draft" you cannot jump to "completed"
        r = s.post(f"{API}/work-orders/{pytest.owner_wo_id}/transition",
                   json={"to_status": "completed"},
                   headers=h(client_token), timeout=15)
        assert r.status_code == 400

    def test_full_workflow_draft_to_completed(self, s, client_token):
        wo = pytest.owner_wo_id
        # draft → pending_approval
        r = s.post(f"{API}/work-orders/{wo}/transition",
                   json={"to_status": "pending_approval", "note": "review"},
                   headers=h(client_token), timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "pending_approval"
        # pending_approval → approved
        r = s.post(f"{API}/work-orders/{wo}/transition",
                   json={"to_status": "approved"},
                   headers=h(client_token), timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] == "approved"
        # approved → in_progress
        r = s.post(f"{API}/work-orders/{wo}/transition",
                   json={"to_status": "in_progress"},
                   headers=h(client_token), timeout=15)
        assert r.status_code == 200
        # in_progress → completed
        r = s.post(f"{API}/work-orders/{wo}/transition",
                   json={"to_status": "completed", "note": "done"},
                   headers=h(client_token), timeout=15)
        assert r.status_code == 200
        assert r.json()["status"] == "completed"

        # Verify history via GET
        r = s.get(f"{API}/work-orders/{wo}", headers=h(client_token), timeout=15)
        assert r.status_code == 200
        w = r.json()
        assert len(w["history"]) == 5  # initial draft + 4 transitions
        statuses = [h["status"] for h in w["history"]]
        assert statuses == ["draft", "pending_approval", "approved", "in_progress", "completed"]

    def test_transition_from_terminal_400(self, s, client_token):
        r = s.post(f"{API}/work-orders/{pytest.owner_wo_id}/transition",
                   json={"to_status": "cancelled"},
                   headers=h(client_token), timeout=15)
        # completed is terminal → 400
        assert r.status_code == 400


# ==========================================================
# DASHBOARD / ANALYTICS / MAP
# ==========================================================
class TestDashboardAnalyticsMap:
    def test_dashboard_keys(self, s, client_token):
        r = s.get(f"{API}/organizations/{SEED_ORG_ID}/dashboard",
                  headers=h(client_token), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        required = {"total_properties", "open_interventions", "upcoming_maintenance",
                    "pending_approvals", "monthly_spending_cents", "monthly_payments_count",
                    "avg_response_min", "property_documents_count",
                    "organization_documents_count", "invoices_count", "recent_activity"}
        assert required.issubset(set(d.keys())), f"missing: {required - set(d.keys())}"
        assert isinstance(d["recent_activity"], list)
        assert len(d["recent_activity"]) <= 10

    def test_dashboard_non_member_403(self, s, pro_token, iso_org_id):
        r = s.get(f"{API}/organizations/{iso_org_id}/dashboard",
                  headers=h(pro_token), timeout=15)
        assert r.status_code == 403

    def test_analytics_keys(self, s, client_token):
        r = s.get(f"{API}/organizations/{SEED_ORG_ID}/analytics",
                  headers=h(client_token), timeout=15)
        assert r.status_code == 200
        d = r.json()
        required = {"completed_work_orders", "urgent_work_orders", "frequent_issues",
                    "top_professionals", "average_property_health", "properties_count"}
        assert required.issubset(set(d.keys()))
        assert isinstance(d["frequent_issues"], list)
        assert len(d["frequent_issues"]) <= 5
        assert len(d["top_professionals"]) <= 5

    def test_map(self, s, client_token):
        r = s.get(f"{API}/organizations/{SEED_ORG_ID}/map",
                  headers=h(client_token), timeout=15)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        if items:
            keys = {"property_id", "name", "address", "lat", "lng",
                    "open_interventions", "urgent_count", "upcoming_maintenance"}
            assert keys.issubset(set(items[0].keys()))


# ==========================================================
# DOCUMENTS
# ==========================================================
class TestOrgDocuments:
    def test_upload_invalid_category_400(self, s, client_token):
        r = s.post(f"{API}/organizations/{SEED_ORG_ID}/documents",
                   json={"title": "T", "category": "not_a_cat"},
                   headers=h(client_token), timeout=15)
        assert r.status_code == 400

    def test_upload_ok_all_categories(self, s, client_token):
        for cat in ["invoice", "contract", "report", "certificate", "guarantee",
                    "manual", "inspection", "safety", "other"]:
            r = s.post(f"{API}/organizations/{SEED_ORG_ID}/documents",
                       json={"title": f"TEST_{cat}", "category": cat, "file_uri": "x://f"},
                       headers=h(client_token), timeout=15)
            assert r.status_code == 200, f"{cat}: {r.text}"
        pytest.doc_id_to_delete = r.json()["document_id"]

    def test_upload_without_permission_403(self, s, pro_token, iso_org_id):
        # pro is not a member of the iso org
        r = s.post(f"{API}/organizations/{iso_org_id}/documents",
                   json={"title": "T", "category": "other"},
                   headers=h(pro_token), timeout=15)
        assert r.status_code == 403

    def test_list_filter_invalid_category_400(self, s, client_token):
        r = s.get(f"{API}/organizations/{SEED_ORG_ID}/documents?category=zzz",
                  headers=h(client_token), timeout=15)
        assert r.status_code == 400

    def test_list_filter_ok(self, s, client_token):
        r = s.get(f"{API}/organizations/{SEED_ORG_ID}/documents?category=invoice",
                  headers=h(client_token), timeout=15)
        assert r.status_code == 200
        docs = r.json()
        for d in docs:
            assert d["category"] == "invoice"

    def test_delete_document_owner_ok(self, s, client_token):
        r = s.delete(f"{API}/organizations/{SEED_ORG_ID}/documents/{pytest.doc_id_to_delete}",
                     headers=h(client_token), timeout=15)
        assert r.status_code == 200


# ==========================================================
# INTEGRATIONS
# ==========================================================
class TestIntegrations:
    def test_catalog_shape(self, s):
        r = s.get(f"{API}/integrations/available", timeout=15)
        assert r.status_code == 200
        cat = r.json()
        assert len(cat) == 10
        families = {i["family"] for i in cat}
        assert families == {"ERP", "Accounting", "FM", "IoT", "BMS"}
        for i in cat:
            assert i["status"] == "coming_soon"
            assert {"key", "name", "family"}.issubset(i.keys())

    def test_configure_unknown_key_400(self, s, client_token):
        r = s.post(f"{API}/organizations/{SEED_ORG_ID}/integrations",
                   json={"integration_key": "nope_not_a_key", "config": {}},
                   headers=h(client_token), timeout=15)
        assert r.status_code == 400

    def test_configure_without_permission_403(self, s, pro_token, iso_org_id):
        # pro is not member of iso org
        r = s.post(f"{API}/organizations/{iso_org_id}/integrations",
                   json={"integration_key": "sap", "config": {}},
                   headers=h(pro_token), timeout=15)
        assert r.status_code == 403

    def test_configure_owner_ok_status_coming_soon(self, s, client_token):
        r = s.post(f"{API}/organizations/{SEED_ORG_ID}/integrations",
                   json={"integration_key": "sap", "config": {"host": "sap.corp"}},
                   headers=h(client_token), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "coming_soon"
        assert d["integration_key"] == "sap"
        # Verify persisted
        r = s.get(f"{API}/organizations/{SEED_ORG_ID}/integrations",
                  headers=h(client_token), timeout=15)
        assert r.status_code == 200
        assert any(i["integration_key"] == "sap" for i in r.json())
