"""Faqtotum — service e-mails transactionnels.

Envoie 5 e-mails déclenchés côté serveur via le proxy Resend géré par Emergent :
  1. Inscription (bienvenue)
  2. Nouvelle réservation (client + artisan)
  3. Confirmation de paiement (final)
  4. Validation d'intervention (artisan payé)
  5. Reset de mot de passe (token à usage unique)

Contraintes :
- L'adresse d'expédition (From) est fixée par la plateforme, seule le
  ``from_name`` d'affichage est réglable → nous forçons "Faqtotum".
- Toutes les templates sont **côté serveur**, jamais construites depuis
  l'input utilisateur (G4 du playbook).
- Le garde-fou ``_assert_safe_email`` est appelé sur chaque send.
- L'envoi est **non bloquant** : ``send_email_safe`` (utilisée par les
  routes) log et absorbe toute erreur — la requête utilisateur (register,
  booking…) ne doit jamais échouer parce qu'un e-mail n'est pas parti.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
from html import escape
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()
logger = logging.getLogger(__name__)

# Constante — ne PAS lire depuis env (survit au déploiement).
EMAIL_BASE_URL = "https://integrations.emergentagent.com"

EMAIL_KEY = os.environ.get("EMERGENT_EMAIL_KEY", "")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "Faqtotum")
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO") or None

# URL de la plateforme (affichée dans les liens des e-mails). Doit être https.
PLATFORM_URL = os.environ.get(
    "PLATFORM_URL", "https://reviens-app.preview.emergentagent.com"
).rstrip("/")


# ---------------------------------------------------------------------------
# Guardrail gate (copié tel quel du playbook, ne pas affaiblir).
# ---------------------------------------------------------------------------
_SHORTENERS = (
    "bit.ly", "tinyurl.com", "t.co", "is.gd", "cutt.ly", "goo.gl", "rebrand.ly",
)
_CRED_ASK = (
    "reply with your password", "reply with the code", "send your password", "cvv",
    "send us your password", "enter your password below", "confirm your card number",
    "your full card number", "seed phrase", "recovery phrase", "verify your card",
    "social security number", "confirm your bank details",
)
_HOSTISH = re.compile(r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})", re.I)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass
    return not any(host == s or host.endswith("." + s) for s in _SHORTENERS)


def _same_site(shown: str, real: str) -> bool:
    return (
        shown == real
        or real.endswith("." + shown)
        or shown.endswith("." + real)
    )


class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags: set[str] = set()
        self.urls: list[str] = []
        self.anchors: list[tuple[str, str]] = []
        self._href: Optional[str] = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan()
    scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    body = f"{subject}\n{html}".lower()
    for p in _CRED_ASK:
        if p in body:
            raise ValueError(
                f"Email asks the recipient for credentials: {p!r} (G2)"
            )
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(
                f"Email links/assets must be absolute https: {url!r} (G3)"
            )
        host = urlparse(low).hostname or ""
        if not _host_ok(host) or urlparse(low).username is not None:
            raise ValueError(
                f"Shortened, numeric-host or credential-bearing URL: {url!r} (G3)"
            )
    for href, text in scan.anchors:
        real = urlparse(href.strip().lower()).hostname or ""
        if not real:
            continue
        for m in _HOSTISH.finditer(text):
            if not _same_site(m.group(1).lower(), real):
                raise ValueError(
                    f"Anchor text {m.group(1)!r} ≠ real link host {real!r} (G3)"
                )


# ---------------------------------------------------------------------------
# Envoi bas niveau.
# ---------------------------------------------------------------------------
async def send_email(
    *, to: str, subject: str, html: str, reply_to: Optional[str] = None
) -> Optional[str]:
    """Version stricte : lève HTTPException en cas d'échec HTTP.

    À utiliser dans les endpoints où l'envoi est le CŒUR de l'opération
    (ex: /auth/password/forgot). Pour les envois secondaires (welcome,
    booking, payment…), préférer ``send_email_safe``.
    """
    if not EMAIL_KEY:
        logger.warning("EMERGENT_EMAIL_KEY absent, e-mail non envoyé (to=%s)", to)
        return None
    _assert_safe_email(subject, html)
    payload = {
        "to": [to],
        "subject": subject,
        "html": html,
        "from_name": EMAIL_FROM_NAME,
    }
    if reply_to or EMAIL_REPLY_TO:
        payload["contact_email"] = reply_to or EMAIL_REPLY_TO
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{EMAIL_BASE_URL}/api/v1/email/send",
                headers={"X-Email-Key": EMAIL_KEY},
                json=payload,
            )
        resp.raise_for_status()
        return resp.json().get("id")
    except httpx.HTTPStatusError as e:
        logger.error(
            "Email send failed: %s %s", e.response.status_code, e.response.text
        )
        raise HTTPException(status_code=502, detail="Échec d'envoi d'e-mail")
    except Exception as e:  # pragma: no cover
        logger.error("Email send error: %s", str(e))
        raise HTTPException(status_code=500, detail="Échec d'envoi d'e-mail")


async def send_email_safe(
    *, to: str, subject: str, html: str, reply_to: Optional[str] = None
) -> bool:
    """Version fire-and-forget : ne lève JAMAIS.

    Utilisée dans les flux où l'e-mail est un effet de bord (registration,
    booking, payment…). En cas d'échec, on log mais la requête HTTP
    principale n'est pas impactée.
    """
    if not to or "@" not in to:
        return False
    try:
        await send_email(to=to, subject=subject, html=html, reply_to=reply_to)
        return True
    except Exception as e:
        logger.warning("send_email_safe swallow (to=%s): %s", to, e)
        return False


# ---------------------------------------------------------------------------
# Templates Faqtotum — minimaliste Noir / Blanc / Gris, texte concis FR.
# ---------------------------------------------------------------------------
_BASE_STYLE = (
    "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;"
    "color:#111111;background:#ffffff;line-height:1.5;font-size:15px;"
)
_MUTED = "color:#6B6B6B;font-size:12px;"
_BTN_STYLE = (
    "display:inline-block;background:#000000;color:#ffffff;"
    "text-decoration:none;padding:12px 20px;border-radius:8px;"
    "font-weight:600;font-size:14px;"
)
_FOOTER = (
    f'<p style="{_MUTED}">Envoyé par {escape(EMAIL_FROM_NAME)}. '
    "Nous ne vous demanderons jamais votre mot de passe par e-mail.</p>"
)


def _wrap(inner_html: str) -> str:
    """Layout <table> universel — les clients mail supportent mal les CSS avancés."""
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="{_BASE_STYLE}">'
        "<tr><td align=\"center\" style=\"padding:32px 16px;\">"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:520px;">'
        '<tr><td style="padding:0 0 24px 0;">'
        f'<div style="font-size:22px;font-weight:700;letter-spacing:-0.5px;">'
        f"{escape(EMAIL_FROM_NAME)}</div>"
        "</td></tr>"
        f"<tr><td>{inner_html}</td></tr>"
        f'<tr><td style="padding-top:32px;border-top:1px solid #E5E5E5;">{_FOOTER}</td></tr>'
        "</table></td></tr></table>"
    )


# --- 1. Bienvenue -----------------------------------------------------------
def tpl_welcome(name: str) -> tuple[str, str]:
    subject = f"Bienvenue sur {EMAIL_FROM_NAME}"
    inner = (
        f"<h1 style=\"font-size:20px;margin:0 0 12px 0;\">Bienvenue, {escape(name)} 👋</h1>"
        f"<p>Votre compte {escape(EMAIL_FROM_NAME)} est prêt. Vous pouvez dès à présent "
        "réserver un artisan de confiance ou proposer vos services.</p>"
        f'<p style="margin:24px 0;"><a href="{PLATFORM_URL}" style="{_BTN_STYLE}">'
        "Ouvrir l'application</a></p>"
        "<p>Un souci ? Répondez simplement à cet e-mail.</p>"
    )
    return subject, _wrap(inner)


# --- 2. Nouvelle réservation ------------------------------------------------
def tpl_booking_client(
    client_name: str, artisan_name: str, date: str, slot: str, booking_id: str
) -> tuple[str, str]:
    subject = f"Réservation confirmée — {artisan_name}"
    inner = (
        f"<h1 style=\"font-size:20px;margin:0 0 12px 0;\">Bonjour {escape(client_name)},</h1>"
        f"<p>Votre demande auprès de <strong>{escape(artisan_name)}</strong> "
        f"a été enregistrée.</p>"
        f'<p style="background:#F5F5F5;padding:12px 16px;border-radius:8px;">'
        f"<strong>Date</strong> : {escape(date)}<br>"
        f"<strong>Créneau</strong> : {escape(slot)}<br>"
        f"<strong>Référence</strong> : {escape(booking_id)}"
        "</p>"
        f'<p style="margin:24px 0;"><a href="{PLATFORM_URL}" style="{_BTN_STYLE}">'
        "Voir la réservation</a></p>"
        "<p>Vous recevrez un nouvel e-mail dès la confirmation de l'artisan.</p>"
    )
    return subject, _wrap(inner)


def tpl_booking_artisan(
    artisan_name: str, client_name: str, date: str, slot: str, booking_id: str
) -> tuple[str, str]:
    subject = f"Nouvelle demande — {client_name}"
    inner = (
        f"<h1 style=\"font-size:20px;margin:0 0 12px 0;\">Bonjour {escape(artisan_name)},</h1>"
        f"<p>Vous avez une nouvelle demande de <strong>{escape(client_name)}</strong>.</p>"
        f'<p style="background:#F5F5F5;padding:12px 16px;border-radius:8px;">'
        f"<strong>Date souhaitée</strong> : {escape(date)}<br>"
        f"<strong>Créneau</strong> : {escape(slot)}<br>"
        f"<strong>Référence</strong> : {escape(booking_id)}"
        "</p>"
        f'<p style="margin:24px 0;"><a href="{PLATFORM_URL}" style="{_BTN_STYLE}">'
        "Répondre à la demande</a></p>"
        "<p>Une réponse rapide améliore votre score de confiance.</p>"
    )
    return subject, _wrap(inner)


# --- 3. Confirmation de paiement --------------------------------------------
def tpl_payment_confirmed(
    client_name: str, amount_cents: int, intervention_id: str
) -> tuple[str, str]:
    amount = f"{amount_cents / 100:.2f} €"
    subject = "Paiement reçu"
    inner = (
        f"<h1 style=\"font-size:20px;margin:0 0 12px 0;\">Merci {escape(client_name)},</h1>"
        f"<p>Nous avons bien reçu votre paiement de "
        f"<strong>{escape(amount)}</strong>.</p>"
        f'<p style="background:#F5F5F5;padding:12px 16px;border-radius:8px;">'
        f"Intervention <strong>{escape(intervention_id)}</strong> — "
        "en attente de votre validation finale."
        "</p>"
        f'<p style="margin:24px 0;"><a href="{PLATFORM_URL}" style="{_BTN_STYLE}">'
        "Voir l'intervention</a></p>"
        "<p>Vous pourrez valider les travaux depuis l'application une fois "
        "l'intervention terminée.</p>"
    )
    return subject, _wrap(inner)


# --- 4. Validation d'intervention (artisan payé) ----------------------------
def tpl_intervention_validated(
    artisan_name: str, net_cents: int, intervention_id: str
) -> tuple[str, str]:
    amount = f"{net_cents / 100:.2f} €" if net_cents else "0.00 €"
    subject = "Intervention validée — versement en cours"
    inner = (
        f"<h1 style=\"font-size:20px;margin:0 0 12px 0;\">Bravo {escape(artisan_name)} 🎉</h1>"
        f"<p>Le client a validé votre intervention "
        f"<strong>{escape(intervention_id)}</strong>.</p>"
        f'<p style="background:#F5F5F5;padding:12px 16px;border-radius:8px;">'
        f"Montant net versé : <strong>{escape(amount)}</strong><br>"
        "Le virement Stripe est en cours vers votre compte connecté."
        "</p>"
        f'<p style="margin:24px 0;"><a href="{PLATFORM_URL}" style="{_BTN_STYLE}">'
        "Voir mes revenus</a></p>"
    )
    return subject, _wrap(inner)


# --- 5. Reset de mot de passe -----------------------------------------------
def tpl_password_reset(name: str, reset_link: str) -> tuple[str, str]:
    subject = "Réinitialisation de votre mot de passe"
    inner = (
        f"<h1 style=\"font-size:20px;margin:0 0 12px 0;\">Bonjour {escape(name)},</h1>"
        "<p>Vous avez demandé la réinitialisation de votre mot de passe. "
        "Ce lien expire dans <strong>60 minutes</strong> et n'est utilisable qu'une fois.</p>"
        f'<p style="margin:24px 0;"><a href="{reset_link}" style="{_BTN_STYLE}">'
        "Choisir un nouveau mot de passe</a></p>"
        "<p>Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail : "
        "votre mot de passe restera inchangé.</p>"
    )
    return subject, _wrap(inner)


__all__ = [
    "send_email",
    "send_email_safe",
    "tpl_welcome",
    "tpl_booking_client",
    "tpl_booking_artisan",
    "tpl_payment_confirmed",
    "tpl_intervention_validated",
    "tpl_password_reset",
    "_assert_safe_email",  # exporté pour les tests
    "PLATFORM_URL",
    "EMAIL_FROM_NAME",
]
