"""
V1 hardening — verify the MFA flow.

Covers:
- The historical "000000" demo bypass is closed in default/prod configuration
  (only opens when BOTH `MFA_DEMO_MODE=true` and `APP_ENV != production`
  AND no real secret is enrolled yet).
- Real RFC 6238 TOTP: `mfa_prepare` returns a base32 secret + provisioning URI,
  `mfa_verify_stub` accepts codes computed from that secret (±1 period window).
- Once a real secret is enrolled, the demo "000000" bypass is IGNORED — real
  TOTP wins.
- Secrets are stored encrypted at rest (never plaintext).

Direct unit tests against `mfa_*` functions with monkeypatched env — no HTTP
round-trip, so results are not affected by the running server's own env.
"""
import asyncio
import os
import uuid

import pymongo
import pyotp
import pytest
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from services import security as security_svc

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "auxora")


def _run_with_db(coro_factory):
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


def _cleanup(user_id: str):
    sync = pymongo.MongoClient(MONGO_URL)
    sync[DB_NAME].mfa_settings.delete_one({"user_id": user_id})
    sync.close()


# ---------- Demo bypass — closed by default ----------

def test_mfa_demo_bypass_rejected_when_env_unset(monkeypatch):
    monkeypatch.delenv("MFA_DEMO_MODE", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.raises(HTTPException) as exc:
        _run_with_db(lambda db: security_svc.mfa_verify_stub(
            db, f"user_{uuid.uuid4().hex[:8]}", "000000"
        ))
    assert exc.value.status_code == 400


def test_mfa_demo_bypass_rejected_in_production(monkeypatch):
    monkeypatch.setenv("MFA_DEMO_MODE", "true")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("MFA_ENCRYPTION_KEY", _dev_fernet_key())
    with pytest.raises(HTTPException) as exc:
        _run_with_db(lambda db: security_svc.mfa_verify_stub(
            db, f"user_{uuid.uuid4().hex[:8]}", "000000"
        ))
    assert exc.value.status_code == 400


def test_mfa_demo_bypass_rejected_when_flag_false(monkeypatch):
    monkeypatch.setenv("MFA_DEMO_MODE", "false")
    monkeypatch.setenv("APP_ENV", "development")
    with pytest.raises(HTTPException) as exc:
        _run_with_db(lambda db: security_svc.mfa_verify_stub(
            db, f"user_{uuid.uuid4().hex[:8]}", "000000"
        ))
    assert exc.value.status_code == 400


def test_mfa_demo_bypass_accepted_when_explicitly_enabled(monkeypatch):
    """Only combination that opens the bypass: dev + explicit flag + no real secret enrolled."""
    monkeypatch.setenv("MFA_DEMO_MODE", "true")
    monkeypatch.setenv("APP_ENV", "development")
    uid = f"user_{uuid.uuid4().hex[:8]}"
    try:
        result = _run_with_db(lambda db: security_svc.mfa_verify_stub(db, uid, "000000"))
        assert result["enabled"] is True
    finally:
        _cleanup(uid)


def test_mfa_arbitrary_code_always_rejected(monkeypatch):
    monkeypatch.setenv("MFA_DEMO_MODE", "true")
    monkeypatch.setenv("APP_ENV", "development")
    with pytest.raises(HTTPException) as exc:
        _run_with_db(lambda db: security_svc.mfa_verify_stub(
            db, f"user_{uuid.uuid4().hex[:8]}", "123456"
        ))
    assert exc.value.status_code == 400


# ---------- Real TOTP (RFC 6238) ----------

def _dev_fernet_key() -> str:
    """Deterministic dev key so tests can encrypt/decrypt across processes."""
    import base64
    import hashlib
    return base64.urlsafe_b64encode(
        hashlib.sha256(b"faqtotum-dev-mfa-ephemeral-key").digest()
    ).decode()


def test_mfa_prepare_returns_base32_secret_and_provisioning_uri(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    uid = f"user_{uuid.uuid4().hex[:8]}"
    try:
        out = _run_with_db(lambda db: security_svc.mfa_prepare(db, uid, "totp"))
        # Base32, 32 chars (160-bit).
        assert isinstance(out["secret"], str) and len(out["secret"]) == 32
        assert set(out["secret"]).issubset(set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"))
        assert out["provisioning_uri"].startswith("otpauth://totp/")
        assert "Faqtotum" in out["provisioning_uri"]
    finally:
        _cleanup(uid)


def test_mfa_secret_is_encrypted_at_rest(monkeypatch):
    """The DB must never contain the plaintext base32 secret."""
    monkeypatch.setenv("APP_ENV", "development")
    uid = f"user_{uuid.uuid4().hex[:8]}"
    try:
        out = _run_with_db(lambda db: security_svc.mfa_prepare(db, uid, "totp"))
        secret_plain = out["secret"]
        # Read the raw document synchronously to inspect on-disk state.
        sync = pymongo.MongoClient(MONGO_URL)
        try:
            doc = sync[DB_NAME].mfa_settings.find_one({"user_id": uid}) or {}
        finally:
            sync.close()
        # Encrypted field is present, plaintext one is NOT.
        assert doc.get("secret_pending_enc"), "encrypted secret missing"
        assert secret_plain not in doc.get("secret_pending_enc", ""), \
            "encrypted field contains plaintext secret"
        # Legacy plaintext key must not exist.
        assert doc.get("secret_pending") is None
    finally:
        _cleanup(uid)


def test_mfa_verify_accepts_valid_totp_code(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    uid = f"user_{uuid.uuid4().hex[:8]}"
    try:
        prep = _run_with_db(lambda db: security_svc.mfa_prepare(db, uid, "totp"))
        code = pyotp.TOTP(prep["secret"]).now()
        result = _run_with_db(lambda db: security_svc.mfa_verify_stub(db, uid, code))
        assert result["enabled"] is True
        # Pending secret was promoted to active on success.
        sync = pymongo.MongoClient(MONGO_URL)
        try:
            doc = sync[DB_NAME].mfa_settings.find_one({"user_id": uid}) or {}
        finally:
            sync.close()
        assert doc.get("secret_enc")
        assert doc.get("secret_pending_enc") is None
        assert doc.get("enabled") is True
    finally:
        _cleanup(uid)


def test_mfa_verify_rejects_wrong_totp_code(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    uid = f"user_{uuid.uuid4().hex[:8]}"
    try:
        _run_with_db(lambda db: security_svc.mfa_prepare(db, uid, "totp"))
        with pytest.raises(HTTPException) as exc:
            _run_with_db(lambda db: security_svc.mfa_verify_stub(db, uid, "999999"))
        assert exc.value.status_code == 400
    finally:
        _cleanup(uid)


def test_mfa_real_secret_bypasses_demo_mode(monkeypatch):
    """Once a real secret is enrolled, "000000" must NOT work even with demo mode on."""
    monkeypatch.setenv("MFA_DEMO_MODE", "true")
    monkeypatch.setenv("APP_ENV", "development")
    uid = f"user_{uuid.uuid4().hex[:8]}"
    try:
        _run_with_db(lambda db: security_svc.mfa_prepare(db, uid, "totp"))
        with pytest.raises(HTTPException) as exc:
            _run_with_db(lambda db: security_svc.mfa_verify_stub(db, uid, "000000"))
        assert exc.value.status_code == 400
    finally:
        _cleanup(uid)


def test_mfa_disable_clears_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    uid = f"user_{uuid.uuid4().hex[:8]}"
    try:
        prep = _run_with_db(lambda db: security_svc.mfa_prepare(db, uid, "totp"))
        code = pyotp.TOTP(prep["secret"]).now()
        _run_with_db(lambda db: security_svc.mfa_verify_stub(db, uid, code))
        _run_with_db(lambda db: security_svc.mfa_disable(db, uid))
        sync = pymongo.MongoClient(MONGO_URL)
        try:
            doc = sync[DB_NAME].mfa_settings.find_one({"user_id": uid}) or {}
        finally:
            sync.close()
        assert doc.get("enabled") is False
        assert doc.get("secret_enc") is None
        assert doc.get("secret_pending_enc") is None
    finally:
        _cleanup(uid)


def test_mfa_only_totp_method_supported(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    uid = f"user_{uuid.uuid4().hex[:8]}"
    try:
        with pytest.raises(HTTPException) as exc:
            _run_with_db(lambda db: security_svc.mfa_prepare(db, uid, "sms"))
        assert exc.value.status_code == 400
    finally:
        _cleanup(uid)
