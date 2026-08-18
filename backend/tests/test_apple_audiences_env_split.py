"""
V1 hardening — verify APPLE_AUDIENCES config is safe by environment.

Guarantees under test:
- Production MUST refuse to boot if `APPLE_AUDIENCES_PROD` contains the Expo
  Go audience `host.exp.Exponent`. The failure comes from
  `verify_apple_audiences_config()` at server startup.
- Production MUST refuse to boot if `APPLE_AUDIENCES_PROD` is empty.
- Development picks up `APPLE_AUDIENCES_DEV` and defaults to the safe list
  (bundle id + Expo Go).
- Development also honors the legacy `APPLE_AUDIENCES` env var as a fallback.
- In production, the legacy `APPLE_AUDIENCES` env var is IGNORED so a stale
  config file from an older release can't leak the Expo Go audience.
"""
from __future__ import annotations
import subprocess

import pytest

from routes.auth import (
    _APPLE_EXPO_GO_AUD,
    _apple_audiences,
    AppleAudiencesConfigError,
    verify_apple_audiences_config,
)


# ---------- Production fail-fast paths ----------

def test_prod_refuses_expo_go_audience(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APPLE_AUDIENCES_PROD", f"com.faqtotum.app,{_APPLE_EXPO_GO_AUD}")
    monkeypatch.setenv("APPLE_AUDIENCES_DEV", "com.emergent.reviensapp.uwn3nc,host.exp.Exponent")
    with pytest.raises(AppleAudiencesConfigError) as exc:
        _apple_audiences()
    assert _APPLE_EXPO_GO_AUD in str(exc.value)
    assert "production" in str(exc.value).lower()


def test_prod_refuses_empty_prod_var(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APPLE_AUDIENCES_PROD", "")
    with pytest.raises(AppleAudiencesConfigError) as exc:
        _apple_audiences()
    assert "APPLE_AUDIENCES_PROD" in str(exc.value)


def test_prod_ignores_legacy_apple_audiences(monkeypatch):
    """Legacy env var must NOT be used to satisfy the prod requirement."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APPLE_AUDIENCES_PROD", "")
    monkeypatch.setenv("APPLE_AUDIENCES", "com.faqtotum.app,host.exp.Exponent")
    with pytest.raises(AppleAudiencesConfigError):
        _apple_audiences()


def test_prod_accepts_clean_audience_list(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APPLE_AUDIENCES_PROD", "com.faqtotum.app, com.faqtotum.artisan")
    result = _apple_audiences()
    assert result == ["com.faqtotum.app", "com.faqtotum.artisan"]
    assert _APPLE_EXPO_GO_AUD not in result


# ---------- Development / preview paths ----------

def test_dev_uses_dev_env_var(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("APPLE_AUDIENCES_DEV", "com.faqtotum.app,host.exp.Exponent")
    monkeypatch.delenv("APPLE_AUDIENCES", raising=False)
    result = _apple_audiences()
    assert "com.faqtotum.app" in result
    assert _APPLE_EXPO_GO_AUD in result


def test_dev_falls_back_to_legacy_env_var(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("APPLE_AUDIENCES_DEV", raising=False)
    monkeypatch.setenv("APPLE_AUDIENCES", "legacy.bundle,host.exp.Exponent")
    result = _apple_audiences()
    assert "legacy.bundle" in result


def test_dev_uses_defaults_when_no_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("APPLE_AUDIENCES_DEV", raising=False)
    monkeypatch.delenv("APPLE_AUDIENCES", raising=False)
    result = _apple_audiences()
    assert _APPLE_EXPO_GO_AUD in result


def test_dev_allows_expo_go_audience(monkeypatch):
    """Dev must NOT raise when Expo Go audience is present."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("APPLE_AUDIENCES_DEV", f"bundle.x,{_APPLE_EXPO_GO_AUD}")
    # Should not raise.
    result = _apple_audiences()
    assert _APPLE_EXPO_GO_AUD in result


# ---------- Boot integration test ----------

def test_boot_fails_fast_on_misconfig(tmp_path, monkeypatch):
    """
    Full boot integration: launching `python -c 'import server'` with a
    poisoned APPLE_AUDIENCES_PROD MUST exit with a non-zero code and print
    the actionable error message.
    """
    env = dict(**{
        k: v for k, v in __import__("os").environ.items()
        if k in ("MONGO_URL", "DB_NAME", "EMERGENT_LLM_KEY", "PATH", "PYTHONPATH")
    })
    env["APP_ENV"] = "production"
    env["APPLE_AUDIENCES_PROD"] = f"com.faqtotum.app,{_APPLE_EXPO_GO_AUD}"
    env["ALLOWED_ORIGINS"] = "https://faqtotum.example.com"
    env["APPLE_AUDIENCES_DEV"] = ""

    proc = subprocess.run(
        ["python", "-c", "import sys; sys.path.insert(0, '/app/backend'); import server"],
        env=env, capture_output=True, text=True, timeout=20,
    )
    assert proc.returncode != 0, f"expected boot failure, got exit 0. stderr={proc.stderr!r}"
    combined = (proc.stderr + proc.stdout).lower()
    assert "apple audiences" in combined or "host.exp.exponent" in combined


def test_verify_apple_audiences_config_returns_resolved_list(monkeypatch):
    """The boot helper returns the same list for logging purposes."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("APPLE_AUDIENCES_DEV", "test.bundle,host.exp.Exponent")
    monkeypatch.delenv("APPLE_AUDIENCES", raising=False)
    result = verify_apple_audiences_config()
    assert result == ["test.bundle", "host.exp.Exponent"]
