"""FAQTOTUM V1 — Estimation & Caution : endpoints publics.

Fournit un endpoint léger pour calculer la caution (7 % de la borne haute)
depuis une fourchette de prix. Utilisé par le frontend pour prévisualiser
le montant que le client va préautoriser avant de créer un broadcast.

Endpoints
---------
    POST /api/estimation/quote  { price_min_eur, price_max_eur }
        → { caution_cents, caution_eur, caution_display, rate }
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from services import caution as caution_svc


class QuoteInput(BaseModel):
    price_min_eur: float = Field(0, ge=0, le=100000)
    price_max_eur: float = Field(..., ge=0, le=100000)


def build_estimation_router(get_current_user) -> APIRouter:
    r = APIRouter()

    @r.post("/estimation/quote")
    async def estimation_quote(
        data: QuoteInput, user=Depends(get_current_user),
    ):
        """Retourne la caution (7 % de la borne haute) et son affichage FR."""
        cents = caution_svc.compute_caution_cents(data.price_max_eur)
        return {
            "price_min_eur": data.price_min_eur,
            "price_max_eur": data.price_max_eur,
            "caution_cents": cents,
            "caution_eur": round(cents / 100.0, 2),
            "caution_display": caution_svc.format_eur(cents),
            "rate": caution_svc.CAUTION_RATE,
            "rate_display": "7 %",
            "note": (
                "Caution basée sur l'estimation initiale. "
                "Ne sera pas recalculée si le prix final varie."
            ),
        }

    return r
