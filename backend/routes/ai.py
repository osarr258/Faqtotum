"""
ai router — V1 migration (Option B: fast structural partition).

Legacy routes previously defined inline in ``server.py`` are moved here
verbatim (bodies unchanged) and mounted via ``build_ai_router(**deps)``.
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
import logging
logger = logging.getLogger(__name__)
from services import concierge
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
from emergentintegrations.llm.openai.speech_to_text import OpenAISpeechToText
from datetime import datetime, timezone
import base64
import tempfile
import os
import uuid
import json

# `db`, `get_current_user`, and every helper/service/model this module needs
# are captured in the closure of `build_ai_router(**deps)` below.


def build_ai_router(**deps) -> APIRouter:
    """Factory: returns an APIRouter mounting every ai endpoint.

    `deps` MUST include (all names as used inside the extracted route bodies):
    db, get_current_user, now_utc, new_id, _load_conv, LlmChat, UserMessage, ImageContent, OpenAISpeechToText, concierge, DiagnoseInput, TranscribeInput, ConciergeStartInput, ConciergeMessageInput, ConciergeVideoInput
    """
    # Explode deps into locals so the extracted route bodies find them by name.
    globals().update(deps)  # noqa: F821 — populates module scope for closures
    _locals = deps
    for _k, _v in _locals.items():
        locals()[_k] = _v

    r = APIRouter()

    @r.post("/ai/diagnose")
    async def ai_diagnose(data: DiagnoseInput, user=Depends(get_current_user)):
        slugs = ", ".join(c["slug"] for c in CATEGORIES)
        system = (
            "Tu es l'IA de diagnostic de ProConnect, plateforme premium de services à domicile en France. "
            "Tu analyses la description et/ou les photos d'un problème domestique et tu produis un diagnostic clair. "
            "Réponds UNIQUEMENT avec un objet JSON valide (aucun texte autour), avec ces clés exactes: "
            "problem (string, résumé du problème en français), "
            f"trade (un slug parmi: {slugs}), "
            "trade_label (nom lisible du métier), "
            "urgency (un parmi: faible, moyenne, elevee, urgence), "
            "duration_min (number, heures), duration_max (number, heures), "
            "price_min (number, euros), price_max (number, euros), "
            "materials (array de strings), "
            "causes (array de 2 à 3 causes probables, strings), "
            "confidence (entier 0-100), "
            "advice (string, conseil de sécurité court en français)."
        )
        if not EMERGENT_LLM_KEY:
            raise HTTPException(status_code=500, detail="Clé IA non configurée")
        chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"diag-{uuid.uuid4().hex[:10]}", system_message=system).with_model("openai", "gpt-4o")
        files = []
        for img in (data.images or [])[:3]:
            b64 = img.split(",", 1)[1] if img.startswith("data:") else img
            files.append(ImageContent(image_base64=b64))
        text = data.text.strip() or "Analyse les photos fournies et établis le diagnostic."
        try:
            raw = await chat.send_message(UserMessage(text=text, file_contents=files or None))
        except Exception as e:
            logger.error(f"diagnose error: {e}")
            raise HTTPException(status_code=502, detail="Le diagnostic IA a échoué, réessayez.")
        txt = raw.strip()
        if txt.startswith("```"):
            txt = txt.strip("`")
            if txt.lower().startswith("json"):
                txt = txt[4:]
            txt = txt.strip()
        try:
            result = json.loads(txt)
        except Exception:
            result = {
                "problem": text, "trade": "plombier", "trade_label": "Plombier",
                "urgency": "moyenne", "duration_min": 1, "duration_max": 2,
                "price_min": 80, "price_max": 200, "materials": [], "confidence": 50,
                "advice": "Coupez l'alimentation concernée et attendez le professionnel.",
            }
        if result.get("trade") not in CATEGORY_MAP:
            lbl = (result.get("trade_label") or "").lower()
            match = next((c["slug"] for c in CATEGORIES if c["name"].lower() in lbl or c["slug"] in lbl), "plombier")
            result["trade"] = match
        cat = CATEGORY_MAP.get(result["trade"])
        result["trade_label"] = cat["name"] if cat else result.get("trade_label")
        result["trade_icon"] = cat["icon"] if cat else "construct"
        return result


    @r.post("/ai/transcribe")
    async def ai_transcribe(data: TranscribeInput, user=Depends(get_current_user)):
        if not EMERGENT_LLM_KEY:
            raise HTTPException(status_code=500, detail="Clé IA non configurée")
        payload = data.audio_base64.split(",", 1)[-1]
        try:
            raw = base64.b64decode(payload)
        except Exception:
            raise HTTPException(status_code=400, detail="Audio invalide")
        suffix = "." + (data.ext or "m4a").lstrip(".")
        path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
                f.write(raw)
                path = f.name
            stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
            res = await stt.transcribe(file=path, model="whisper-1", response_format="json", language="fr")
            text = getattr(res, "text", None)
            if text is None and isinstance(res, dict):
                text = res.get("text", "")
            if text is None:
                text = str(res)
            return {"text": text}
        except Exception as e:
            logger.error(f"transcribe error: {e}")
            raise HTTPException(status_code=502, detail="La transcription a échoué.")
        finally:
            if path and os.path.exists(path):
                os.remove(path)


    @r.post("/concierge/start")
    async def concierge_start(body: ConciergeStartInput, user=Depends(get_current_user)):
        sid = concierge.new_session_id()
        initial = concierge.initial_greeting()
        doc = {
            "session_id": sid,
            "user_id": user["user_id"],
            "property_id": body.property_id,
            "status": "active",
            "turns": [{"role": "assistant", "text": initial["ai_message"], "ai_state": initial, "created_at": concierge.now_iso()}],
            "detected_trade": None,
            "urgency": "faible",
            "confidence": 0,
            "final_summary": None,
            "video_pending": False,
            "created_at": concierge.now_iso(),
            "updated_at": concierge.now_iso(),
        }
        await db.concierge_sessions.insert_one(dict(doc))
        return {"session_id": sid, "state": initial}


    @r.post("/concierge/{sid}/message")
    async def concierge_message(sid: str, body: ConciergeMessageInput, user=Depends(get_current_user)):
        session = await _load_conv(sid, user["user_id"])
        if session["status"] != "active":
            raise HTTPException(status_code=400, detail="Session déjà terminée")

        user_text = (body.text or "").strip()
        if body.voice_base64:
            try:
                payload_v = body.voice_base64.split(",", 1)[-1]
                raw = base64.b64decode(payload_v)
                suffix = "." + (body.voice_ext or "m4a").lstrip(".")
                path = None
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
                    f.write(raw)
                    path = f.name
                stt = OpenAISpeechToText(api_key=EMERGENT_LLM_KEY)
                res = await stt.transcribe(file=path, model="whisper-1", response_format="json", language="fr")
                transcript = getattr(res, "text", None) or (res.get("text") if isinstance(res, dict) else "") or ""
                user_text = f"{user_text} {transcript}".strip() if user_text else transcript
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.warning(f"concierge voice transcribe: {e}")

        turn_user = {
            "role": "user",
            "text": user_text,
            "attachments": {"photos_count": len(body.photos_base64 or []), "voice": bool(body.voice_base64)},
            "created_at": concierge.now_iso(),
        }
        try:
            state = await concierge.next_turn(sid, user_text, body.photos_base64)
        except Exception as e:
            logger.error(f"concierge next_turn failed: {e}")
            raise HTTPException(status_code=502, detail="AURA n'a pas pu répondre, réessayez dans un instant.")

        turn_ai = {"role": "assistant", "text": state["ai_message"], "ai_state": state, "created_at": concierge.now_iso()}
        updates = {
            "detected_trade": state.get("detected_trade") or session.get("detected_trade"),
            "urgency": (state.get("live_diagnosis") or {}).get("urgency") or session.get("urgency"),
            "confidence": (state.get("live_diagnosis") or {}).get("confidence") or session.get("confidence"),
            "updated_at": concierge.now_iso(),
        }
        if state.get("next_action") == "finish" and state.get("summary"):
            updates["status"] = "completed"
            updates["final_summary"] = state["summary"]
        await db.concierge_sessions.update_one(
            {"session_id": sid},
            {"$push": {"turns": {"$each": [turn_user, turn_ai]}}, "$set": updates},
        )
        return {"state": state, "user_text": user_text}


    @r.post("/concierge/{sid}/finish")
    async def concierge_finish(sid: str, user=Depends(get_current_user)):
        session = await _load_conv(sid, user["user_id"])
        if session["status"] != "active":
            return {"state": {"summary": session.get("final_summary")}, "already_finished": True}
        try:
            state = await concierge.next_turn(sid, "Fais-moi le résumé final maintenant, avec la recommandation.", None, force_finish=True)
        except Exception as e:
            logger.error(f"concierge force finish: {e}")
            raise HTTPException(status_code=502, detail="Résumé impossible pour le moment, réessayez.")
        updates = {
            "status": "completed",
            "final_summary": state.get("summary"),
            "detected_trade": state.get("detected_trade") or session.get("detected_trade"),
            "updated_at": concierge.now_iso(),
        }
        await db.concierge_sessions.update_one(
            {"session_id": sid},
            {"$push": {"turns": {"role": "assistant", "text": state["ai_message"], "ai_state": state, "created_at": concierge.now_iso()}},
             "$set": updates},
        )
        return {"state": state}


    @r.post("/concierge/{sid}/video")
    async def concierge_attach_video(sid: str, body: ConciergeVideoInput, user=Depends(get_current_user)):
        await _load_conv(sid, user["user_id"])
        note = {
            "role": "system",
            "text": f"Vidéo reçue ({body.filename}, {body.size_bytes} octets). L'analyse vidéo IA sera bientôt disponible.",
            "created_at": concierge.now_iso(),
            "video_placeholder": True,
        }
        await db.concierge_sessions.update_one(
            {"session_id": sid},
            {"$push": {"turns": note}, "$set": {"video_pending": True, "updated_at": concierge.now_iso()}},
        )
        return {"attached": True, "message": "L'analyse vidéo IA arrive bientôt. En attendant, décrivez ce que vous voyez ou envoyez une photo."}


    @r.get("/concierge/sessions")
    async def concierge_list_sessions(user=Depends(get_current_user)):
        rows = await db.concierge_sessions.find(
            {"user_id": user["user_id"]},
            {"_id": 0, "session_id": 1, "status": 1, "detected_trade": 1, "urgency": 1, "confidence": 1,
             "final_summary": 1, "created_at": 1, "updated_at": 1, "turns": {"$slice": -1}},
        ).sort("updated_at", -1).to_list(100)
        for r in rows:
            last = r.get("turns") or []
            r["last_message"] = last[-1]["text"] if last else ""
            r.pop("turns", None)
        return rows


    @r.get("/concierge/{sid}")
    async def concierge_get_session(sid: str, user=Depends(get_current_user)):
        return await _load_conv(sid, user["user_id"])


    @r.delete("/concierge/{sid}")
    async def concierge_delete_session(sid: str, user=Depends(get_current_user)):
        await _load_conv(sid, user["user_id"])
        await db.concierge_sessions.delete_one({"session_id": sid, "user_id": user["user_id"]})
        return {"ok": True}


    return r
