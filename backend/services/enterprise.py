"""
ProConnect / Auxora — Enterprise / B2B Layer
=============================================
Everything a business needs on top of the existing B2C stack — organizations,
team members with roles + granular permissions, work orders with approval
workflow, business dashboards, multi-location aggregation, and stubs for
future ERP/Accounting/FM/IoT/BMS integrations.

Design invariants
-----------------
- ONE application. `account_type` on the user determines which surface is
  active — no fork.
- Every organization-scoped resource carries `organization_id`.
- Permissions are declarative via `PERMISSIONS[role]` — trivial to audit and
  future-proof for a real RBAC/ABAC store.
- Zero DB coupling — server.py persists.
"""
from __future__ import annotations
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timezone

ACCOUNT_TYPES = ["personal", "professional", "business", "property_manager", "admin", "super_admin"]

ORG_TYPES = [
    "hotel", "restaurant", "retail_chain", "warehouse", "office",
    "apartment_building", "shopping_center", "medical_clinic", "school",
    "factory", "property_manager", "other",
]

TEAM_ROLES = ["owner", "manager", "supervisor", "maintenance_manager", "finance", "employee", "viewer"]

# --- RBAC permission matrix ----------------------------------------------
# Every high-level action lives here — server.py checks via has_permission().
PERMISSIONS: Dict[str, Set[str]] = {
    "owner": {
        "org.update", "org.delete", "team.invite", "team.remove", "team.update_role",
        "property.add", "property.remove", "property.update",
        "work_order.create", "work_order.update", "work_order.approve", "work_order.reject", "work_order.complete", "work_order.cancel",
        "documents.upload", "documents.delete",
        "analytics.view", "invoices.view", "invoices.pay",
        "integrations.configure",
    },
    "manager": {
        "team.invite", "team.remove",
        "property.add", "property.update",
        "work_order.create", "work_order.update", "work_order.approve", "work_order.reject", "work_order.complete", "work_order.cancel",
        "documents.upload", "analytics.view", "invoices.view",
    },
    "supervisor": {
        "work_order.create", "work_order.update", "work_order.complete",
        "documents.upload", "analytics.view",
    },
    "maintenance_manager": {
        "work_order.create", "work_order.update", "work_order.complete",
        "documents.upload", "analytics.view",
    },
    "finance": {
        "analytics.view", "invoices.view", "invoices.pay",
        "work_order.approve",  # can approve based on cost thresholds
    },
    "employee": {
        "work_order.create",  # creations go into pending_approval
        "documents.upload",
    },
    "viewer": set(),  # read-only — enforced by absence
}

# --- Work order workflow -------------------------------------------------
WORK_ORDER_STATUSES = ["draft", "pending_approval", "approved", "rejected", "in_progress", "completed", "cancelled"]
WORK_ORDER_PRIORITIES = ["low", "normal", "high", "urgent"]

WORK_ORDER_TRANSITIONS: Dict[str, Set[str]] = {
    "draft":             {"pending_approval", "cancelled"},
    "pending_approval":  {"approved", "rejected", "cancelled"},
    "approved":          {"in_progress", "cancelled"},
    "in_progress":       {"completed", "cancelled"},
    "completed":         set(),
    "rejected":          set(),
    "cancelled":         set(),
}

# --- Integration catalog (stubs; no implementation yet) ------------------
INTEGRATIONS_CATALOG = [
    {"key": "sap",         "family": "ERP",        "name": "SAP",             "status": "coming_soon"},
    {"key": "oracle",      "family": "ERP",        "name": "Oracle ERP",      "status": "coming_soon"},
    {"key": "sage",        "family": "Accounting", "name": "Sage",            "status": "coming_soon"},
    {"key": "quickbooks",  "family": "Accounting", "name": "QuickBooks",      "status": "coming_soon"},
    {"key": "xero",        "family": "Accounting", "name": "Xero",            "status": "coming_soon"},
    {"key": "planon",      "family": "FM",         "name": "Planon",          "status": "coming_soon"},
    {"key": "servicenow",  "family": "FM",         "name": "ServiceNow FSM",  "status": "coming_soon"},
    {"key": "iot_generic", "family": "IoT",        "name": "MQTT / IoT hub",  "status": "coming_soon"},
    {"key": "bms_niagara", "family": "BMS",        "name": "Niagara Framework","status": "coming_soon"},
    {"key": "bms_bacnet",  "family": "BMS",        "name": "BACnet gateway",  "status": "coming_soon"},
]

def has_permission(role: str, action: str) -> bool:
    return action in PERMISSIONS.get(role, set())

def role_capabilities(role: str) -> List[str]:
    return sorted(PERMISSIONS.get(role, set()))

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
