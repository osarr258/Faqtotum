"""Tests unitaires du service emails (Sprint 1 Brique 2 — Resend).

Ces tests ne font AUCUN appel HTTP réel. Ils valident :
- Les 6 templates FR passent le guardrail gate G2/G3.
- ``send_email_safe`` avale toute exception (fire-and-forget).
- Un HTML malveillant (form / http non-https / shortener / anchor
  spoofing) est rejeté par ``_assert_safe_email``.
"""

from __future__ import annotations

import asyncio

import pytest

from services import emails


# --- Templates -----------------------------------------------------------

@pytest.mark.parametrize(
    "factory,args",
    [
        (emails.tpl_welcome, ("Alice",)),
        (emails.tpl_booking_client, ("Alice", "Bob", "2026-06-15", "10:00-12:00", "bk_1")),
        (emails.tpl_booking_artisan, ("Bob", "Alice", "2026-06-15", "10:00-12:00", "bk_1")),
        (emails.tpl_payment_confirmed, ("Alice", 15000, "iv_1")),
        (emails.tpl_intervention_validated, ("Bob", 13500, "iv_1")),
        (
            emails.tpl_password_reset,
            ("Alice", emails.PLATFORM_URL + "/reset-password?token=abc"),
        ),
    ],
)
def test_templates_pass_guardrail_gate(factory, args):
    subject, html = factory(*args)
    assert isinstance(subject, str) and subject
    assert isinstance(html, str) and html
    # Ne doit PAS lever.
    emails._assert_safe_email(subject, html)


def test_templates_contain_faqtotum_brand():
    subject, html = emails.tpl_welcome("Alice")
    assert "Faqtotum" in html


# --- Guardrail rejects ---------------------------------------------------

def test_gate_rejects_form():
    with pytest.raises(ValueError):
        emails._assert_safe_email(
            "x",
            '<form action="https://example.com"><input name="p"/></form>',
        )


def test_gate_rejects_http_link():
    with pytest.raises(ValueError):
        emails._assert_safe_email(
            "x", '<a href="http://foo.com">click</a>',
        )


def test_gate_rejects_shortener():
    with pytest.raises(ValueError):
        emails._assert_safe_email(
            "x", '<a href="https://bit.ly/xxx">click</a>',
        )


def test_gate_rejects_anchor_host_mismatch():
    """L'ancre affiche 'paypal.com' mais pointe vers un autre domaine."""
    with pytest.raises(ValueError):
        emails._assert_safe_email(
            "x",
            '<a href="https://evil.example.com/p">paypal.com login</a>',
        )


def test_gate_rejects_credential_ask():
    with pytest.raises(ValueError):
        emails._assert_safe_email(
            "Reply with your password",
            "<p>hello</p>",
        )


# --- send_email_safe fire-and-forget -------------------------------------

def test_send_email_safe_swallow_on_bad_recipient():
    """Un `to` invalide ne doit JAMAIS lever."""
    result = asyncio.run(
        emails.send_email_safe(
            to="",
            subject="x",
            html=emails.tpl_welcome("A")[1],
        )
    )
    assert result is False


def test_send_email_safe_swallow_on_bad_html(monkeypatch):
    """Un template qui trip la gate ne doit pas lever depuis _safe."""
    # Patch send_email pour simuler un fail non-httpx.
    async def _boom(**_kwargs):
        raise RuntimeError("simulated boom")

    monkeypatch.setattr(emails, "send_email", _boom)
    result = asyncio.run(
        emails.send_email_safe(
            to="test@example.com",
            subject="x",
            html="<p>ok</p>",
        )
    )
    assert result is False
