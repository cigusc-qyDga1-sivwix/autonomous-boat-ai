from datetime import datetime, timedelta, timezone
import pytest
from boat_ai.scheduler import inspection_time, due_for_inspection, validate_venue
from boat_ai.inspection import inspection_record

JST = timezone(timedelta(hours=9))

def test_ten_minutes_before_cutoff():
    cutoff = datetime(2026,10,21,20,0,tzinfo=JST)
    assert inspection_time(cutoff) == datetime(2026,10,21,19,50,tzinfo=JST)
    assert due_for_inspection(cutoff, inspection_time(cutoff))
    assert not due_for_inspection(cutoff, cutoff)

def test_only_wakamatsu():
    validate_venue("20")
    with pytest.raises(ValueError):
        validate_venue("12")

def test_missing_exhibition_never_guessed():
    result = inspection_record("20-20261021-05", {"odds": {"1-2-3": 8.2}})
    assert result["recommendation"] == "SKIP"
    assert "exhibition_st" in result["missing"]
    assert result["observed"]["exhibition_st"] is None
