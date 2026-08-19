"""Central state machine for missions, bookings and interventions.

Design goals
------------
- **Single source of truth**: every allowed transition (from_state, to_state, actor_role)
  lives in one dict per domain. Any transition NOT listed is refused with 409.
- **Actor authorization is embedded in the transition table**: the same
  from/to pair may be allowed for the client but not for the artisan,
  or vice-versa. No route module ever encodes "who can do what" locally.
- **Immutable audit trail**: every attempt (allowed OR denied) can be
  audited by callers; the helper only decides the legal move.

Terminology
-----------
- `state`  = the domain-specific status column (`bookings.status`,
             `missions.status`, `interventions.status`).
- `role`   = the caller's business role for the resource: "client",
             "artisan", "system" (for automated transitions, e.g. Stripe
             webhook — kept out of scope for Bloc 4 but reserved).
"""
from __future__ import annotations
from typing import Dict, Iterable, Set, Tuple, Optional
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# BOOKINGS — legacy client-vs-artisan booking flow
# ---------------------------------------------------------------------------
# (from_state, actor_role) -> {allowed to_states}
BOOKING_TRANSITIONS: Dict[Tuple[str, str], Set[str]] = {
    ("pending", "artisan"):   {"accepted", "declined"},
    ("pending", "client"):    {"cancelled"},
    # FAQTOTUM V1 — États de progression étendus (En route, Arrivé, En cours).
    ("accepted", "artisan"):  {"en_route", "in_progress", "completed", "cancelled", "replaced"},
    ("accepted", "client"):   {"cancelled"},
    ("en_route", "artisan"):  {"arrived", "cancelled", "replaced"},
    ("en_route", "client"):   {"cancelled"},
    ("arrived", "artisan"):   {"in_progress", "cancelled", "replaced"},
    ("arrived", "client"):    set(),
    ("in_progress", "artisan"): {"completed"},
    ("in_progress", "client"):  set(),
    ("completed", "artisan"): set(),
    ("completed", "client"):  set(),
    ("declined", "artisan"):  set(),
    ("declined", "client"):   set(),
    ("cancelled", "artisan"): set(),
    ("cancelled", "client"):  set(),
    # FAQTOTUM V1 — "Artisan remplacé" (§23) : le booking est marqué
    # replaced, un nouveau matching est lancé automatiquement, le client
    # ne recommence PAS son parcours. Transition system-only (pas d'acteur
    # externe direct) — représenté par le system role via l'admin path.
    ("replaced", "artisan"):  set(),
    ("replaced", "client"):   set(),
    ("replaced", "system"):   {"pending"},  # relance auto du matching
}
BOOKING_TERMINAL = {"completed", "declined", "cancelled"}


# ---------------------------------------------------------------------------
# MISSIONS — the "AI dispatch" flow (client posts a request, matching engine
# offers pros; one of them is confirmed).
# ---------------------------------------------------------------------------
MISSION_TRANSITIONS: Dict[Tuple[str, str], Set[str]] = {
    # Initial dispatch
    ("searching", "client"):     {"cancelled"},        # client aborts
    ("searching", "artisan"):    {"en_route"},         # first-to-accept in emergency
    ("proposed", "client"):      {"cancelled", "en_route"},
    ("proposed", "artisan"):     set(),                # only client can confirm
    # Mission accepted → pro travels
    ("en_route", "client"):      {"cancelled"},
    ("en_route", "artisan"):     {"arrived", "cancelled"},
    ("arrived", "client"):       set(),
    ("arrived", "artisan"):      {"in_progress", "cancelled"},
    ("in_progress", "client"):   set(),
    ("in_progress", "artisan"):  {"completed"},
    ("completed", "client"):     {"disputed"},         # client can raise dispute
    ("completed", "artisan"):    set(),                # terminal for pro
    # Terminal branches
    ("cancelled", "client"):     set(),
    ("cancelled", "artisan"):    set(),
    ("disputed", "client"):      set(),
    ("disputed", "artisan"):     set(),
    ("no_pro", "client"):        set(),
    ("no_pro", "artisan"):       set(),
}
MISSION_TERMINAL = {"cancelled", "disputed", "no_pro"}


# ---------------------------------------------------------------------------
# INTERVENTIONS — the Uber-style live booking
# ---------------------------------------------------------------------------
INTERVENTION_TRANSITIONS: Dict[Tuple[str, str], Set[str]] = {
    # Client posts a request; a pro is offered (assigned) or not yet.
    ("requested", "client"):        {"cancelled"},
    ("requested", "artisan"):       {"accepted", "declined"},   # only the assigned pro
    ("assigned", "client"):         {"cancelled"},
    ("assigned", "artisan"):        {"accepted", "declined"},
    # Accepted — pro on the way
    ("accepted", "client"):         {"cancelled"},
    ("accepted", "artisan"):        {"professional_on_the_way", "cancelled"},
    ("professional_on_the_way", "client"):  {"cancelled"},
    ("professional_on_the_way", "artisan"): {"arrived", "cancelled"},
    ("arrived", "client"):          set(),
    ("arrived", "artisan"):         {"in_progress"},
    ("in_progress", "client"):      set(),
    ("in_progress", "artisan"):     {"completed"},
    # Completed — client validates (moves to `validated`) or disputes.
    ("completed", "client"):        {"validated", "disputed"},
    ("completed", "artisan"):       set(),
    # Payment-linked states remain OUT OF Bloc 4 scope but referenced here so
    # future payment flows can extend the table without duplication.
    ("awaiting_validation", "client"):   {"validated", "disputed"},
    ("awaiting_validation", "artisan"):  set(),
    # Terminal
    ("validated", "client"):        set(),
    ("validated", "artisan"):       set(),
    ("cancelled", "client"):        set(),
    ("cancelled", "artisan"):       set(),
    ("declined", "client"):         set(),
    ("declined", "artisan"):        set(),
    ("disputed", "client"):         set(),
    ("disputed", "artisan"):        set(),
}
INTERVENTION_TERMINAL = {"validated", "cancelled", "declined", "disputed"}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _check(
    table: Dict[Tuple[str, str], Set[str]],
    from_state: str,
    to_state: str,
    actor_role: str,
) -> None:
    """Raise 400 if the transition (from -> to, by role) is not authorized.

    Note on HTTP code: we use 400 (not 409) so that legacy clients that
    validated status values receive the same error class as before. 409 is
    reserved for TRUE concurrency conflicts (the doc was modified between
    read and write) which are raised by the caller after a failed
    compare-and-set.
    """
    key = (from_state, actor_role)
    allowed = table.get(key, set())
    if to_state not in allowed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Transition {from_state!r} → {to_state!r} interdite "
                f"pour le rôle {actor_role!r}"
            ),
        )


def check_booking_transition(from_state: str, to_state: str, actor_role: str) -> None:
    _check(BOOKING_TRANSITIONS, from_state, to_state, actor_role)


def check_mission_transition(from_state: str, to_state: str, actor_role: str) -> None:
    _check(MISSION_TRANSITIONS, from_state, to_state, actor_role)


def check_intervention_transition(
    from_state: str, to_state: str, actor_role: str,
) -> None:
    _check(INTERVENTION_TRANSITIONS, from_state, to_state, actor_role)


def actor_role_for(resource: dict, user_id: str) -> Optional[str]:
    """Return "client" or "artisan" depending on ownership fields on the doc.
    Returns None if the user has no role on this resource — callers should
    map that to 404 (no enumeration leak).
    """
    if resource.get("client_id") == user_id:
        return "client"
    if resource.get("artisan_user_id") == user_id:
        return "artisan"
    return None
