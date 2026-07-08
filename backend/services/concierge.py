"""
ProConnect / Auxora — AI Concierge
==================================
Multi-turn conversational diagnosis. Guides the customer through the problem
naturally, adapts questions to the detected trade, produces a live diagnosis
card at every turn, surfaces safety alerts, and generates a final summary
with a recommended professional.

Design goals
------------
- **Conversational**: never overwhelm — one focused question at a time.
- **Trade-adaptive**: dynamic follow-ups depend on the detected trade (leak,
  power outage, boiler error code, ...).
- **Safety-first**: if the model detects danger (electrical short, gas smell,
  major leak, fire risk), it MUST surface `safety_alerts` before anything else.
- **Structured**: every LLM turn returns strict JSON — the app trusts nothing
  else. Free-form conversation lives inside `ai_message`.
- **Persistable**: full turn history stored in `concierge_sessions` (Mongo).
- **Stateless service**: LlmChat handles multi-turn memory via `session_id`.

Callers
-------
`server.py` exposes CRUD around this service. The service itself never touches
the DB — the router owns persistence.
"""
from __future__ import annotations
import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

logger = logging.getLogger(__name__)

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

TRADES = [
    "plombier", "electricien", "chauffagiste", "climaticien",
    "peintre", "serrurier", "menuisier", "macon",
    "carreleur", "vitrier", "couvreur", "jardinier",
]
URGENCIES = ["faible", "moyenne", "elevee", "urgence"]
NEXT_ACTIONS = ["continue", "ask_photo", "ask_video", "ask_voice", "finish"]

SAFETY_KEYWORDS = {
    "electricien": [
        {"trigger": ["odeur", "brûlé", "brule"], "level": "urgence",
         "message": "Coupez immédiatement le disjoncteur général et évacuez si l'odeur s'intensifie."},
        {"trigger": ["choc électrique", "électrocuté", "electrocute"], "level": "urgence",
         "message": "Appelez le 15 (SAMU). Coupez le compteur avant toute manipulation."},
    ],
    "plombier": [
        {"trigger": ["fuite majeure", "inondation", "eau partout"], "level": "urgence",
         "message": "Fermez immédiatement l'arrivée d'eau générale (vanne principale)."},
    ],
    "chauffagiste": [
        {"trigger": ["odeur gaz", "gaz", "fuite gaz"], "level": "urgence",
         "message": "Ne touchez aucun interrupteur. Ouvrez les fenêtres, fermez la vanne gaz, sortez et appelez le 18."},
        {"trigger": ["monoxyde", "co2", "maux de tête"], "level": "urgence",
         "message": "Sortez immédiatement, appelez le 15. Le monoxyde de carbone est mortel."},
    ],
    "serrurier": [
        {"trigger": ["enfermé", "enferme", "cambriolage"], "level": "urgence",
         "message": "Si vous êtes en danger immédiat, appelez le 17 (Police)."},
    ],
    "couvreur": [
        {"trigger": ["effondrement", "tuile qui tombe"], "level": "urgence",
         "message": "Évacuez la zone en dessous de la toiture. N'accédez pas au toit."},
    ],
}

