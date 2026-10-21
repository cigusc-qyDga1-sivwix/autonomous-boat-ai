"""Wakamatsu-only deadline-based scheduling. No external fetch or wagering."""
from datetime import datetime, timedelta

VENUE_CODE = "20"
LEAD_MINUTES = 10

def inspection_time(cutoff: datetime) -> datetime:
    if cutoff.tzinfo is None:
        raise ValueError("Timezone-aware cutoff required")
    return cutoff - timedelta(minutes=LEAD_MINUTES)

def due_for_inspection(cutoff: datetime, now: datetime, window_seconds: int = 60) -> bool:
    if now.tzinfo is None:
        raise ValueError("Timezone-aware current time required")
    target = inspection_time(cutoff)
    return target <= now < target + timedelta(seconds=window_seconds)

def validate_venue(venue_code: str) -> None:
    if venue_code != VENUE_CODE:
        raise ValueError("Pilot is restricted to Wakamatsu (20)")
