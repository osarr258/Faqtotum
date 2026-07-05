"""
ProConnect — Calendar Sync (architecture, MOCKED provider sync)
===============================================================
Provides the scheduling backbone: availability slot generation and a
provider-agnostic connection layer (Google / Outlook / Apple). The real
provider OAuth + two-way sync is intentionally MOCKED for now — every public
function is shaped so that a real implementation can drop in later without
touching callers.

Design: pure, deterministic helpers (no DB, no network). The caller persists
the returned structures.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

# Default working window (local hours) and slot granularity.
WORK_START_HOUR = 8
WORK_END_HOUR = 19
SLOT_HOURS = 2  # 2-hour appointment windows
SUPPORTED_PROVIDERS = ("google", "outlook", "apple")

SLOT_LABELS = {
    8: "08:00 – 10:00",
    10: "10:00 – 12:00",
    12: "12:00 – 14:00",
    14: "14:00 – 16:00",
    16: "16:00 – 18:00",
    18: "18:00 – 20:00",
}


def _pseudo_busy(artisan_id: str, day_index: int, hour: int) -> bool:
    """Deterministic 'busy' pattern so the mock looks realistic & stable.
    Replaced by real provider free/busy data once sync is wired."""
    seed = (sum(ord(c) for c in (artisan_id or "x")) + day_index * 7 + hour) % 5
    return seed == 0


def generate_availability(artisan_id: str, days: int = 7,
                          busy: List[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
    """Return a list of day buckets with bookable slots for the next `days`.

    `busy` is an optional list of {date, hour} the artisan already booked
    (from our own bookings DB) — those slots are removed. The remaining
    'busy' simulation stands in for an external calendar's free/busy feed.
    """
    busy_set = {(b.get("date"), int(b.get("hour", -1))) for b in (busy or [])}
    today = datetime.now(timezone.utc).date()
    out: List[Dict[str, Any]] = []
    for d in range(days):
        day = today + timedelta(days=d)
        date_str = day.isoformat()
        weekday = day.weekday()  # 0=Mon .. 6=Sun
        slots = []
        for hour in range(WORK_START_HOUR, WORK_END_HOUR, SLOT_HOURS):
            # Sundays closed; Saturdays morning only.
            if weekday == 6:
                continue
            if weekday == 5 and hour >= 14:
                continue
            taken = (date_str, hour) in busy_set or _pseudo_busy(artisan_id, d, hour)
            slots.append({
                "hour": hour,
                "label": SLOT_LABELS.get(hour, f"{hour:02d}:00"),
                "available": not taken,
            })
        out.append({
            "date": date_str,
            "weekday": weekday,
            "slots": slots,
            "has_availability": any(s["available"] for s in slots),
        })
    return out


def next_available(artisan_id: str, days: int = 7,
                   busy: List[Dict[str, Any]] | None = None) -> Dict[str, Any] | None:
    """First bookable {date, hour, label} or None."""
    for day in generate_availability(artisan_id, days, busy):
        for s in day["slots"]:
            if s["available"]:
                return {"date": day["date"], **s}
    return None


def connect_provider(provider: str) -> Dict[str, Any]:
    """MOCK provider connection. Returns a synthetic connection descriptor.
    Replace with real OAuth handshake when going live."""
    provider = (provider or "").lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Fournisseur non supporté: {provider}")
    return {
        "provider": provider,
        "connected": True,
        "mock": True,
        "scope": "calendar.readwrite",
        "connected_at": datetime.now(timezone.utc).isoformat(),
        "synced_calendars": [f"{provider}:primary"],
    }
