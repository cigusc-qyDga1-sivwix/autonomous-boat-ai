"""Strong-field classification is grade-independent and read-only."""
from copy import deepcopy
from datetime import datetime

from scripts.strong_field_diagnostic import analyze
from scripts import autonomous_daily as A
from tests.test_four_factor_main import race


def racers(values):
    return [{"lane": i + 1, "course": i + 1,
             "national_win_rate": value}
            for i, value in enumerate(values)]


def heads(shares):
    return [{"lane": i + 1, "relative_share": share}
            for i, share in enumerate(shares)]


def picks():
    return [{"combination": c, "virtual_yen": 12500}
            for c in ("1-2-3", "1-3-2", "1-2-4", "1-4-2")]


def test_strong_competitive_field_detects_uncovered_winner_head():
    r = analyze(racers([7.5, 7.3, 7.0, 6.8, 4.8, 4.6]),
                heads([.31, .28, .20, .10, .06, .05]), picks(),
                phase="exhibition",
                grade_context={"status": "SOURCE_MAPPED_NOT_OFFICIAL_CROSSCHECK",
                               "grade": "GENERAL"})
    assert r["status"] == "STRONG_FIELD_CLOSE_HEADS"
    assert r["head_candidates_absent_from_tickets"] == [2]
    assert r["head_coverage_warning"]
    assert r["recommendation"] == "WATCH_CONTESTED_HEAD"
    assert not r["changes_bets"] and not r["changes_stake"]
    assert not r["results_used"] and not r["calibrated"]
    assert r["grade"] == "GENERAL"


def test_strong_field_does_not_force_spreading_when_leader_clear():
    r = analyze(racers([8.1, 8.0, 7.8, 7.1, 5.0, 4.9]),
                heads([.60, .12, .10, .08, .06, .04]), picks(),
                phase="exhibition",
                grade_context={"status": "SOURCE_MAPPED_NOT_OFFICIAL_CROSSCHECK",
                               "grade": "G1"})
    assert r["status"] == "STRONG_FIELD_HEAD_SEPARATED"
    assert not r["head_coverage_warning"]


def test_grade_alone_is_not_a_parity_signal():
    r = analyze(racers([8, 5, 4, 4, 3, 2]),
                heads([.70, .13, .07, .05, .03, .02]), picks(),
                phase="exhibition",
                grade_context={"status": "SOURCE_MAPPED_NOT_OFFICIAL_CROSSCHECK",
                               "grade": "G1"})
    assert r["status"] == "NO_STRONG_FIELD_PARITY_SIGNAL"
    assert r["grade"] == "G1"


def test_unknown_strength_and_ambiguous_actual_entry_fail_closed():
    rs = racers([7.5, 7.3, 7.0, 6.8, 4.8, 4.6])
    hs = heads([.31, .28, .20, .10, .06, .05])
    missing = deepcopy(rs)
    missing[1]["national_win_rate"] = None
    assert analyze(missing, hs, picks(), phase="exhibition")["status"] == "INSUFFICIENT_EVIDENCE"
    duplicated = deepcopy(rs)
    duplicated[2]["course"] = 2
    assert analyze(duplicated, hs, picks(), phase="exhibition")["status"] == "INSUFFICIENT_EVIDENCE"
    assert analyze(rs, hs, picks(), phase="postrace")["status"] == "INSUFFICIENT_EVIDENCE"


def test_forward_only_main_snapshot_includes_diagnostic_without_result_leak():
    data = race("2026-11-09")
    for i in range(1, 7):
        data["racers"][str(i)]["national_win_rate"] = 7 + .1 * i
    now = datetime.fromisoformat("2026-11-09T09:20:00+09:00")
    normal = A.prediction(data, "徳山", 1, "exhibition", now, "fixture")
    diag = normal["strong_field_diagnostic"]
    assert normal["model_version"] == A.CONDITIONAL_SECOND_MAIN_MODEL
    assert diag["version"].startswith("strong-field-")
    assert diag["changes_bets"] is False
    assert sum(x["virtual_yen"] for x in normal["bets"]) == 50000
    assert normal["sha256"] == A.stable_hash({k: v for k, v in normal.items()
                                               if k != "sha256"})
    with_result = deepcopy(data)
    with_result["result"] = {"finish": "6-1-2", "payout_per_100": 9000}
    post = A.prediction(with_result, "徳山", 1, "exhibition", now, "fixture")
    assert post["bets"] == normal["bets"]
    assert post["strong_field_diagnostic"] == diag


def test_official_audit_splits_strong_close_field_vs_unassessed_without_hindsight():
    from scripts.forecast_audit import analyze as audit
    from tests.test_forecast_audit import make_example
    payload = make_example()
    for race_row in payload["forecast_races"]:
        race_row["ticket_status"] = "formal"
    payload["forecast_races"][0]["strong_field_diagnostic"] = {
        "status": "STRONG_FIELD_CLOSE_HEADS", "changes_bets": False
    }
    outcome = audit(payload)
    formal = outcome["by_strong_field_formal"]
    assert formal["STRONG_FIELD_CLOSE_HEADS"]["verified_races"] == 1
    assert formal["NOT_ASSESSED"]["verified_races"] == 3
    assert formal["STRONG_FIELD_CLOSE_HEADS"]["hits"] == 1
    assert outcome["metrics"]["verified_races"] == 4

def test_close_head_omission_warns_even_outside_strong_field():
    tickets = picks()
    tickets[1]["combination"] = "3-1-2"
    tickets[2]["combination"] = "3-2-1"
    r = analyze(racers([5.8, 5.5, 5.2, 4.7, 3.2, 3.0]),
                heads([.31, .28, .20, .10, .06, .05]), tickets,
                phase="exhibition")
    assert r["status"] == "MODEL_CLOSE_HEADS_NOT_STRONG_FIELD"
    assert r["head_coverage_warning"]
    assert r["risk_flags"] == ["MODEL_CLOSE_HEAD_UNCOVERED"]
    assert r["recommendation"] == "WATCH_HEAD_RISK"
    assert r["head_candidates_absent_from_tickets"] == [2]
    assert not r["changes_bets"] and not r["changes_stake"]


def test_course1_concentration_warns_without_confusing_boat_number():
    base = racers([5.8, 5.5, 5.2, 4.7, 3.2, 3.0])
    model = heads([.50, .20, .12, .08, .06, .04])
    r = analyze(base, model, picks(), phase="exhibition")
    assert r["inside_course_lane"] == 1
    assert r["inside_course_ticket_stake_share"] == 1.
    assert r["inside_course_modeled_head_share"] == .50
    assert r["risk_flags"] == ["INSIDE_TICKET_CONCENTRATION"]
    assert r["inside_overexposure_research_warning"]
    reassigned = deepcopy(base)
    reassigned[0]["course"], reassigned[1]["course"] = 2, 1
    changed = analyze(reassigned, model, picks(), phase="exhibition")
    assert changed["inside_course_lane"] == 2
    assert changed["inside_course_ticket_stake_share"] == 0.
    assert not changed["inside_overexposure_research_warning"]


def test_diagnostic_missing_stake_and_result_phase_fail_closed():
    rs = racers([5.8, 5.5, 5.2, 4.7, 3.2, 3.0])
    hs = heads([.31, .28, .20, .10, .06, .05])
    malformed = picks()
    malformed[0].pop("virtual_yen")
    assert analyze(rs, hs, malformed, phase="exhibition")["status"] == "INSUFFICIENT_EVIDENCE"
    assert analyze(rs, hs, picks(), phase="postrace")["status"] == "INSUFFICIENT_EVIDENCE"
