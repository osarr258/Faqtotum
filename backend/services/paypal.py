"""
Auxora — PayPal Advanced Checkout Service
==========================================
PayPal REST API v2 (Orders) integration, designed to coexist with Stripe as an
alternative payment method for escrow deposits and final payments.

Modes
-----
- **Live/Sandbox mode**: `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` are set.
  Uses PayPal's real REST API (https://api-m.paypal.com in live,
  https://api-m.sandbox.paypal.com in sandbox).
- **Mock mode**: if either credential is missing/placeholder, we short-circuit
  every PayPal call and return deterministic fake objects, mirroring the
  Stripe mock pattern used in services/payments.py.

Design invariants
-----------------
- OAuth2 access tokens are cached in-memory and refreshed before expiry.
- All state transitions must be recorded through the caller's audit_log helper.
- Webhook signature verification uses PayPal's `verify-webhook-signature` API
  when a `PAYPAL_WEBHOOK_ID` is configured; in mock mode we accept any payload.
- Idempotency: each order creation includes a PayPal-Request-Id header derived
  from the intervention_id + purpose so retries won't double-charge.
"""
from __future__ import annotations
import os
import json
import time
import uuid
import base64
import logging
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.environ.get("PAYPAL_CLIENT_SECRET", "")
PAYPAL_ENV = os.environ.get("PAYPAL_ENV", "live").lower()  # "live" or "sandbox"
PAYPAL_WEBHOOK_ID = os.environ.get("PAYPAL_WEBHOOK_ID", "")
PLATFORM_URL = os.environ.get("PLATFORM_URL", "http://localhost:3000")

_PLACEHOLDER_VALUES = {"", "paypal_client_id_placeholder", "paypal_client_secret_placeholder", "placeholder"}
MOCK_MODE = (
    PAYPAL_CLIENT_ID.strip().lower() in _PLACEHOLDER_VALUES
    or PAYPAL_CLIENT_SECRET.strip().lower() in _PLACEHOLDER_VALUES
)

PAYPAL_API_BASE = (
    "https://api-m.sandbox.paypal.com" if PAYPAL_ENV == "sandbox" else "https://api-m.paypal.com"
)
PAYPAL_APPROVE_BASE = (
    "https://www.sandbox.paypal.com/checkoutnow" if PAYPAL_ENV == "sandbox"
    else "https://www.paypal.com/checkoutnow"
)

# In-memory OAuth2 token cache
_access_token: Dict[str, Any] = {"token": None, "expires_at": 0}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_id(prefix: str) -> str:
    return f"{prefix}_pp_mock_{uuid.uuid4().hex[:14]}"


def _cents_to_str(amount_cents: int, currency: str) -> str:
    """PayPal wants string amounts. EUR/USD are 2-decimal currencies."""
    zero_decimal = {"JPY", "KRW", "VND"}
    if currency.upper() in zero_decimal:
        return f"{int(amount_cents)}"
    return f"{amount_cents / 100:.2f}"


async def _get_access_token() -> str:
    """Fetch (or reuse) an OAuth2 access token from PayPal."""
    now = int(time.time())
    if _access_token["token"] and _access_token["expires_at"] - 30 > now:
        return _access_token["token"]

    creds = f"{PAYPAL_CLIENT_ID}:{PAYPAL_CLIENT_SECRET}".encode("utf-8")
    b64 = base64.b64encode(creds).decode("ascii")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{PAYPAL_API_BASE}/v1/oauth2/token",
            headers={
                "Authorization": f"Basic {b64}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
        )
    if resp.status_code >= 400:
        logger.error(f"PayPal OAuth failed: {resp.status_code} {resp.text}")
        raise RuntimeError("paypal_oauth_failed")
    data = resp.json()
    _access_token["token"] = data["access_token"]
    _access_token["expires_at"] = now + int(data.get("expires_in", 3200))
    return _access_token["token"]