SYSTEM_PROMPT = """Tu es AURA, le concierge IA de ProConnect / Auxora, plateforme premium de services à domicile en France.

Ta mission : accompagner le client dans un diagnostic conversationnel naturel, comme un expert du bâtiment au téléphone. Chaleureux, calme, précis, JAMAIS bavard.

RÈGLES ABSOLUES
1. Une seule question à la fois. Elle doit avoir du sens vis-à-vis de ce que le client vient de dire.
2. Adapte tes questions au métier détecté :
   - Plomberie → localisation, intensité fuite, eau chaude/froide, pression.
   - Électricité → coupure, disjoncteur, odeur de brûlé, prises concernées.
   - Chauffage → code erreur chaudière, bruit, température, pression circuit.
   - Serrurerie → verrou/porte, cambriolage possible, urgence physique.
   - Toiture → matériau, âge, fuite intérieure, accessibilité.
3. Si tu détectes un danger (feu, gaz, électrocution, inondation, effondrement) tu remplis `safety_alerts` en priorité.
4. Si une photo aiderait vraiment → next_action="ask_photo". Une vidéo pour un bruit/mouvement → next_action="ask_video". Un enregistrement vocal si le client tape mal → next_action="ask_voice".
5. Après 4-6 échanges utiles OU si confidence ≥ 80 → next_action="finish" et remplis `summary` (voir schéma).
6. Toujours en français. Ton chaleureux, tutoiement PROSCRIT — vouvoiement obligatoire ("vous").
7. Ne propose JAMAIS de tarif fantaisiste. Fourchettes réalistes marché France 2026.
8. Ne donne JAMAIS de conseil qui remplace un pro. Redirige toujours vers l'artisan.

FORMAT DE RÉPONSE — OBLIGATOIRE JSON strict (rien avant, rien après) :
{
  "ai_message": "string — ta phrase au client, MAX 2 phrases, chaleureuse.",
  "detected_trade": "un slug parmi: plombier, electricien, chauffagiste, climaticien, peintre, serrurier, menuisier, macon, carreleur, vitrier, couvreur, jardinier",
  "live_diagnosis": {
    "issue": "string — problème identifié en 1 phrase, ou 'analyse en cours' au début",
    "confidence": 0-100,
    "urgency": "faible | moyenne | elevee | urgence",
    "duration_min_hours": number,
    "duration_max_hours": number,
    "price_min_eur": number,
    "price_max_eur": number,
    "risks": ["string", ...]
  },
  "safety_alerts": [{"level": "info|urgence", "message": "string"}],
  "next_action": "continue | ask_photo | ask_video | ask_voice | finish",
  "followup_suggestions": ["Réponse rapide 1", "Réponse rapide 2", "Réponse rapide 3"],
  "summary": null OR (si next_action=finish) {
    "problem": "string — résumé du problème",
    "trade": "slug",
    "trade_label": "string — nom lisible",
    "urgency": "…",
    "duration_hours": "string court '1-2h'",
    "price_range_eur": "string '80-200€'",
    "materials": ["…"],
    "safety_advice": "string",
    "preparation_tips": ["conseil 1 avant l'intervention", "…"],
    "confidence": 0-100
  }
}

Tu dois retourner UNIQUEMENT ce JSON, sans texte autour, sans backticks.
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _augment_safety(user_text: str, detected_trade: Optional[str], safety_alerts: List[Dict]) -> List[Dict]:
    """Deterministic safety net — even if the model misses a red flag, keyword
    detection kicks in and prepends an alert. Never removes model alerts."""
    text_lc = (user_text or "").lower()
    triggered = []
    for trade, rules in SAFETY_KEYWORDS.items():
        if detected_trade and trade != detected_trade:
            # We still check cross-trade triggers for gas/electricity because
            # safety > taxonomy.
            if trade not in ("chauffagiste", "electricien"):
                continue
        for rule in rules:
            if any(t in text_lc for t in rule["trigger"]):
                triggered.append({"level": rule["level"], "message": rule["message"]})
    # Merge — de-dup by message.
    seen = {a.get("message") for a in safety_alerts or []}
    for t in triggered:
        if t["message"] not in seen:
            safety_alerts = (safety_alerts or []) + [t]
            seen.add(t["message"])
    return safety_alerts


def _sanitize(state: Dict[str, Any], user_text: str) -> Dict[str, Any]:
    """Guarantee schema even if the model drifts."""
    ld = state.get("live_diagnosis") or {}
    ld.setdefault("issue", "analyse en cours")
    ld.setdefault("confidence", 0)
    ld.setdefault("urgency", "moyenne")
    ld.setdefault("duration_min_hours", 1)
    ld.setdefault("duration_max_hours", 2)
    ld.setdefault("price_min_eur", 80)
    ld.setdefault("price_max_eur", 200)
    ld.setdefault("risks", [])
    if ld["urgency"] not in URGENCIES:
        ld["urgency"] = "moyenne"
    ld["confidence"] = max(0, min(100, int(ld.get("confidence") or 0)))

    trade = state.get("detected_trade")
    if trade not in TRADES:
        trade = None
    next_action = state.get("next_action")
    if next_action not in NEXT_ACTIONS:
        next_action = "continue"
    safety = _augment_safety(user_text, trade, state.get("safety_alerts") or [])
    suggestions = state.get("followup_suggestions") or []
    if not isinstance(suggestions, list):
        suggestions = []
    return {
        "ai_message": (state.get("ai_message") or "Pouvez-vous m'en dire un peu plus ?").strip(),
        "detected_trade": trade,
        "live_diagnosis": ld,
        "safety_alerts": safety,
        "next_action": next_action,
        "followup_suggestions": suggestions[:4],
        "summary": state.get("summary"),
    }


async def next_turn(session_id: str, user_text: str, photos_base64: Optional[List[str]] = None,
                     force_finish: bool = False) -> Dict[str, Any]:
    """Send the user's turn to the LLM and return the structured next state.
    `session_id` MUST be reused across turns so the model keeps context."""
    if not os.environ.get("EMERGENT_LLM_KEY"):
        raise RuntimeError("EMERGENT_LLM_KEY not configured")
    key = os.environ["EMERGENT_LLM_KEY"]

    prompt = SYSTEM_PROMPT
    if force_finish:
        prompt += "\n\nLe client demande le résumé maintenant. Réponds avec next_action='finish' et remplis 'summary' complet."

    chat = LlmChat(api_key=key, session_id=session_id,
                   system_message=prompt).with_model("openai", "gpt-4o")
    files = []
    for img in (photos_base64 or [])[:4]:
        b64 = img.split(",", 1)[1] if img.startswith("data:") else img
        files.append(ImageContent(image_base64=b64))
    text = user_text.strip() or "Analyse mes photos."
    raw = await chat.send_message(UserMessage(text=text, file_contents=files or None))
    txt = raw.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:]
        txt = txt.strip()
    try:
        parsed = json.loads(txt)
    except Exception as e:
        logger.warning(f"concierge json parse failed: {e} raw={txt[:200]}")
        parsed = {
            "ai_message": "Pouvez-vous préciser un peu plus votre problème ?",
            "detected_trade": None,
            "live_diagnosis": {"issue": "analyse en cours", "confidence": 20, "urgency": "moyenne"},
            "next_action": "continue",
            "followup_suggestions": [],
        }
    return _sanitize(parsed, user_text)


def initial_greeting() -> Dict[str, Any]:
    """First turn is deterministic — no LLM call. Sets up the conversation."""
    return {
        "ai_message": "Bonjour, je suis AURA, votre concierge IA. Racontez-moi ce qui vous arrive — texte, photo, ou message vocal, comme vous préférez.",
        "detected_trade": None,
        "live_diagnosis": {
            "issue": "analyse en cours",
            "confidence": 0,
            "urgency": "faible",
            "duration_min_hours": 0,
            "duration_max_hours": 0,
            "price_min_eur": 0,
            "price_max_eur": 0,
            "risks": [],
        },
        "safety_alerts": [],
        "next_action": "continue",
        "followup_suggestions": [
            "J'ai une fuite d'eau",
            "Panne d'électricité",
            "Chaudière en panne",
            "Serrure cassée",
        ],
        "summary": None,
    }


def new_session_id() -> str:
    return f"conv_{uuid.uuid4().hex[:16]}"
