"""
admin router — V1 migration (Option B: fast structural partition).

Legacy routes previously defined inline in ``server.py`` are moved here
verbatim (bodies unchanged) and mounted via ``build_admin_router(**deps)``.
All external references (db, helpers, services, Pydantic models) are
injected via keyword arguments so this module has no circular import back
to ``server``.

Do NOT add new business logic here without splitting into a dedicated file —
this file exists to keep server.py small; the "canonical" refactor (typed
Pydantic input models per route, explicit dependency signatures) is a
follow-up sprint.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from services import payments, security
from datetime import datetime, timezone

# `db`, `get_current_user`, and every helper/service/model this module needs
# are captured in the closure of `build_admin_router(**deps)` below.


def build_admin_router(**deps) -> APIRouter:
    """Factory: returns an APIRouter mounting every admin endpoint.

    `deps` MUST include (all names as used inside the extracted route bodies):
    db, get_current_user, require_admin, now_utc, new_id, security, CommissionConfigInput, CommissionRuleInput
    """
    # Explode deps into locals so the extracted route bodies find them by name.
    globals().update(deps)  # noqa: F821 — populates module scope for closures
    _locals = deps
    for _k, _v in _locals.items():
        locals()[_k] = _v

    r = APIRouter()

    @r.get("/admin/finance/overview")
    async def admin_finance_overview(user=Depends(require_admin)):
        total_gross = await db.payments.aggregate([
            {"$match": {"status": "succeeded"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount_cents"}, "count": {"$sum": 1}}},
        ]).to_list(1)
        total_commissions = await db.transfers.aggregate([
            {"$group": {"_id": None, "total": {"$sum": "$commission_cents"}, "count": {"$sum": 1}}},
        ]).to_list(1)
        total_refunds = await db.refunds.aggregate([
            {"$group": {"_id": None, "total": {"$sum": "$amount_cents"}, "count": {"$sum": 1}}},
        ]).to_list(1)
        subs = await db.subscriptions_records.aggregate([
            {"$match": {"status": "active"}}, {"$group": {"_id": "$plan_key", "count": {"$sum": 1}}},
        ]).to_list(20)
        plan_price = {p["key"]: p["price_cents"] for p in payments.PLANS}
        mrr = sum(row["count"] * plan_price.get(row["_id"], 0) for row in subs)

        pending_payouts = await db.escrows.aggregate([
            {"$match": {"state": "held"}}, {"$group": {"_id": None, "total": {"$sum": "$amount_cents"}, "count": {"$sum": 1}}},
        ]).to_list(1)
        failed_payments = await db.payments.count_documents({"status": "payment_failed"})
        top_trades = await db.transfers.aggregate([
            {"$lookup": {"from": "artisan_profiles", "localField": "artisan_id", "foreignField": "artisan_id", "as": "a"}},
            {"$unwind": "$a"},
            {"$group": {"_id": "$a.trade", "revenue": {"$sum": "$gross_cents"}, "count": {"$sum": 1}}},
            {"$sort": {"revenue": -1}},
            {"$limit": 5},
        ]).to_list(5)
        return {
            "gross_cents": total_gross[0]["total"] if total_gross else 0,
            "payments_count": total_gross[0]["count"] if total_gross else 0,
            "commission_cents": total_commissions[0]["total"] if total_commissions else 0,
            "transfers_count": total_commissions[0]["count"] if total_commissions else 0,
            "refunds_cents": total_refunds[0]["total"] if total_refunds else 0,
            "refunds_count": total_refunds[0]["count"] if total_refunds else 0,
            "active_subscriptions": [{"plan": r["_id"], "count": r["count"]} for r in subs],
            "mrr_cents": mrr,
            "pending_payouts_cents": pending_payouts[0]["total"] if pending_payouts else 0,
            "pending_payouts_count": pending_payouts[0]["count"] if pending_payouts else 0,
            "failed_payments": failed_payments,
            "top_trades": [{"trade": r["_id"], "revenue_cents": r["revenue"], "count": r["count"]} for r in top_trades],
            "mock_mode": payments.MOCK_MODE,
        }


    @r.get("/admin/commissions")
    async def get_commission_config(user=Depends(require_admin)):
        cfg = await db.platform_config.find_one({"key": "commission"}, {"_id": 0}) or {}
        rules = await db.commission_rules.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
        return {
            "global_bps": cfg.get("global_bps", payments.DEFAULT_COMMISSION_BPS),
            "min_cents": cfg.get("min_cents", payments.DEFAULT_COMMISSION_MIN_CENTS),
            "rules": rules,
        }


    @r.put("/admin/commissions")
    async def set_commission_config(body: CommissionConfigInput, user=Depends(require_admin)):
        await db.platform_config.update_one(
            {"key": "commission"},
            {"$set": {"key": "commission", "global_bps": int(body.global_bps), "min_cents": int(body.min_cents), "updated_by": user["user_id"], "updated_at": payments.now_utc_iso()}},
            upsert=True,
        )
        await payments.audit(db, user["user_id"], "commission.global_updated", "commission", {"global_bps": body.global_bps, "min_cents": body.min_cents})
        return {"ok": True, "global_bps": body.global_bps, "min_cents": body.min_cents}


    @r.post("/admin/commission-rules")
    async def create_commission_rule(body: CommissionRuleInput, user=Depends(require_admin)):
        if body.kind not in ("trade", "promo", "exemption"):
            raise HTTPException(status_code=400, detail="kind invalide")
        doc = {
            "rule_id": new_id("crule"),
            "kind": body.kind,
            "bps": int(body.bps),
            "trade": body.trade,
            "artisan_id": body.artisan_id,
            "start_at": body.start_at,
            "end_at": body.end_at,
            "label": body.label or "",
            "active": True,
            "created_by": user["user_id"],
            "created_at": payments.now_utc_iso(),
        }
        await db.commission_rules.insert_one(dict(doc))
        await payments.audit(db, user["user_id"], "commission.rule_created", doc["rule_id"], {"kind": body.kind, "bps": body.bps})
        return doc


    @r.delete("/admin/commission-rules/{rule_id}")
    async def delete_commission_rule(rule_id: str, user=Depends(require_admin)):
        await db.commission_rules.update_one({"rule_id": rule_id}, {"$set": {"active": False, "deactivated_at": payments.now_utc_iso()}})
        await payments.audit(db, user["user_id"], "commission.rule_deactivated", rule_id)
        return {"ok": True}


    @r.get("/admin/audit-logs")
    async def admin_audit_logs(limit: int = 100, user=Depends(require_admin)):
        limit = max(1, min(500, limit))
        rows = await db.audit_logs.find({}, {"_id": 0}).sort("created_at", -1).to_list(limit)
        return rows


    return r
