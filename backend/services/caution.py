"""FAQTOTUM V1 — Calcul de la caution.

Règle produit (brief §5) :
    caution = borne_haute × 7 %

La caution est ARRONDIE au centime le plus proche.
Elle est basée sur l'estimation INITIALE et ne doit PAS être recalculée
automatiquement si le prix final varie.
"""
from __future__ import annotations

CAUTION_RATE = 0.07  # 7 %


def compute_caution_cents(price_max_eur: float) -> int:
    """Retourne la caution en centimes (int) pour une borne haute donnée.

    Exemples::

        >>> compute_caution_cents(250)
        1750
        >>> compute_caution_cents(180)
        1260
        >>> compute_caution_cents(0)
        0
        >>> compute_caution_cents(-100)
        0
    """
    if not price_max_eur or price_max_eur <= 0:
        return 0
    # borne_haute (€) × 100 pour cents × 0.07
    cents = round(float(price_max_eur) * 100.0 * CAUTION_RATE)
    return max(0, int(cents))


def format_eur(cents: int) -> str:
    """Retourne "17,50 €" (français, virgule décimale)."""
    if cents <= 0:
        return "0 €"
    euros = cents / 100.0
    if euros == int(euros):
        return f"{int(euros)} €"
    return f"{euros:.2f} €".replace(".", ",")
