"""
payments router — V1 migration (Option B: fast structural partition).

Legacy routes previously defined inline in ``server.py`` are moved here
verbatim (bodies unchanged) and mounted via ``build_payments_router(**deps)``.
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
from services import payments, paypal as paypal_svc, trust_engine, security
from datetime import datetime, timezone

# `db`, `get_current_user`, and every helper/service/model this module needs
# are captured in the closure of `build_payments_router(**deps)` below.


def build_payments_router(**deps) -> APIRouter:
    """Factory: returns an APIRouter mounting every payments endpoint.

    `deps` MUST include (all names as used inside the extracted route bodies):
    db, get_current_user, now_utc, new_id, _append_passport_history, _compute_deposit_cents, payments, paypal_svc, trust_engine, ADMIN_EMAILS, ESCROW_STATES, PaymentIntentInput, ConnectOnboardInput, RefundInput, DisputeFreezeInput, DepositCreateInput, FinalCreateInput, require_admin
    """
    # Explode deps into locals so the extracted route bodies find them by name.
    globals().update(deps)  # noqa: F821 — populates module scope for closures
    _locals = deps
    for _k, _v in _locals.items():
        locals()[_k] = _v

    r = APIRouter()

    @r.post("/connect/onboard")
    async def connect_onboard(body: ConnectOnboardInput, user=Depends(get_current_user)):
        if user.get("role") != "artisan":
            raise HTTPException(status_code=403, detail="Réservé aux artisans")
        profile = await db.artisan_profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
        if not profile:
            raise HTTPException(status_code=400, detail="Créez d'abord votre profil artisan")

        existing = await db.stripe_accounts.find_one({"user_id": user["user_id"]}, {"_id": 0})
        try:
            if existing:
                acct_id = existing["stripe_account_id"]
            else:
                acct = payments.create_connect_account(user["email"], body.country)
                acct_id = acct["id"]
                await db.stripe_accounts.insert_one({
                    "user_id": user["user_id"],
                    "artisan_id": profile["artisan_id"],
                    "stripe_account_id": acct_id,
                    "country": body.country,
                    "charges_enabled": False,
                    "payouts_enabled": False,
                    "details_submitted": False,
                    "created_at": payments.now_utc_iso(),
                })
                await payments.audit(db, user["user_id"], "connect.account_created", acct_id, {"artisan_id": profile["artisan_id"]})

            link = payments.create_account_link(
                acct_id,
                return_url=f"{payments.PLATFORM_URL}/connect/return",
                refresh_url=f"{payments.PLATFORM_URL}/connect/refresh",
            )
        except payments.StripeAccountUnavailable as exc:
            # Structured 503 instead of a bare 500 when Stripe rejects the
            # Accounts API (v1 deprecated, live-mode not activated, etc.).
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "STRIPE_CONNECT_UNAVAILABLE",
                    "message": str(exc),
                },
            )
        return {"onboarding_url": link["url"], "expires_at": link.get("expires_at"), "stripe_account_id": acct_id, "mock_mode": payments.MOCK_MODE}


    @r.get("/connect/status")
    async def connect_status(user=Depends(get_current_user)):
        row = await db.stripe_accounts.find_one({"user_id": user["user_id"]}, {"_id": 0})
        if not row:
            return {"connected": False}
        fresh = payments.retrieve_account(row["stripe_account_id"])
        await db.stripe_accounts.update_one(
            {"stripe_account_id": row["stripe_account_id"]},
            {"$set": {
                "charges_enabled": fresh.get("charges_enabled", False),
                "payouts_enabled": fresh.get("payouts_enabled", False),
                "details_submitted": fresh.get("details_submitted", False),
                "requirements": fresh.get("requirements", {}),
                "updated_at": payments.now_utc_iso(),
            }},
        )
        return {
            "connected": True,
            "stripe_account_id": row["stripe_account_id"],
            "charges_enabled": fresh.get("charges_enabled", False),
            "payouts_enabled": fresh.get("payouts_enabled", False),
            "details_submitted": fresh.get("details_submitted", False),
            "requirements": fresh.get("requirements", {}),
            "mock_mode": payments.MOCK_MODE,
        }


    @r.post("/payments/create-intent")
    async def create_payment_intent(body: PaymentIntentInput, user=Depends(get_current_user)):
        booking = await db.bookings.find_one({"booking_id": body.booking_id, "client_id": user["user_id"]}, {"_id": 0})
        if not booking:
            raise HTTPException(status_code=404, detail="Réservation introuvable")
        existing = await db.payments.find_one({"booking_id": body.booking_id, "status": {"$in": ["requires_confirmation", "succeeded"]}}, {"_id": 0})
        if existing:
            return {"payment_id": existing["payment_id"], "client_secret": existing.get("client_secret"), "amount_cents": existing["amount_cents"]}

        artisan = await db.artisan_profiles.find_one({"artisan_id": booking["artisan_id"]}, {"_id": 0}) or {}
        hourly = int(round((artisan.get("hourly_rate") or 60) * 100))  # gross cents
        amount = max(hourly, 2000)  # min 20€
        intent = payments.create_payment_intent(
            amount_cents=amount,
            currency="eur",
            metadata={"booking_id": body.booking_id, "client_id": user["user_id"], "artisan_id": booking["artisan_id"]},
            customer_email=user["email"],
        )
        payment_id = payments._mock_id("pay") if payments.MOCK_MODE else new_id("pay")
        doc = {
            "payment_id": payment_id,
            "booking_id": body.booking_id,
            "client_id": user["user_id"],
            "artisan_id": booking["artisan_id"],
            "stripe_payment_intent_id": intent["id"],
            "client_secret": intent.get("client_secret"),
            "amount_cents": amount,
            "currency": "eur",
            "status": intent.get("status", "requires_confirmation"),
            "created_at": payments.now_utc_iso(),
        }
        await db.payments.insert_one(dict(doc))
        # Create escrow envelope (state=pending; becomes 'held' once webhook confirms).
        await db.escrows.insert_one({
            "escrow_id": new_id("esc"),
            "payment_id": payment_id,
            "booking_id": body.booking_id,
            "artisan_id": booking["artisan_id"],
            "amount_cents": amount,
            "state": "pending",
            "created_at": payments.now_utc_iso(),
        })
        await payments.audit(db, user["user_id"], "payment.intent_created", payment_id, {"amount_cents": amount, "booking_id": body.booking_id})
        return {"payment_id": payment_id, "client_secret": intent.get("client_secret"), "amount_cents": amount, "mock_mode": payments.MOCK_MODE}


    @r.post("/payments/{payment_id}/mock-confirm")
    async def mock_confirm_payment(payment_id: str, user=Depends(get_current_user)):
        """DEV ONLY — simulates a successful Stripe webhook when running in MOCK_MODE.
        In production, Stripe hits /stripe/webhooks and moves the state forward."""
        if not payments.MOCK_MODE:
            raise HTTPException(status_code=400, detail="Endpoint disponible uniquement en MOCK_MODE")
        p = await db.payments.find_one({"payment_id": payment_id}, {"_id": 0})
        if not p:
            raise HTTPException(status_code=404, detail="Paiement introuvable")
        await db.payments.update_one({"payment_id": payment_id}, {"$set": {"status": "succeeded", "confirmed_at": payments.now_utc_iso()}})
        await db.escrows.update_one({"payment_id": payment_id}, {"$set": {"state": "held", "held_at": payments.now_utc_iso()}})
        await payments.audit(db, user["user_id"], "payment.succeeded", payment_id, {"mock": True})
        return {"ok": True, "status": "succeeded"}


    @r.get("/escrows/mine")
    async def my_escrows(user=Depends(get_current_user)):
        if user.get("role") == "artisan":
            prof = await db.artisan_profiles.find_one({"user_id": user["user_id"]}, {"_id": 0})
            if not prof:
                return []
            rows = await db.escrows.find({"artisan_id": prof["artisan_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
        else:
            rows = await db.escrows.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
            # filter to those on this client's bookings
            booking_ids = [r["booking_id"] for r in rows]
            clients = {b["booking_id"]: b["client_id"] async for b in db.bookings.find({"booking_id": {"$in": booking_ids}}, {"_id": 0, "booking_id": 1, "client_id": 1})}
            rows = [r for r in rows if clients.get(r["booking_id"]) == user["user_id"]]
        return rows


    @r.post("/escrow/{booking_id}/release")
    async def escrow_release(booking_id: str, user=Depends(get_current_user)):
        booking = await db.bookings.find_one({"booking_id": booking_id, "client_id": user["user_id"]}, {"_id": 0})
        if not booking:
            raise HTTPException(status_code=404, detail="Réservation introuvable")
        escrow = await db.escrows.find_one({"booking_id": booking_id}, {"_id": 0})
        if not escrow:
            raise HTTPException(status_code=404, detail="Escrow introuvable")
        if escrow["state"] != "held":
            raise HTTPException(status_code=400, detail=f"Escrow en état '{escrow['state']}', ne peut pas être libéré")

        artisan = await db.artisan_profiles.find_one({"artisan_id": booking["artisan_id"]}, {"_id": 0}) or {}
        connected = await db.stripe_accounts.find_one({"artisan_id": booking["artisan_id"]}, {"_id": 0})
        if not connected:
            raise HTTPException(status_code=400, detail="L'artisan n'a pas encore configuré Stripe Connect")

        bps = await payments.resolve_commission_bps(db, artisan)
        fee = payments.commission_amount(escrow["amount_cents"], bps)
        net = escrow["amount_cents"] - fee

        transfer = payments.create_transfer(
            amount_cents=net,
            currency=escrow.get("currency", "eur"),
            destination=connected["stripe_account_id"],
            transfer_group=booking_id,
            metadata={"booking_id": booking_id, "artisan_id": booking["artisan_id"]},
        )
        await db.transfers.insert_one({
            "transfer_id": new_id("tr"),
            "stripe_transfer_id": transfer["id"],
            "booking_id": booking_id,
            "escrow_id": escrow["escrow_id"],
            "artisan_id": booking["artisan_id"],
            "gross_cents": escrow["amount_cents"],
            "commission_bps": bps,
            "commission_cents": fee,
            "net_cents": net,
            "created_at": payments.now_utc_iso(),
        })
        await db.escrows.update_one({"escrow_id": escrow["escrow_id"]}, {"$set": {
            "state": "released",
            "released_at": payments.now_utc_iso(),
            "commission_bps": bps,
            "commission_cents": fee,
            "net_cents": net,
            "stripe_transfer_id": transfer["id"],
        }})
        await payments.audit(db, user["user_id"], "escrow.released", escrow["escrow_id"], {
            "gross_cents": escrow["amount_cents"], "commission_cents": fee, "net_cents": net,
        })
        return {"ok": True, "gross_cents": escrow["amount_cents"], "commission_cents": fee, "net_cents": net, "transfer_id": transfer["id"]}


    @r.post("/escrow/{booking_id}/refund")
    async def escrow_refund(booking_id: str, body: RefundInput, user=Depends(get_current_user)):
        booking = await db.bookings.find_one({"booking_id": booking_id, "client_id": user["user_id"]}, {"_id": 0})
        if not booking:
            raise HTTPException(status_code=404, detail="Réservation introuvable")
        escrow = await db.escrows.find_one({"booking_id": booking_id}, {"_id": 0})
        payment = await db.payments.find_one({"booking_id": booking_id, "status": "succeeded"}, {"_id": 0})
        if not escrow or not payment:
            raise HTTPException(status_code=404, detail="Paiement introuvable")
        if escrow["state"] not in ("held", "frozen"):
            raise HTTPException(status_code=400, detail=f"Escrow en état '{escrow['state']}', non remboursable")
        refund_amount = body.amount_cents or escrow["amount_cents"]
        refund = payments.refund_payment(payment["stripe_payment_intent_id"], refund_amount, body.reason)
        await db.refunds.insert_one({
            "refund_id": new_id("ref"),
            "stripe_refund_id": refund["id"],
            "payment_id": payment["payment_id"],
            "booking_id": booking_id,
            "amount_cents": refund_amount,
            "reason": body.reason,
            "created_at": payments.now_utc_iso(),
        })
        await db.escrows.update_one({"escrow_id": escrow["escrow_id"]}, {"$set": {"state": "refunded", "refunded_at": payments.now_utc_iso()}})
        await payments.audit(db, user["user_id"], "escrow.refunded", escrow["escrow_id"], {"amount_cents": refund_amount, "reason": body.reason})
        return {"ok": True, "refund_id": refund["id"], "amount_cents": refund_amount}


    @r.post("/escrow/freeze")
    async def escrow_freeze(body: DisputeFreezeInput, user=Depends(get_current_user)):
        """Freeze an escrow when a dispute is opened. Only admins or the funds owner can freeze.
        The Trust Engine's POST /disputes should also call this internally for severe cases."""
        escrow = await db.escrows.find_one({"booking_id": body.booking_id}, {"_id": 0})
        if not escrow:
            raise HTTPException(status_code=404, detail="Escrow introuvable")
        booking = await db.bookings.find_one({"booking_id": body.booking_id}, {"_id": 0})
        is_admin = user.get("email", "").lower() in ADMIN_EMAILS
        is_owner = booking and booking.get("client_id") == user["user_id"]
        if not (is_admin or is_owner):
            raise HTTPException(status_code=403, detail="Non autorisé")
        if escrow["state"] != "held":
            raise HTTPException(status_code=400, detail="Seuls les escrows 'held' peuvent être gelés")
        await db.escrows.update_one({"escrow_id": escrow["escrow_id"]}, {"$set": {
            "state": "frozen", "frozen_at": payments.now_utc_iso(), "freeze_reason": body.reason,
        }})
        await payments.audit(db, user["user_id"], "escrow.frozen", escrow["escrow_id"], {"reason": body.reason})
        return {"ok": True, "state": "frozen"}


    @r.post("/interventions/{iv_id}/deposit/create")
    async def create_deposit_intent(iv_id: str, data: DepositIntentInput, user=Depends(get_current_user)):
        iv = await db.interventions.find_one({"intervention_id": iv_id})
        if not iv:
            raise HTTPException(status_code=404, detail="Intervention introuvable")
        if iv.get("client_id") != user["user_id"]:
            raise HTTPException(status_code=403, detail="Réservé au client")
        if iv.get("status") not in ("accepted",):
            raise HTTPException(status_code=400, detail="L'artisan doit d'abord accepter la demande")
        if iv.get("deposit_status") == "paid":
            return {"already_paid": True, "amount_cents": iv.get("deposit_amount_cents")}

        amount_cents = _compute_deposit_cents(iv)
        pi = payments.create_payment_intent(
            amount_cents=amount_cents,
            currency="eur",
            metadata={"intervention_id": iv_id, "client_id": user["user_id"], "artisan_id": iv.get("artisan_id", "")},
            customer_email=user.get("email"),
        )
        await db.interventions.update_one(
            {"intervention_id": iv_id},
            {"$set": {
                "deposit_status": "pending",
                "deposit_amount_cents": amount_cents,
                "deposit_currency": "eur",
                "deposit_payment_intent_id": pi["id"],
                "deposit_created_at": now_utc().isoformat(),
            }},
        )
        await security.audit_log(
            db, action="intervention.deposit_created",
            actor_id=user["user_id"], actor_role=user.get("role"),
            target=iv_id, metadata={"amount_cents": amount_cents}, severity="info",
        )
        return {
            "client_secret": pi.get("client_secret"),
            "payment_intent_id": pi["id"],
            "amount_cents": amount_cents,
            "currency": "eur",
            "mock": pi.get("client_secret", "").endswith("_secret_mock"),
        }



    @r.post("/interventions/{iv_id}/deposit/confirm")
    async def confirm_deposit(iv_id: str, data: DepositConfirmInput, user=Depends(get_current_user)):
        """Frontend calls this after Stripe Payment Sheet returns success.
        In mock mode, this is called directly since the fake PI never confirms via webhook.
        """
        iv = await db.interventions.find_one({"intervention_id": iv_id})
        if not iv:
            raise HTTPException(status_code=404, detail="Intervention introuvable")
        if iv.get("client_id") != user["user_id"]:
            raise HTTPException(status_code=403, detail="Réservé au client")
        if iv.get("deposit_status") == "paid":
            return {"ok": True, "already_paid": True}

        await db.interventions.update_one(
            {"intervention_id": iv_id},
            {"$set": {
                "deposit_status": "paid",
                "deposit_paid_at": now_utc().isoformat(),
                "status": "confirmed",
                "escrow_deposit_state": "held",
            }},
        )
        await security.audit_log(
            db, action="intervention.deposit_paid",
            actor_id=user["user_id"], actor_role=user.get("role"),
            target=iv_id, metadata={"amount_cents": iv.get("deposit_amount_cents")}, severity="critical",
        )
        return {"ok": True, "status": "confirmed"}



    @r.post("/interventions/{iv_id}/start")
    async def start_intervention(iv_id: str, user=Depends(get_current_user)):
        """Artisan marks intervention as in progress (arrived on site)."""
        iv = await db.interventions.find_one({"intervention_id": iv_id})
        if not iv:
            raise HTTPException(status_code=404, detail="Introuvable")
        if iv.get("artisan_user_id") != user["user_id"]:
            raise HTTPException(status_code=403, detail="Réservé à l'artisan")
        if iv.get("status") != "confirmed":
            raise HTTPException(status_code=400, detail="Le paiement d'acompte doit être effectué avant")
        await db.interventions.update_one(
            {"intervention_id": iv_id},
            {"$set": {"status": "in_progress", "started_at": now_utc().isoformat()}},
        )
        await security.audit_log(db, action="intervention.started", actor_id=user["user_id"], target=iv_id, severity="info")
        return {"ok": True, "status": "in_progress"}



    @r.post("/interventions/{iv_id}/finish")
    async def finish_intervention(iv_id: str, data: InterventionFinalInput, user=Depends(get_current_user)):
        """Artisan marks intervention as finished with the final total amount.
        Client will then be prompted to pay the balance (final - deposit).
        """
        iv = await db.interventions.find_one({"intervention_id": iv_id})
        if not iv:
            raise HTTPException(status_code=404, detail="Introuvable")
        if iv.get("artisan_user_id") != user["user_id"]:
            raise HTTPException(status_code=403, detail="Réservé à l'artisan")
        if iv.get("status") not in ("in_progress", "confirmed"):
            raise HTTPException(status_code=400, detail="État invalide")
        deposit = iv.get("deposit_amount_cents", 0)
        if data.total_amount_cents < deposit:
            raise HTTPException(status_code=400, detail="Le total doit couvrir au moins l'acompte")
        balance = data.total_amount_cents - deposit
        await db.interventions.update_one(
            {"intervention_id": iv_id},
            {"$set": {
                "status": "awaiting_final_payment" if balance > 0 else "awaiting_validation",
                "total_amount_cents": data.total_amount_cents,
                "balance_cents": balance,
                "finished_at": now_utc().isoformat(),
            }},
        )
        await security.audit_log(
            db, action="intervention.finished",
            actor_id=user["user_id"], target=iv_id,
            metadata={"total_cents": data.total_amount_cents, "balance_cents": balance}, severity="info",
        )
        return {"ok": True, "total_cents": data.total_amount_cents, "balance_cents": balance}



    @r.post("/interventions/{iv_id}/final/create")
    async def create_final_payment(iv_id: str, user=Depends(get_current_user)):
        """Create a PaymentIntent for the balance (total - deposit)."""
        iv = await db.interventions.find_one({"intervention_id": iv_id})
        if not iv:
            raise HTTPException(status_code=404, detail="Introuvable")
        if iv.get("client_id") != user["user_id"]:
            raise HTTPException(status_code=403, detail="Réservé au client")
        if iv.get("status") != "awaiting_final_payment":
            raise HTTPException(status_code=400, detail="État invalide")
        balance = iv.get("balance_cents", 0)
        if balance <= 0:
            return {"already_paid": True}
        pi = payments.create_payment_intent(
            amount_cents=balance,
            currency="eur",
            metadata={"intervention_id": iv_id, "type": "final", "artisan_id": iv.get("artisan_id", "")},
            customer_email=user.get("email"),
        )
        await db.interventions.update_one(
            {"intervention_id": iv_id},
            {"$set": {"final_payment_intent_id": pi["id"], "final_status": "pending"}},
        )
        return {
            "client_secret": pi.get("client_secret"),
            "payment_intent_id": pi["id"],
            "amount_cents": balance,
            "currency": "eur",
            "mock": pi.get("client_secret", "").endswith("_secret_mock"),
        }



    @r.post("/interventions/{iv_id}/final/confirm")
    async def confirm_final_payment(iv_id: str, user=Depends(get_current_user)):
        iv = await db.interventions.find_one({"intervention_id": iv_id})
        if not iv:
            raise HTTPException(status_code=404, detail="Introuvable")
        if iv.get("client_id") != user["user_id"]:
            raise HTTPException(status_code=403, detail="Réservé au client")
        await db.interventions.update_one(
            {"intervention_id": iv_id},
            {"$set": {
                "final_status": "paid",
                "final_paid_at": now_utc().isoformat(),
                "status": "awaiting_validation",
            }},
        )
        await security.audit_log(
            db, action="intervention.final_paid",
            actor_id=user["user_id"], target=iv_id,
            metadata={"amount_cents": iv.get("balance_cents")}, severity="critical",
        )
        return {"ok": True, "status": "awaiting_validation"}



    @r.post("/interventions/{iv_id}/validate")
    async def validate_intervention(iv_id: str, user=Depends(get_current_user)):
        """Client validates the completed work → escrow is released to artisan via Stripe Connect Transfer."""
        iv = await db.interventions.find_one({"intervention_id": iv_id})
        if not iv:
            raise HTTPException(status_code=404, detail="Introuvable")
        if iv.get("client_id") != user["user_id"]:
            raise HTTPException(status_code=403, detail="Réservé au client")
        if iv.get("status") not in ("awaiting_validation", "awaiting_final_payment"):
            raise HTTPException(status_code=400, detail="État invalide")

        artisan_profile = await db.artisan_profiles.find_one({"artisan_id": iv.get("artisan_id")}, {"_id": 0}) or {}
        connected = await db.stripe_accounts.find_one({"artisan_id": iv.get("artisan_id")}, {"_id": 0})
        total = iv.get("total_amount_cents") or iv.get("deposit_amount_cents") or 0

        result: Dict[str, Any] = {"ok": True, "status": "completed", "total_cents": total}

        if connected and total > 0:
            bps = await payments.resolve_commission_bps(db, artisan_profile)
            fee = payments.commission_amount(total, bps)
            net = total - fee
            transfer = payments.create_transfer(
                amount_cents=net,
                currency="eur",
                destination=connected["stripe_account_id"],
                transfer_group=iv_id,
                metadata={"intervention_id": iv_id, "artisan_id": iv.get("artisan_id", "")},
            )
            await db.transfers.insert_one({
                "transfer_id": new_id("tr"),
                "stripe_transfer_id": transfer["id"],
                "intervention_id": iv_id,
                "artisan_id": iv.get("artisan_id"),
                "gross_cents": total,
                "commission_bps": bps,
                "commission_cents": fee,
                "net_cents": net,
                "created_at": now_utc().isoformat(),
            })
            result.update({"commission_cents": fee, "net_cents": net, "transfer_id": transfer["id"], "commission_bps": bps})
        else:
            result.update({"note": "Aucun transfert Stripe Connect (artisan non connecté ou montant nul)"})

        await db.interventions.update_one(
            {"intervention_id": iv_id},
            {"$set": {
                "status": "completed",
                "completed_at": now_utc().isoformat(),
                "escrow_deposit_state": "released",
                **({"commission_cents": result.get("commission_cents"), "net_paid_cents": result.get("net_cents")} if "net_cents" in result else {}),
            }},
        )
        await security.audit_log(
            db, action="intervention.validated_and_transferred",
            actor_id=user["user_id"], target=iv_id,
            metadata={k: v for k, v in result.items() if k != "ok"}, severity="critical",
        )
        return result



    @r.get("/interventions/{iv_id}/payment-summary")
    async def intervention_payment_summary(iv_id: str, user=Depends(get_current_user)):
        iv = await db.interventions.find_one({"intervention_id": iv_id}, {"_id": 0})
        if not iv:
            raise HTTPException(status_code=404, detail="Introuvable")
        if user["user_id"] not in (iv.get("client_id"), iv.get("artisan_user_id")):
            raise HTTPException(status_code=403, detail="Accès refusé")
        deposit = iv.get("deposit_amount_cents", 0)
        total = iv.get("total_amount_cents", 0)
        balance = iv.get("balance_cents", 0)
        return {
            "deposit_cents": deposit,
            "total_cents": total,
            "balance_cents": balance,
            "deposit_status": iv.get("deposit_status"),
            "final_status": iv.get("final_status"),
            "status": iv.get("status"),
            "commission_cents": iv.get("commission_cents"),
            "net_paid_cents": iv.get("net_paid_cents"),
        }


        event_date: str = Field(..., description="ISO date YYYY-MM-DD")



    return r
