"""Weather acquisition, model safeguards, pre-cutoff snapshot integrity."""
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from scripts.venue_weather import VENUE_POINTS, VARIABLES, parse_batch, weather_at
from scripts.autonomous_daily import (build, prediction, condition_weights,
                                      preview_complete, weather_for_prediction)

JST = ZoneInfo("Asia/Tokyo")
CLOCK = datetime(2026, 10, 22, 8, 30, tzinfo=JST)


def forecast_payload(code: str):
    lat, lon = VENUE_POINTS[code]
    return {
        "latitude": lat, "longitude": lon,
        "hourly": {
            "time": ["2026-10-22T09:00", "2026-10-22T10:00"],
            "wind_speed_10m": [6.5, 7.0],
            "wind_direction_10m": [245, 250],
            "wind_gusts_10m": [11.0, 12.0],
            "temperature_2m": [22.0, 23.0],
            "precipitation": [0.1, 0.3],
            "weather_code": [3, 61],
        },
    }


def test_all_24_venues_have_reference_points_and_hourly_variables():
    assert len(VENUE_POINTS) == 24
    assert set(VENUE_POINTS) == {str(c) for c in range(1, 25)}
    assert "wind_direction_10m" in VARIABLES and "precipitation" in VARIABLES


def test_weather_batch_rejects_wrong_grid_location_or_missing_variables():
    d = parse_batch([forecast_payload("18"), forecast_payload("23")], ["18", "23"], CLOCK)
    assert set(d) == {"18", "23"}
    assert d["18"]["hours_jst"]["2026-10-22T10:00"]["wind_gust"] == 12.0
    assert d["18"]["source"] == "open-meteo"
    snap = weather_at(d["18"], datetime(2026,10,22,9,35,tzinfo=JST))
    assert snap["wind_speed"] == 7.0
    assert snap["site_observed"] is False
    assert snap["forecast_hour_jst"].startswith("2026-10-22T10:00")
    assert snap["issued_at_utc"] and "credit" in snap
    assert weather_at(d["18"], datetime(2026,10,22,14,30,tzinfo=JST)) is None
    with pytest.raises(ValueError, match="location"):
        parse_batch([forecast_payload("23"), forecast_payload("18")], ["18", "23"], CLOCK)
    wrong=forecast_payload("18")
    del wrong["hourly"]["wind_speed_10m"]
    with pytest.raises(ValueError, match="Incomplete"):
        parse_batch(wrong,["18"],CLOCK)


def synthetic_race(with_obs=False):
    x = {"closed_at": "2026-10-22 10:00:00",
         "racers": {str(i): {
             "name": f"Racer{i}", "national_win_rate": 5.2,
             "motor_top_2_percent": 33, "average_start_timing": .16
         } for i in range(1, 7)}}
    if with_obs:
        # Track weather may arrive before a complete six-racer exhibition.
        x["preview"]={"wind_speed":9, "wave_height":7,
                      "wind_direction_number":5, "racers":{}}
    return x


def test_weather_is_reflected_in_early_baseline_without_exhibition():
    venue = parse_batch(forecast_payload("18"), ["18"], CLOCK)
    race = synthetic_race()
    frozen, display, stat = build(None, {"programs":{"stadiums":{
        "18":{"races":{"1": race}},
    }}}, CLOCK, "fixture", venue)
    snap=frozen["race_records"]["18-1"]["versions"][0]
    assert snap["phase"] == "baseline"
    assert snap["weather_observed"] is None
    assert snap["weather_used"]["source"]=="open-meteo"
    assert snap["weather_used"]["wind_speed"] == 7.0
    assert snap["weather_adjustment"]["applied"] is True
    assert snap["weather_adjustment"]["uncertainty_exponent"] < 1
    assert snap["point_reason"].find("気象補正試験") >= 0
    assert display["weather_venue_count"]==1
    assert display["forecast_races"][0]["weather_used"]["site_observed"] is False
    assert len(display["forecast_races"][0]["bets"]) in range(4,13)
    assert sum(b["virtual_yen"] for b in snap["bets"])==50000
    old=deepcopy(snap)
    repeat,_,stats = build(frozen, {"programs":{"stadiums":{
        "18":{"races":{"1":race}}
    }}}, datetime(2026,10,22,9,15,tzinfo=JST), "fixture", venue)
    assert repeat["race_records"]["18-1"]["versions"][0]==old
    assert stats["new_baseline"]==0


def test_track_observed_wind_takes_precedence_over_nearby_forecast():
    venue=parse_batch(forecast_payload("18"),["18"],CLOCK)
    w=weather_at(venue["18"],datetime(2026,10,22,10,0,tzinfo=JST))
    observed,preferred=weather_for_prediction(synthetic_race(True),w)
    assert observed["wind_speed"]==9
    assert preferred["source"]=="boatrace_preview"
    assert preferred["site_observed"] is True
    assert preferred["wave_height"] == 7
    assert not preview_complete(synthetic_race(True))
    snap=prediction(synthetic_race(True),"徳山",1,"baseline",CLOCK,"fixture",w)
    assert snap["weather_used"]["wind_speed"]==9
    assert snap["weather_observed"]["wave_height"]==7
    assert snap["weather_adjustment"]["applied"] is True


def test_missing_weather_is_not_hallucinated_or_backfilled():
    race=synthetic_race()
    snap=prediction(race,"徳山",1,"baseline",CLOCK,"fixture")
    assert snap["weather_used"] is None
    assert snap["weather_adjustment"]["applied"] is False
    assert snap["weather_adjustment"]["uncertainty_exponent"]==1
    assert "気象未取得" in snap["evidence"]
    weights=[1.75,1.27,1.05,.9,.79,.69]
    x, reason=condition_weights(weights,None)
    assert x==weights and not reason["applied"]
    # Identical strong-wind intensity shrinks relative differences, not
    # favouring a particular course or interpreting a raw compass bearing.
    strong,_=condition_weights(weights,{"wind_speed":9,"wind_direction_degrees":180})
    assert strong[0]/strong[-1] < weights[0]/weights[-1]


def test_no_backfilled_weather_after_cutoff():
    venue=parse_batch(forecast_payload("18"),["18"],CLOCK)
    early,_,_=build(None,{"programs":{"stadiums":{
      "18":{"races":{"1":synthetic_race()}}
    }}},CLOCK,"fixture")
    historic=deepcopy(early["race_records"]["18-1"]["versions"][0])
    late=datetime(2026,10,22,11,0,tzinfo=JST)
    frozen,ui,_=build(early,{"programs":{"stadiums":{
      "18":{"races":{"1":synthetic_race()}}
    }}},late,"fixture",venue)
    assert frozen["race_records"]["18-1"]["versions"][0]==historic
    assert ui["forecast_races"][0]["weather_used"] is None
    assert ui["forecast_races"][0]["weather_adjustment"]["applied"] is False