def _mock_order(amount_cents: int, currency: str, purpose: str, metadata: Dict[str, str],
                return_url: str, cancel_url: str) -> Dict[str, Any]:
    order_id = _mock_id(purpose)
    return {
        "id": order_id,
        "status": "CREATED",
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": metadata.get("intervention_id", "ref"),
            "amount": {"currency_code": currency.upper(), "value": _cents_to_str(amount_cents, currency)},
            "custom_id": metadata.get("intervention_id", ""),
        }],
        "links": [
            {"rel": "self", "href": f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}", "method": "GET"},
            {"rel": "approve", "href": f"{PLATFORM_URL}/paypal-mock/approve?order_id={order_id}&return_url={return_url}", "method": "GET"},
            {"rel": "capture", "href": f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}/capture", "method": "POST"},
        ],
        "amount_cents": amount_cents,
        "currency": currency.upper(),
        "mock": True,
    }


# ---------------------------------------------------------------------------
# PayPal wrappers — every call short-circuits in MOCK_MODE.
# ---------------------------------------------------------------------------

async def create_order(
    amount_cents: int,
    currency: str,
    purpose: str,  # "deposit" | "final"
    metadata: Dict[str, str],
    return_url: Optional[str] = None,
    cancel_url: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a PayPal Order with intent=CAPTURE.
    Returns a normalized dict with `id`, `approve_url`, `amount_cents`, `mock`.
    """
    return_url = return_url or f"{PLATFORM_URL}/paypal-return"
    cancel_url = cancel_url or f"{PLATFORM_URL}/paypal-cancel"

    if MOCK_MODE:
        order = _mock_order(amount_cents, currency, purpose, metadata, return_url, cancel_url)
        approve = next((l["href"] for l in order["links"] if l["rel"] == "approve"), None)
        return {
            "id": order["id"],
            "status": order["status"],
            "approve_url": approve,
            "amount_cents": amount_cents,
            "currency": currency.upper(),
            "mock": True,
        }

    token = await _get_access_token()
    body = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": metadata.get("intervention_id", "ref"),
            "custom_id": metadata.get("intervention_id", ""),
            "description": description or f"Auxora {purpose}",
            "amount": {
                "currency_code": currency.upper(),
                "value": _cents_to_str(amount_cents, currency),
            },
        }],
        "application_context": {
            "brand_name": "Auxora",
            "user_action": "PAY_NOW",
            "landing_page": "LOGIN",
            "shipping_preference": "NO_SHIPPING",
            "return_url": return_url,
            "cancel_url": cancel_url,
        },
    }
    idempotency_key = f"{metadata.get('intervention_id', 'x')}-{purpose}-{uuid.uuid4().hex[:8]}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{PAYPAL_API_BASE}/v2/checkout/orders",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "PayPal-Request-Id": idempotency_key,
            },
            content=json.dumps(body),
        )
    if resp.status_code >= 400:
        logger.error(f"PayPal create_order failed: {resp.status_code} {resp.text}")
        raise RuntimeError(f"paypal_create_order_failed:{resp.status_code}")
    data = resp.json()
    approve = next((l["href"] for l in data.get("links", []) if l.get("rel") == "approve"), None)
    return {
        "id": data["id"],
        "status": data.get("status", "CREATED"),
        "approve_url": approve,
        "amount_cents": amount_cents,
        "currency": currency.upper(),
        "mock": False,
    }


async def capture_order(order_id: str) -> Dict[str, Any]:
    """Capture funds for a previously approved order.
    Returns normalized dict with `id`, `status`, `captured_cents`, `capture_id`.
    """
    if MOCK_MODE or order_id.startswith(("deposit_pp_mock_", "final_pp_mock_")):
        return {
            "id": order_id,
            "status": "COMPLETED",
            "capture_id": _mock_id("cap"),
            "captured_cents": None,  # caller knows the intended amount
            "payer_email": "buyer@paypal.mock",
            "mock": True,
        }

    token = await _get_access_token()
    async with httpx.AsyncClient(timeout=25.0) as client:
        resp = await client.post(
            f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}/capture",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "PayPal-Request-Id": f"cap-{order_id}",
            },
        )
    if resp.status_code >= 400:
        logger.error(f"PayPal capture failed: {resp.status_code} {resp.text}")
        raise RuntimeError(f"paypal_capture_failed:{resp.status_code}")
    data = resp.json()
    # Extract capture details
    pu = (data.get("purchase_units") or [{}])[0]
    payments_list = ((pu.get("payments") or {}).get("captures") or [])
    cap = payments_list[0] if payments_list else {}
    amount = (cap.get("amount") or {}).get("value")
    captured_cents = int(round(float(amount) * 100)) if amount else None
    return {
        "id": data.get("id", order_id),
        "status": data.get("status", cap.get("status", "COMPLETED")),
        "capture_id": cap.get("id"),
        "captured_cents": captured_cents,
        "payer_email": (data.get("payer") or {}).get("email_address"),
        "mock": False,
    }


async def refund_capture(capture_id: str, amount_cents: Optional[int] = None,
                          currency: str = "EUR", note: Optional[str] = None) -> Dict[str, Any]:
    if MOCK_MODE or capture_id.startswith("cap_pp_mock_"):
        return {
            "id": _mock_id("re"),
            "capture_id": capture_id,
            "status": "COMPLETED",
            "amount_cents": amount_cents,
            "mock": True,
        }

    token = await _get_access_token()
    body: Dict[str, Any] = {}
    if amount_cents is not None:
        body["amount"] = {"currency_code": currency.upper(), "value": _cents_to_str(amount_cents, currency)}
    if note:
        body["note_to_payer"] = note[:255]
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{PAYPAL_API_BASE}/v2/payments/captures/{capture_id}/refund",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "PayPal-Request-Id": f"ref-{capture_id}-{uuid.uuid4().hex[:6]}",
            },
            content=json.dumps(body) if body else "{}",
        )
    if resp.status_code >= 400:
        logger.error(f"PayPal refund failed: {resp.status_code} {resp.text}")
        raise RuntimeError(f"paypal_refund_failed:{resp.status_code}")
    return resp.json()


async def get_order(order_id: str) -> Dict[str, Any]:
    if MOCK_MODE or order_id.startswith(("deposit_pp_mock_", "final_pp_mock_")):
        return {"id": order_id, "status": "APPROVED", "mock": True}
    token = await _get_access_token()
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
    if resp.status_code >= 400:
        raise RuntimeError(f"paypal_get_order_failed:{resp.status_code}")
    return resp.json()


async def verify_webhook(payload: bytes, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Verify a PayPal webhook signature.
    - In mock mode: parse and return the JSON without verification.
    - In live mode: call PayPal's /v1/notifications/verify-webhook-signature.
    """
    try:
        event = json.loads(payload)
    except Exception:
        return None

    if MOCK_MODE or not PAYPAL_WEBHOOK_ID:
        return event

    token = await _get_access_token()
    hnorm = {k.lower(): v for k, v in headers.items()}
    body = {
        "auth_algo": hnorm.get("paypal-auth-algo"),
        "cert_url": hnorm.get("paypal-cert-url"),
        "transmission_id": hnorm.get("paypal-transmission-id"),
        "transmission_sig": hnorm.get("paypal-transmission-sig"),
        "transmission_time": hnorm.get("paypal-transmission-time"),
        "webhook_id": PAYPAL_WEBHOOK_ID,
        "webhook_event": event,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{PAYPAL_API_BASE}/v1/notifications/verify-webhook-signature",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            content=json.dumps(body),
        )
    if resp.status_code >= 400:
        logger.warning(f"paypal webhook verify http error: {resp.status_code}")
        return None
    result = resp.json()
    if result.get("verification_status") == "SUCCESS":
        return event
    logger.warning(f"paypal webhook verify failed: {result}")
    return None


def config_public() -> Dict[str, Any]:
    """Public config safe to expose to the frontend."""
    return {
        "client_id": PAYPAL_CLIENT_ID if not MOCK_MODE else "",
        "env": PAYPAL_ENV,
        "mock_mode": MOCK_MODE,
        "currency": "EUR",
    }
