"""
ProConnect / Auxora — Payments & Escrow Service
================================================
Production-ready Stripe Connect (Express) integration for a marketplace with
escrow. Uses the "Separate charges and transfers" pattern: the customer pays
the platform, the platform holds the funds until the customer validates the
mission, and then transfers the net amount to the professional (minus the
platform commission).

Modes
-----
- **Live/Test mode**: `STRIPE_API_KEY` is a real Stripe key (`sk_test_...` or
  `sk_live_...`). Every call hits Stripe's API.
- **Mock mode**: if the key is the placeholder `sk_test_emergent`, this module
  short-circuits every Stripe call and returns deterministic fake objects.
  Lets us ship the entire escrow/subscription state machine without needing
  real API credentials during development. Real keys switch the app to live
  behaviour with zero code changes.

Design invariants
-----------------
- The **platform** owns the funds until an explicit `release()` call.
- Commissions are **configurable at runtime** via `platform_config` and
  `commission_rules` (global, trade-specific, promo, exemptions).
- Ranking (matching.py) is **never** biased by subscription tier — this file
  is intentionally decoupled from matching.
- Every state transition writes to `audit_logs` for compliance.
- Stripe webhooks are **idempotent** via the `stripe_events` collection.
"""
from __future__ import annotations
import os
import uuid
import time
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

import stripe

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
PLATFORM_URL = os.environ.get("PLATFORM_URL", "http://localhost:3000")

MOCK_MODE = STRIPE_API_KEY in ("", "sk_test_emergent", "sk_test_placeholder")

if not MOCK_MODE:
    stripe.api_key = STRIPE_API_KEY

# Default commission (basis points). 10.0% = 1000 bps.
DEFAULT_COMMISSION_BPS = 1000
DEFAULT_COMMISSION_MIN_CENTS = 200  # 2€ minimum

# Subscription plans catalog — Stripe price IDs live in .env so we never hard
# code prod IDs. Ranking is never influenced by these tiers.
PLANS: List[Dict[str, Any]] = [
    {
        "key": "starter",
        "name": "Starter",
        "price_cents": 0,
        "period": "month",
        "stripe_price_id": os.environ.get("STRIPE_PRICE_STARTER", ""),
        "features": [
            "Profil pro basique",
            "Recevoir des demandes",
            "Réponse aux avis",
        ],
    },
    {
        "key": "professional",
        "name": "Professional",
        "price_cents": 2900,
        "period": "month",
        "stripe_price_id": os.environ.get("STRIPE_PRICE_PROFESSIONAL", ""),
        "features": [
            "Statistiques avancées",
            "Support prioritaire",
            "Page pro personnalisée",
            "Synchronisation calendrier",
            "Boost visibilité modéré",
        ],
    },
    {
        "key": "enterprise",
        "name": "Enterprise",
        "price_cents": 7900,
        "period": "month",
        "stripe_price_id": os.environ.get("STRIPE_PRICE_ENTERPRISE", ""),
        "features": [
            "Statistiques avancées + exports",
            "Outils marketing intégrés",
            "Analytics business complet",
            "Support dédié 24/7",
            "Outils IA (bientôt disponible)",
            "API partenaire",
        ],
    },
]

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _mock_id(prefix: str) -> str:
    return f"{prefix}_mock_{uuid.uuid4().hex[:14]}"

# ---------------------------------------------------------------------------
# Commissions — configurable rules with priority resolution
# ---------------------------------------------------------------------------

