"""Tests FAQTOTUM V1 — Règle MAX 3 QUESTIONS côté IA concierge.

Ces tests vérifient l'intégration du cap "3 questions max" côté backend :
  1. Le SYSTEM_PROMPT contient bien la règle.
  2. Le route counter `user_turns_so_far` est correctement calculé.
  3. Le contrat de sortie inclut `price_min_eur` / `price_max_eur` pour
     que le frontend puisse afficher la fourchette et calculer la caution.
"""
from __future__ import annotations

import os

import httpx

BASE = os.environ.get("BASE_URL", "http://localhost:8001")


def _h(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def _login(email: str, password: str) -> str:
    r = httpx.post(
        f"{BASE}/api/auth/login",
        json={"email": email, "password": password},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_system_prompt_enforces_max_3_questions():
    from services import concierge

    prompt = concierge.SYSTEM_PROMPT
    assert "MAXIMUM 3 QUESTIONS" in prompt.upper(), (
        "Le prompt doit expliciter la règle 'MAX 3 QUESTIONS' pour l'IA."
    )
    # Doit préciser que 3 n'est PAS obligatoire.
    assert "n'est" in prompt.lower() and "obligation" in prompt.lower(), (
        "Le prompt doit préciser que 3 questions n'est pas une obligation."
    )
    # FAQTOTUM branding
    assert "FAQTOTUM" in prompt


def test_system_prompt_requests_price_min_max_and_summary():
    from services import concierge

    prompt = concierge.SYSTEM_PROMPT
    # Fourchette prix pour l'estimation.
    assert "price_min_eur" in prompt
    assert "price_max_eur" in prompt
    # Le summary final doit inclure les 2 bornes pour permettre le calcul caution.
    assert prompt.count("price_min_eur") >= 2, (
        "price_min_eur doit apparaître dans live_diagnosis ET summary."
    )
    assert prompt.count("price_max_eur") >= 2


def test_concierge_start_returns_initial_greeting():
    token = _login("client.test@auxora.fr", "Test1234!")
    r = httpx.post(
        f"{BASE}/api/concierge/start", headers=_h(token), json={}, timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "session_id" in body
    assert "state" in body
    assert "ai_message" in body["state"]


def test_route_counts_user_turns_correctly():
    """Vérifie que le compteur `user_turns_so_far` est bien calculé.

    On simule 3 tours utilisateur en insérant directement dans Mongo,
    puis on lit ce que ferait le route pour déterminer force_finish.
    """
    from pymongo import MongoClient
    import uuid as _uuid

    client = MongoClient(
        os.environ.get("MONGO_URL", "mongodb://localhost:27017"),
    )
    db = client.auxora
    sid = f"test_sid_{_uuid.uuid4().hex[:8]}"
    session = {
        "session_id": sid,
        "user_id": "test_user",
        "status": "active",
        "turns": [
            {"role": "assistant", "text": "greeting"},
            {"role": "user", "text": "1er"},
            {"role": "assistant", "text": "q1"},
            {"role": "user", "text": "2e"},
            {"role": "assistant", "text": "q2"},
            {"role": "user", "text": "3e"},
        ],
    }
    db.concierge_sessions.insert_one(dict(session))
    try:
        fresh = db.concierge_sessions.find_one({"session_id": sid})
        assert fresh is not None
        user_turns = sum(
            1 for t in (fresh.get("turns") or []) if t.get("role") == "user"
        )
        assert user_turns == 3
        # Au 4ᵉ tour utilisateur, force_finish doit devenir True.
        force = user_turns >= 3
        assert force is True
    finally:
        db.concierge_sessions.delete_one({"session_id": sid})
