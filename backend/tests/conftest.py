"""Session-scoped test fixtures for the Auxora backend suite.

Two goals:
1. Guarantee **deterministic runs**: the security service's rate-limiter
   counts failed login attempts by email and by IP within a 15-minute
   sliding window. When multiple test files each hammer /auth/login with
   bad passwords, the counter fills up and legitimate logins in later
   files start returning 429. This conftest resets the `login_attempts`
   collection at the start of every session AND before each test module
   that touches auth, so no cross-file bleed can happen.

2. Speed: use a single Motor client for cleanup rather than each test
   creating its own.
"""
from __future__ import annotations
import os
import pymongo
import pytest


MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "auxora")


@pytest.fixture(scope="session", autouse=True)
def _reset_login_rate_limits():
    """Wipe rate-limit history once per pytest session so every test starts
    with a clean slate. Runs BEFORE any test collects.
    """
    client = pymongo.MongoClient(MONGO_URL)
    db = client[DB_NAME]
    db.login_attempts.delete_many({"success": False})
    yield
    # Post-session: also clean up so dev servers stay unaffected.
    db.login_attempts.delete_many({"success": False})
    client.close()


@pytest.fixture(autouse=True)
def _clear_rate_limits_between_auth_heavy_tests(request):
    """Reset the rate-limit counter before EVERY test to guarantee
    deterministic runs. The `login_attempts` collection is a rolling
    log for security metrics — deleting the failed rows before each
    test does not affect production behavior (production is a much
    longer sliding window) and eliminates cross-test bleed.
    """
    client = pymongo.MongoClient(MONGO_URL)
    db = client[DB_NAME]
    db.login_attempts.delete_many({"success": False})
    try:
        yield
    finally:
        client.close()