async def resolve_commission_bps(db, artisan: Dict[str, Any]) -> int:
    """Resolve the commission (basis points) that applies to this artisan.

    Precedence (higher wins, first match returned):
        exemption > promo (active) > trade-specific > global
    """
    # 1. Exemption — artisan-specific 0% or reduced.
    exempt = await db.commission_rules.find_one(
        {"kind": "exemption", "artisan_id": artisan.get("artisan_id"), "active": True}
    )
    if exempt:
        return int(exempt["bps"])

    # 2. Active promo (start_at <= now <= end_at).
    now = now_utc_iso()
    promo = await db.commission_rules.find_one(
        {"kind": "promo", "active": True, "start_at": {"$lte": now}, "end_at": {"$gte": now}},
        sort=[("bps", 1)],  # lowest promo wins
    )
    if promo:
        return int(promo["bps"])

    # 3. Trade-specific.
    trade_rule = await db.commission_rules.find_one(
        {"kind": "trade", "trade": artisan.get("trade"), "active": True}
    )
    if trade_rule:
        return int(trade_rule["bps"])

    # 4. Global override from platform_config.
    cfg = await db.platform_config.find_one({"key": "commission"}, {"_id": 0})
    if cfg and "global_bps" in cfg:
        return int(cfg["global_bps"])

    return DEFAULT_COMMISSION_BPS

def commission_amount(gross_cents: int, bps: int, min_cents: int = DEFAULT_COMMISSION_MIN_CENTS) -> int:
    """Compute commission in cents. Never below the min floor."""
    calc = int(round(gross_cents * bps / 10000))
    return max(calc, min_cents)

# ---------------------------------------------------------------------------
# Stripe wrappers — every call short-circuits in MOCK_MODE.
# ---------------------------------------------------------------------------

def create_connect_account(email: str, country: str = "FR") -> Dict[str, Any]:
    if MOCK_MODE:
        return {
            "id": _mock_id("acct"),
            "email": email,
            "country": country,
            "charges_enabled": False,
            "payouts_enabled": False,
            "details_submitted": False,
            "requirements": {"currently_due": ["individual.first_name", "individual.last_name", "external_account"]},
            "capabilities": {"card_payments": "inactive", "transfers": "inactive"},
        }
    acc = stripe.Account.create(
        type="express",
        country=country,
        email=email,
        capabilities={"card_payments": {"requested": True}, "transfers": {"requested": True}},
    )
    return acc.to_dict()

def create_account_link(account_id: str, return_url: str, refresh_url: str) -> Dict[str, Any]:
    if MOCK_MODE:
        return {
            "url": f"{PLATFORM_URL}/connect/mock-onboarding?acct={account_id}",
            "expires_at": int(time.time()) + 300,
        }
    link = stripe.AccountLink.create(
        account=account_id,
        return_url=return_url,
        refresh_url=refresh_url,
        type="account_onboarding",
    )
    return link.to_dict()

def retrieve_account(account_id: str) -> Dict[str, Any]:
    if MOCK_MODE:
        # After the mock onboarding the account looks "verified".
        return {
            "id": account_id,
            "charges_enabled": True,
            "payouts_enabled": True,
            "details_submitted": True,
            "requirements": {"currently_due": []},
            "capabilities": {"card_payments": "active", "transfers": "active"},
        }
    return stripe.Account.retrieve(account_id).to_dict()

def create_payment_intent(amount_cents: int, currency: str, metadata: Dict[str, str],
                           customer_email: Optional[str] = None) -> Dict[str, Any]:
    """Create a PaymentIntent charged on the PLATFORM account (escrow model).

    We hold the money and later create a Transfer to the connected account
    once the customer validates the work. This is Stripe's recommended
    "Separate charges and transfers" flow.
    """
    if MOCK_MODE:
        pi_id = _mock_id("pi")
        return {
            "id": pi_id,
            "amount": amount_cents,
            "currency": currency,
            "status": "requires_confirmation",
            "client_secret": f"{pi_id}_secret_mock",
            "metadata": metadata,
            "receipt_email": customer_email,
            "automatic_payment_methods": {"enabled": True, "allow_redirects": "never"},
        }
    intent = stripe.PaymentIntent.create(
        amount=amount_cents,
        currency=currency,
        automatic_payment_methods={"enabled": True},  # includes card, Apple Pay, Google Pay
        metadata=metadata,
        receipt_email=customer_email,
        transfer_group=metadata.get("booking_id", metadata.get("mission_id", "")),
    )
    return intent.to_dict()

