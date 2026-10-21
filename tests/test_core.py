from datetime import datetime, timezone
import pytest
from boat_ai.core import RaceInput, predict, freeze_prediction, settle_prediction

RACE = RaceInput("test-1", "2030-01-01T12:00:00+09:00", (6,5,4,3,2,1))

def test_120_probabilities():
    p = predict(RACE)
    assert len(p) == 120
    assert sum(p.values()) == pytest.approx(1.0)

def test_invalid_strengths():
    with pytest.raises(ValueError):
        predict(RaceInput("bad", RACE.cutoff_iso, (1,2,3)))

def test_cutoff_enforced():
    with pytest.raises(ValueError):
        freeze_prediction(RACE, predict(RACE), datetime(2030,1,1,4,tzinfo=timezone.utc))

def test_freeze_and_settle():
    frozen = freeze_prediction(RACE, predict(RACE), datetime(2029,12,31,tzinfo=timezone.utc))
    result = settle_prediction(frozen, "1-2-3")
    assert len(frozen["sha256"]) == 64
    assert result["prediction_sha256"] == frozen["sha256"]
