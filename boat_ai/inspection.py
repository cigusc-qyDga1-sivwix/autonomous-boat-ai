"""Explicit missing-data handling; no guessed exhibition readings."""
REQUIRED = ("exhibition_st", "exhibition_time", "entry", "tilt", "wind", "wave", "odds")

def inspection_record(race_id: str, observed: dict) -> dict:
    missing = [field for field in REQUIRED if observed.get(field) is None]
    return {
        "race_id": race_id,
        "status": "incomplete" if missing else "ready_for_review",
        "missing": missing,
        "observed": {field: observed.get(field) for field in REQUIRED},
        "recommendation": "SKIP" if missing else "REVIEW",
    }
