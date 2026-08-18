"""
messaging router — V1 migration (Option B: fast structural partition).

Legacy routes previously defined inline in ``server.py`` are moved here
verbatim (bodies unchanged) and mounted via ``build_messaging_router(**deps)``.
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
from datetime import datetime, timezone

# `db`, `get_current_user`, and every helper/service/model this module needs
# are captured in the closure of `build_messaging_router(**deps)` below.


def build_messaging_router(**deps) -> APIRouter:
    """Factory: returns an APIRouter mounting every messaging endpoint.

    `deps` MUST include (all names as used inside the extracted route bodies):
    db, get_current_user, now_utc, new_id, conv_view, MessageInput
    """
    # Explode deps into locals so the extracted route bodies find them by name.
    globals().update(deps)  # noqa: F821 — populates module scope for closures
    _locals = deps
    for _k, _v in _locals.items():
        locals()[_k] = _v

    r = APIRouter()

    @r.get("/conversations")
    async def list_conversations(user=Depends(get_current_user)):
        uid = user["user_id"]
        convs = await db.conversations.find({"$or": [{"client_id": uid}, {"artisan_user_id": uid}]}, {"_id": 0}).to_list(500)
        convs.sort(key=lambda x: x.get("last_at", ""), reverse=True)
        return [conv_view(c, uid) for c in convs]


    @r.get("/conversations/{conversation_id}")
    async def get_conversation(conversation_id: str, user=Depends(get_current_user)):
        uid = user["user_id"]
        conv = await db.conversations.find_one({"conversation_id": conversation_id}, {"_id": 0})
        if not conv or uid not in (conv.get("client_id"), conv.get("artisan_user_id")):
            raise HTTPException(status_code=403, detail="Conversation introuvable")
        msgs = await db.messages.find({"conversation_id": conversation_id}, {"_id": 0}).to_list(2000)
        msgs.sort(key=lambda x: x.get("created_at", ""))
        return {"conversation": conv_view(conv, uid), "messages": msgs}


    @r.post("/conversations/{conversation_id}/messages")
    async def send_message(conversation_id: str, data: MessageInput, user=Depends(get_current_user)):
        uid = user["user_id"]
        conv = await db.conversations.find_one({"conversation_id": conversation_id}, {"_id": 0})
        if not conv or uid not in (conv.get("client_id"), conv.get("artisan_user_id")):
            raise HTTPException(status_code=403, detail="Conversation introuvable")
        msg = {
            "message_id": new_id("msg"),
            "conversation_id": conversation_id,
            "sender_id": uid,
            "sender_name": user["name"],
            "text": data.text,
            "created_at": now_utc().isoformat(),
        }
        await db.messages.insert_one(msg)
        await db.conversations.update_one(
            {"conversation_id": conversation_id},
            {"$set": {"last_message": data.text, "last_at": msg["created_at"]}},
        )
        msg.pop("_id", None)
        return msg


    return r