def create_transfer(amount_cents: int, currency: str, destination: str, transfer_group: str,
                     metadata: Dict[str, str]) -> Dict[str, Any]:
    """Move funds from the platform balance to a connected account."""
    if MOCK_MODE:
        return {
            "id": _mock_id("tr"),
            "amount": amount_cents,
            "currency": currency,
            "destination": destination,
            "transfer_group": transfer_group,
            "metadata": metadata,
            "created": int(time.time()),
        }
    tr = stripe.Transfer.create(
        amount=amount_cents,
        currency=currency,
        destination=destination,
        transfer_group=transfer_group,
        metadata=metadata,
    )
    return tr.to_dict()

def refund_payment(payment_intent_id: str, amount_cents: Optional[int] = None,
                    reason: Optional[str] = None) -> Dict[str, Any]:
    if MOCK_MODE:
        return {
            "id": _mock_id("re"),
            "payment_intent": payment_intent_id,
            "amount": amount_cents,
            "reason": reason,
            "status": "succeeded",
        }
    params: Dict[str, Any] = {"payment_intent": payment_intent_id}
    if amount_cents is not None:
        params["amount"] = amount_cents
    if reason:
        params["reason"] = reason
    return stripe.Refund.create(**params).to_dict()

def create_subscription(customer_id: str, price_id: str, metadata: Dict[str, str]) -> Dict[str, Any]:
    if MOCK_MODE:
        return {
            "id": _mock_id("sub"),
            "customer": customer_id,
            "status": "active",
            "current_period_end": int(time.time()) + 30 * 24 * 3600,
            "items": {"data": [{"price": {"id": price_id}}]},
            "metadata": metadata,
        }
    return stripe.Subscription.create(
        customer=customer_id,
        items=[{"price": price_id}],
        payment_behavior="default_incomplete",
        expand=["latest_invoice.payment_intent"],
        metadata=metadata,
    ).to_dict()

def cancel_subscription(subscription_id: str, at_period_end: bool = True) -> Dict[str, Any]:
    if MOCK_MODE:
        return {"id": subscription_id, "status": "canceled" if not at_period_end else "active",
                "cancel_at_period_end": at_period_end}
    if at_period_end:
        return stripe.Subscription.modify(subscription_id, cancel_at_period_end=True).to_dict()
    return stripe.Subscription.delete(subscription_id).to_dict()

def get_or_create_customer(email: str, name: str, metadata: Dict[str, str]) -> Dict[str, Any]:
    if MOCK_MODE:
        return {"id": _mock_id("cus"), "email": email, "name": name, "metadata": metadata}
    existing = stripe.Customer.list(email=email, limit=1)
    if existing.data:
        return existing.data[0].to_dict()
    return stripe.Customer.create(email=email, name=name, metadata=metadata).to_dict()

def verify_webhook(payload: bytes, sig_header: str) -> Optional[Dict[str, Any]]:
    if MOCK_MODE:
        # In mock mode, just parse the JSON directly (no signature verification).
        import json
        try:
            return json.loads(payload)
        except Exception:
            return None
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        return event.to_dict()
    except Exception as e:
        logger.warning(f"stripe webhook verify failed: {e}")
        return None

# ---------------------------------------------------------------------------
# Audit log helper — reused by server.py for compliance
# ---------------------------------------------------------------------------

async def audit(db, actor_id: Optional[str], action: str, resource: str,
                metadata: Optional[Dict[str, Any]] = None):
    await db.audit_logs.insert_one({
        "audit_id": _mock_id("log"),
        "actor_id": actor_id,
        "action": action,
        "resource": resource,
        "metadata": metadata or {},
        "created_at": now_utc_iso(),
    })
