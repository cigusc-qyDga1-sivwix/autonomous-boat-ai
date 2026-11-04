"""Forward-only main promotion checks with same-time old-main control."""
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from scripts.autonomous_daily import (
    prediction, build, INTERACTION_MAIN_MODEL, stable_hash,
)

JST = ZoneInfo("Asia/Tokyo")


def entry(cutoff="2026-11-04 15:00:00", preview=False):
    racers = {str(i): {"name": f"racer{i}", "national_win_rate": 5.1 + .1*i,
                       "motor_top_2_percent": 30 + i,
                       "average_start_timing": .15 + i*.001} for i in range(1, 7)}
    result = {"closed_at": cutoff, "racers": racers}
    if preview:
        result["preview"] = {
            "wind_speed": 2, "wave_height": 1, "wind_direction_number": 5,
            "racers": {str(i): {"course_number": i, "start_timing": .1 + i*.01,
                               "exhibition_time": 6.8 + i*.005} for i in range(1, 7)}
        }
    return result


def test_promoted_baseline_is_primary_and_control_is_preserved():
    now = datetime(2026, 11, 4, 13, 0, tzinfo=JST)
    result = prediction(entry(), "徳山", 1, "baseline", now, "fixture")
    assert result["model_version"] == INTERACTION_MAIN_MODEL
    assert result["model_role"] == "main"
    assert result["interaction_primary"]["uncalibrated"] is True
    assert result["interaction_primary"]["old_main_model_version"] != result["model_version"]
    assert result["interaction_primary"]["old_main_bets"]
    assert result["head_course_shares"] == result["interaction_primary"]["new_head_course_shares"]
    assert "1号艇着外" in result["point_reason"]
    assert "イン着外" in result["scenario"]
    assert len(result["bets"]) == len(result["interaction_primary"]["old_main_bets"])
    assert sum(b["virtual_yen"] for b in result["bets"]) == 50000
    assert sum(b["virtual_yen"] for b in result["interaction_primary"]["old_main_bets"]) == 50000
    assert result["sha256"] == stable_hash({k: v for k, v in result.items() if k != "sha256"})


def test_exhibition_stays_main_and_uses_frozen_input():
    result = prediction(entry(preview=True), "徳山", 1, "exhibition",
                        datetime(2026, 11, 4, 13, 0, tzinfo=JST), "fixture")
    assert result["model_version"] == INTERACTION_MAIN_MODEL
    assert result["phase"] == "exhibition"
    assert len(result["bets"]) == len(result["interaction_primary"]["old_main_bets"])


def test_old_snapshot_is_not_rewritten_during_forward_upgrade():
    now = datetime(2026, 11, 4, 13, 0, tzinfo=JST)
    race = entry()
    source = {"programs": {"stadiums": {"18": {"races": {"1": race}}}}}
    ledger, app, _ = build(None, source, now, "fixture")
    snap = ledger["race_records"]["18-1"]["versions"][0]
    assert snap["model_version"] == INTERACTION_MAIN_MODEL
    ledger2, app2, summary = build(ledger, source, now, "fixture")
    assert ledger2["race_records"]["18-1"]["versions"][0] == snap
    assert summary["new_baseline"] == 0


def test_no_backdated_main_creation():
    with pytest.raises(ValueError):
        prediction(entry(cutoff="2026-11-04 11:00:00"), "徳山", 1, "baseline",
                   datetime(2026, 11, 4, 11, 0, tzinfo=JST), "fixture")

def test_formal_scenario_can_include_one_outside_top3():
    from scripts.autonomous_daily import interaction_primary
    racers = [{"lane": i, "course": i, "relative_weight": w,
               "average_start_timing": .16, "exhibition_time": None}
              for i, w in enumerate((1.75, 1.27, 1.05, .90, .79, .69), 1)]
    older = {"model_version": "prior", "bets": [
        {"combination": f"1-2-{i}", "virtual_yen": 10000} for i in (3, 4, 5, 6)]}
    tickets, meta = interaction_primary(
        older, racers, "2026-11-04T00:01:00+00:00",
        datetime(2026, 11, 4, 1, 0, tzinfo=ZoneInfo("UTC")))
    assert 0 < meta["course1_outside_top3_relative_mass"] < 1
    assert meta["course1_outside_top3_selected"] >= 1
    assert any("1" not in b["combination"].split("-") for b in tickets)
    assert sum(b["virtual_yen"] for b in tickets) == 50000
    assert len(tickets) == len(older["bets"])


