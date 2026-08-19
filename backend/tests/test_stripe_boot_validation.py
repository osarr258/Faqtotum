"""
V1 Sprint 1 — Stripe integration boot validation (structural safeguard).

Verifies:
- In DEV: MOCK_MODE is auto-inferred from the STRIPE_API_KEY prefix.
- In PRODUCTION: the process refuses to boot if:
    * STRIPE_API_KEY is missing / not `sk_live_*`
    * STRIPE_WEBHOOK_SECRET is missing / not `whsec_*`
    * STRIPE_PUBLISHABLE_KEY is not `pk_live_*`
- The current dev deploy has REAL test-mode keys (MOCK_MODE=False).
"""
from __future__ import annotations
import subprocess
import os


def _run_boot(env_overrides: dict) -> subprocess.CompletedProcess:
    env = {
        k: v for k, v in os.environ.items()
        if k in ("MONGO_URL", "DB_NAME", "EMERGENT_LLM_KEY", "PATH", "PYTHONPATH")
    }
    env.update({
        "ALLOWED_ORIGINS": "https://faqtotum.example.com",
        "APPLE_AUDIENCES_PROD": "com.faqtotum.app",
        "MFA_ENCRYPTION_KEY": "aTBmk1uEQBoBt8j2rW1Fx1FqDGnKzYbCPiE-hh17MK4=",
        **env_overrides,
    })
    return subprocess.run(
        ["python", "-c",
         "import sys; sys.path.insert(0, '/app/backend'); "
         "from services import payments"],
        env=env, capture_output=True, text=True, timeout=15,
    )


def test_current_dev_has_real_test_mode_keys():
    """The running dev env has real sk_test_ keys, so MOCK_MODE is off.

    Uses a clean subprocess so a stale shell env (which sometimes carries
    the old `sk_test_emergent` placeholder) cannot mask the .env value.
    """
    p = _run_boot({
        "APP_ENV": "development",
        # DO NOT set STRIPE_* here — force .env-only resolution.
    })
    assert p.returncode == 0
    # Cross-check the running server too via a lightweight import.
    p2 = subprocess.run(
        ["python", "-c",
         "import sys; sys.path.insert(0, '/app/backend'); "
         "from services import payments; "
         "print(payments.STRIPE_API_KEY[:12], payments.MOCK_MODE)"],
        env={
            k: v for k, v in os.environ.items()
            if k in ("MONGO_URL", "DB_NAME", "PATH", "PYTHONPATH")
        },
        capture_output=True, text=True, timeout=15,
    )
    out = p2.stdout.strip()
    assert out.startswith("sk_test_51"), f"expected sk_test_51 prefix, got {out!r}"
    assert "False" in out


def test_prod_refuses_missing_api_key():
    p = _run_boot({"APP_ENV": "production", "STRIPE_API_KEY": ""})
    assert p.returncode != 0
    combined = (p.stderr + p.stdout).lower()
    assert "stripe_api_key" in combined


def test_prod_refuses_test_key_in_live():
    p = _run_boot({
        "APP_ENV": "production",
        "STRIPE_API_KEY": "sk_test_51U5YY2XXX",
        "STRIPE_WEBHOOK_SECRET": "whsec_x",
        "STRIPE_PUBLISHABLE_KEY": "pk_live_x",
    })
    assert p.returncode != 0
    assert "sk_live_" in (p.stderr + p.stdout).lower()


def test_prod_refuses_missing_webhook_secret():
    p = _run_boot({
        "APP_ENV": "production",
        "STRIPE_API_KEY": "sk_live_x",
        "STRIPE_WEBHOOK_SECRET": "",
        "STRIPE_PUBLISHABLE_KEY": "pk_live_x",
    })
    assert p.returncode != 0
    assert "webhook" in (p.stderr + p.stdout).lower()


def test_prod_refuses_wrong_publishable_key():
    p = _run_boot({
        "APP_ENV": "production",
        "STRIPE_API_KEY": "sk_live_x",
        "STRIPE_WEBHOOK_SECRET": "whsec_x",
        "STRIPE_PUBLISHABLE_KEY": "pk_test_x",
    })
    assert p.returncode != 0
    assert "publishable" in (p.stderr + p.stdout).lower()


def test_prod_accepts_valid_live_config():
    """All prefixes correct → boot succeeds."""
    p = _run_boot({
        "APP_ENV": "production",
        "STRIPE_API_KEY": "sk_live_placeholder_never_used",
        "STRIPE_WEBHOOK_SECRET": "whsec_placeholder",
        "STRIPE_PUBLISHABLE_KEY": "pk_live_placeholder",
    })
    assert p.returncode == 0, f"expected 0, got {p.returncode}. stderr={p.stderr!r}"


def test_dev_tolerates_missing_stripe():
    """Dev mode must NOT block startup when Stripe is unconfigured."""
    p = _run_boot({
        "APP_ENV": "development",
        "STRIPE_API_KEY": "",
        "STRIPE_WEBHOOK_SECRET": "",
        "STRIPE_PUBLISHABLE_KEY": "",
    })
    assert p.returncode == 0
