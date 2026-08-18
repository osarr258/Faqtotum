"""
V1 hardening — verify that the MFA "000000" demo bypass is closed by default
and only opens when BOTH `MFA_DEMO_MODE=true` and `APP_ENV != production`.

Direct unit tests against `mfa_verify_stub` with monkeypatched env — no HTTP
round-trip, so results are not affected by the running server's own env.
"""
import asyncio
import os
import uuid

import pymongo
import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from services import security as security_svc

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "auxora")


def _run_with_stub(coro_factory):
    """Run an async function that receives a Motor db bound to a fresh loop.

    Motor's collections cache the running loop, so we must create the client
    inside the same event-loop that will await it. `coro_factory(db)` returns
    the coroutine to execute.
    """
    loop = asyncio.new_event_loop()
    try:
        async def _wrap():
            client = AsyncIOMotorClient(MONGO_URL)
            db = client[DB_NAME]
            try:
                return await coro_factory(db)
            finally:
                client.close()
        return loop.run_until_complete(_wrap())
    finally:
        loop.close()


def test_mfa_demo_bypass_rejected_when_env_unset(monkeypatch):
    """Default configuration: `MFA_DEMO_MODE` unset → "000000" must be rejected."""
    monkeypatch.delenv("MFA_DEMO_MODE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.raises(HTTPException) as exc:
        _run_with_stub(lambda db: security_svc.mfa_verify_stub(
            db, f"user_{uuid.uuid4().hex[:8]}", "000000"
        ))
    assert exc.value.status_code == 400


def test_mfa_demo_bypass_rejected_in_production(monkeypatch):
    """Prod hard-gate: even with MFA_DEMO_MODE=true, APP_ENV=production wins."""
    monkeypatch.setenv("MFA_DEMO_MODE", "true")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(HTTPException) as exc:
        _run_with_stub(lambda db: security_svc.mfa_verify_stub(
            db, f"user_{uuid.uuid4().hex[:8]}", "000000"
        ))
    assert exc.value.status_code == 400


def test_mfa_demo_bypass_rejected_when_flag_false(monkeypatch):
    """Explicit MFA_DEMO_MODE=false must reject."""
    monkeypatch.setenv("MFA_DEMO_MODE", "false")
    monkeypatch.setenv("APP_ENV", "development")
    with pytest.raises(HTTPException) as exc:
        _run_with_stub(lambda db: security_svc.mfa_verify_stub(
            db, f"user_{uuid.uuid4().hex[:8]}", "000000"
        ))
    assert exc.value.status_code == 400


def test_mfa_demo_bypass_accepted_when_explicitly_enabled(monkeypatch):
    """The only combination that opens the bypass: dev + explicit flag."""
    monkeypatch.setenv("MFA_DEMO_MODE", "true")
    monkeypatch.setenv("APP_ENV", "development")
    uid = f"user_{uuid.uuid4().hex[:8]}"
    try:
        result = _run_with_stub(lambda db: security_svc.mfa_verify_stub(db, uid, "000000"))
        assert result["enabled"] is True
    finally:
        # Sync cleanup — avoids leaking the mfa_settings doc across tests.
        sync = pymongo.MongoClient(MONGO_URL)
        sync[DB_NAME].mfa_settings.delete_one({"user_id": uid})
        sync.close()


def test_mfa_arbitrary_code_always_rejected(monkeypatch):
    """Even with demo mode ON, non-"000000" codes must be rejected."""
    monkeypatch.setenv("MFA_DEMO_MODE", "true")
    monkeypatch.setenv("APP_ENV", "development")
    with pytest.raises(HTTPException) as exc:
        _run_with_stub(lambda db: security_svc.mfa_verify_stub(
            db, f"user_{uuid.uuid4().hex[:8]}", "123456"
        ))
    assert exc.value.status_code == 400
