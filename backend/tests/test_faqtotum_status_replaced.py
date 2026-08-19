"""FAQTOTUM V1 — Tests statut "Artisan remplacé" (brief §23)."""
from __future__ import annotations


def test_booking_transitions_include_replaced():
    from services import status_transitions as st

    # accepted → replaced (artisan side)
    assert "replaced" in st.BOOKING_TRANSITIONS[("accepted", "artisan")]
    # en_route → replaced (artisan quits mid-transit)
    assert "replaced" in st.BOOKING_TRANSITIONS[("en_route", "artisan")]
    # arrived → replaced (last-minute quit)
    assert "replaced" in st.BOOKING_TRANSITIONS[("arrived", "artisan")]
    # replaced → pending via system (auto re-broadcast)
    assert "pending" in st.BOOKING_TRANSITIONS[("replaced", "system")]


def test_booking_terminal_still_stable():
    """`replaced` is NOT terminal — it can be rebroadcast."""
    from services import status_transitions as st

    assert "replaced" not in st.BOOKING_TERMINAL
    # But cancelled/completed/declined stay terminal.
    assert "completed" in st.BOOKING_TERMINAL


def test_extended_progression_states_wired():
    """Vérifie que en_route / arrived / in_progress sont bien câblés."""
    from services import status_transitions as st

    assert "en_route" in st.BOOKING_TRANSITIONS[("accepted", "artisan")]
    assert "arrived" in st.BOOKING_TRANSITIONS[("en_route", "artisan")]
    assert "in_progress" in st.BOOKING_TRANSITIONS[("arrived", "artisan")]
    assert "completed" in st.BOOKING_TRANSITIONS[("in_progress", "artisan")]
