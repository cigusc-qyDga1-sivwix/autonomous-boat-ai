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
    assert "自動増減" in result["point_reason"]
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


def test_primary_rating_marginals_and_selected_ticket_counts_share_one_source():
    result = prediction(
        entry(cutoff="2026-11-04 21:00:00"), "徳山", 2, "baseline",
        datetime(2026, 11, 4, 19, 20, tzinfo=JST), "fixture")
    info = result["interaction_primary"]
    assert info["role_evaluation_source"] == "same_final_ranked_120_as_primary_bets"
    roles, counts = info["main_role_shares"], info["ticket_role_counts"]
    assert set(roles) == set(str(i) for i in range(1, 7))
    for role in ("first", "second", "third"):
        assert sum(v[role] for v in roles.values()) == pytest.approx(1, abs=1e-6)
    for share in result["head_course_shares"]:
        assert roles[str(share["lane"])]["first"] == pytest.approx(share["relative_share"], abs=.0001)
    for lane in range(1, 7):
        for position, name in enumerate(("first", "second", "third")):
            assert counts[str(lane)][name] == sum(
                bet["combination"].split("-")[position] == str(lane)
                for bet in result["bets"])
    assert sum(v["first"] for v in counts.values()) == len(result["bets"])
    assert sum(v["second"] for v in counts.values()) == len(result["bets"])
    assert sum(v["third"] for v in counts.values()) == len(result["bets"])
    assert result["sha256"] == stable_hash(
        {k: v for k, v in result.items() if k != "sha256"})
    assert result["interaction_primary"]["main_role_shares"]


def test_v19_aligned_main_upgrades_only_open_races_without_rewriting_v18():
    source = {"programs": {"stadiums": {"18": {"races": {
        "2": entry(cutoff="2026-11-04 21:00:00")}}}}}
    before = datetime(2026, 11, 4, 19, 15, tzinfo=JST)
    ledger, _, _ = build(None, source, before, "fixture")
    previous = ledger["race_records"]["18-2"]["versions"][0]
    assert previous["model_version"] == "four-factor-v1.8-adaptive-points-primary-untrained"
    revised, _, status = build(
        ledger, source, datetime(2026, 11, 4, 19, 35, tzinfo=JST), "fixture")
    versions = revised["race_records"]["18-2"]["versions"]
    assert versions[0] == previous
    assert versions[-1]["model_version"] == "four-factor-v1.9-aligned-primary-untrained"
    assert versions[-1]["model_upgrade"]["previous_sha256"] == previous["sha256"]
    assert versions[-1]["interaction_primary"]["role_evaluation_source"] == "same_final_ranked_120_as_primary_bets"
    assert versions[-1]["interaction_primary"]["point_count_independent_of_prior"]
    assert status["new_model_upgrades"] >= 1
    assert sum(b["virtual_yen"] for b in versions[-1]["bets"]) == 50000
    after_cutoff = prediction(entry(cutoff="2026-11-04 21:00:00"), "徳山", 2, "baseline",
        datetime(2026, 11, 4, 19, 35, tzinfo=JST), "fixture")
    assert after_cutoff["model_version"] == "four-factor-v1.9-aligned-primary-untrained"


def test_v20_main_no_longer_expands_by_entropy_to_120():
    from scripts.autonomous_daily import INTERACTION_JUSTIFIED_MODEL
    when=datetime(2026,11,4,21,20,tzinfo=JST)
    p=prediction(entry(cutoff="2026-11-04 23:00:00"),
                 "徳山",2,"baseline",when,"fixture")
    assert p["model_version"]==INTERACTION_JUSTIFIED_MODEL
    assert p["model_role"]=="main"
    assert 4<=len(p["bets"])<=8
    assert p["point_count"]==len(p["bets"])
    policy=p["interaction_primary"]["point_policy"]
    assert policy["candidate_outcomes_analyzed"]==120
    assert policy["max_issued_ticket_points"]==24
    assert policy["selected_point_count"]==len(p["bets"])
    assert not policy["exhibition_verified"]
    assert not policy["independent_sources"]
    assert sum(b["virtual_yen"] for b in p["bets"])==50000
    assert all(b["virtual_yen"]>=1000 and b["virtual_yen"]%1000==0 for b in p["bets"])
    assert p["classification"] in ("WATCH","SKIP")
    assert p["sha256"]==stable_hash({k:v for k,v in p.items() if k!="sha256"})


def test_v20_exhibition_does_not_auto_spread_to_120():
    when=datetime(2026,11,4,21,20,tzinfo=JST)
    p=prediction(entry(cutoff="2026-11-04 23:00:00",preview=True),
                 "徳山",2,"exhibition",when,"fixture")
    policy=p["interaction_primary"]["point_policy"]
    assert p["model_version"]=="four-factor-v2.0-justified-points-primary-untrained"
    assert 4<=len(p["bets"])<=24
    if not policy["independent_sources"]:
        assert len(p["bets"])<=12
    assert sum(b["virtual_yen"] for b in p["bets"])==50000


def test_v20_is_prospective_and_previous_frozen_sha_remains():
    payload={"programs":{"stadiums":{"18":{"races":{
        "2":entry(cutoff="2026-11-04 23:00:00")}}}}}
    old=datetime(2026,11,4,21,5,tzinfo=JST)
    new=datetime(2026,11,4,21,20,tzinfo=JST)
    ledger,_,_=build(None,payload,old,"fixture")
    first=ledger["race_records"]["18-2"]["versions"][0]
    assert first["model_version"]=="four-factor-v1.9-aligned-primary-untrained"
    updated,_,status=build(ledger,payload,new,"fixture")
    versions=updated["race_records"]["18-2"]["versions"]
    assert versions[0]==first
    assert versions[-1]["model_version"]=="four-factor-v2.0-justified-points-primary-untrained"
    assert versions[-1]["model_upgrade"]["previous_sha256"]==first["sha256"]
    assert len(versions[-1]["bets"])<=24
    assert status["new_model_upgrades"]>=1