def test_formal_scenario_is_not_forced_to_exclude_one_with_tiny_risk():
    from scripts.autonomous_daily import interaction_primary
    racers = [{"lane": i, "course": i,
               "relative_weight": 80.0 if i == 1 else .01,
               "average_start_timing": None, "exhibition_time": None}
              for i in range(1, 7)]
    older = {"model_version": "prior", "bets": [
        {"combination": f"1-2-{i}", "virtual_yen": 10000} for i in (3, 4, 5, 6)]}
    tickets, meta = interaction_primary(
        older, racers, "2026-11-04T00:01:00+00:00",
        datetime(2026, 11, 4, 1, 0, tzinfo=ZoneInfo("UTC")))
    assert meta["course1_outside_top3_relative_mass"] < .25
    assert not meta["conditional_coverage_applied"]
    assert all("1" in b["combination"].split("-") for b in tickets)

def test_new_primary_respects_venue_weather_adjusted_scores():
    from scripts.autonomous_daily import interaction_primary
    people = [{"lane": i, "course": i, "relative_weight": 1.0,
               "average_start_timing": None, "exhibition_time": None}
              for i in range(1, 7)]
    older = {"model_version": "old", "bets": [
        {"combination": f"1-2-{i}", "virtual_yen": 10000} for i in range(3, 7)]}
    cutoff = datetime(2026, 11, 4, 1, 0, tzinfo=ZoneInfo("UTC"))
    _, a = interaction_primary(older, people, "2026-11-04T00:01:00+00:00", cutoff)
    _, b = interaction_primary(older, people, "2026-11-04T00:01:00+00:00",
                               cutoff, scored_weights=[3, 1, 1, 1, 1, 1])
    assert a["new_head_course_shares"] != b["new_head_course_shares"]
    assert b["uses_venue_weather_adjusted_base"]
    assert abs(sum(x["relative_share"] for x in b["new_head_course_shares"]) - 1) <= .001


def test_v18_main_adapts_points_without_following_old_model():
    result = prediction(
        entry(cutoff="2026-11-04 20:00:00"), "徳山", 2, "baseline",
        datetime(2026, 11, 4, 18, 10, tzinfo=JST), "fixture")
    assert result["model_version"] == "four-factor-v1.8-adaptive-points-primary-untrained"
    assert result["model_role"] == "main"
    policy = result["interaction_primary"]["point_policy"]
    assert result["interaction_primary"]["point_count_independent_of_prior"]
    assert policy["point_selection"] == "entropy_and_relative_score_mass"
    assert policy["candidate_count"] == 120
    assert result["point_count"] == policy["selected_point_count"]
    assert 4 <= result["point_count"] <= 120
    assert sum(b["virtual_yen"] for b in result["bets"]) == 50000
    assert all(b["virtual_yen"] % 100 == 0 and b["virtual_yen"] >= 100
               for b in result["bets"])
    assert "可変" in result["point_reason"]
    assert result["sha256"] == stable_hash({k:v for k,v in result.items() if k != "sha256"})


def test_v18_upgrades_only_before_cutoff_and_preserves_old_sha():
    source = {"programs": {"stadiums": {"18": {"races": {
        "2": entry(cutoff="2026-11-04 20:00:00")}}}}}
    old_now = datetime(2026, 11, 4, 17, 55, tzinfo=JST)
    ledger, _, _ = build(None, source, old_now, "fixture")
    first = ledger["race_records"]["18-2"]["versions"][0]
    assert first["model_version"] == "four-factor-v1.7-interaction-inside-failure-untrained"
    revised, _, status = build(
        ledger, source, datetime(2026, 11, 4, 18, 12, tzinfo=JST), "fixture")
    versions = revised["race_records"]["18-2"]["versions"]
    assert versions[0] == first
    assert versions[-1]["model_version"] == "four-factor-v1.8-adaptive-points-primary-untrained"
    assert versions[-1]["model_upgrade"]["previous_sha256"] == first["sha256"]
    assert status["new_model_upgrades"] >= 1


def test_v18_not_backdated_to_previous_activation_or_past_cutoff():
    old = prediction(
        entry(cutoff="2026-11-04 20:00:00"), "徳山", 2, "baseline",
        datetime(2026, 11, 4, 17, 55, tzinfo=JST), "fixture")
    assert old["model_version"] == "four-factor-v1.7-interaction-inside-failure-untrained"
    with pytest.raises(ValueError):
        prediction(entry(cutoff="2026-11-04 18:00:00"), "徳山", 2, "baseline",
                   datetime(2026, 11, 4, 18, 10, tzinfo=JST), "fixture")
