"""Forward-only, immutable formal-vs-reselection-shadow evidence checks."""
from copy import deepcopy
from datetime import datetime
from itertools import permutations

from scripts.coverage_reselection_shadow import review, VERSION
from scripts import autonomous_daily as A
from tests.test_four_factor_main import race


def fixture():
    raw = {"-".join(p): 0.0001 for p in permutations("123456", 3)}
    raw.update({
        "1-3-5": .0624, "1-5-3": .0608, "1-5-6": .0398,
        "5-1-3": .0395, "1-5-4": .0357, "1-5-2": .0345,
        "5-3-1": .0292, "3-1-5": .0291,
    })
    total = sum(raw.values())
    ranked = [{"combination": k, "relative_score": v / total}
              for k, v in raw.items()]
    bets = [
        {"combination": "1-3-5", "virtual_yen": 11000},
        {"combination": "1-5-3", "virtual_yen": 11000},
        {"combination": "1-5-6", "virtual_yen": 7000},
        {"combination": "5-1-3", "virtual_yen": 7000},
        {"combination": "1-5-4", "virtual_yen": 7000},
        {"combination": "1-5-2", "virtual_yen": 7000},
    ]
    diagnostic = {
        "version": "strong-field-parity-diagnostic-v0.2-readonly-coverage",
        "coverage_diagnostics_read_only": True, "results_used": False,
        "second_pair_coverage_status": "ASSESSED",
        "missing_top_second_pairs": [
            {"head_lane": 5, "second_lane": 3,
             "model_relative_share_given_head": .216842}
        ],
        "uncovered_top_two_heads": [],
    }
    scenarios = [
        {"scenario": "head_course_1",
         "top_3": [["1-3-5", .20], ["1-5-3", .15], ["1-5-6", .10]]},
        {"scenario": "head_course_2",
         "top_3": [["2-1-5", .2], ["2-5-1", .1], ["2-1-3", .1]]},
        {"scenario": "head_course_3",
         "top_3": [["3-1-5", .2], ["3-5-1", .1], ["3-1-6", .1]]},
        {"scenario": "head_course_4",
         "top_3": [["4-1-5", .2], ["4-5-1", .1], ["4-1-3", .1]]},
        {"scenario": "head_course_5",
         "top_3": [["5-1-3", .2], ["5-3-1", .1], ["5-1-6", .1]]},
        {"scenario": "head_course_6",
         "top_3": [["6-1-5", .2], ["6-5-1", .1], ["6-1-3", .1]]},
    ]
    policy = {"version": "justified-main-points-v2.0-conservative-untrained"}
    return bets, ranked, diagnostic, scenarios, policy


def test_supported_uncovered_pair_produces_bounded_research_only_swap():
    args = fixture()
    unchanged = deepcopy(args)
    result = review(*args, phase="exhibition", exhibition_verified=True)
    assert result["version"] == VERSION
    assert result["status"] == "PROPOSED_FOR_FORWARD_TEST_ONLY"
    assert result["replacement"] == {
        "removed": "1-5-2", "added": "5-3-1",
        "coverage_kind": "uncovered_second_pair"
    }
    assert result["not_formal"] and result["formal_bets_unchanged"]
    assert result["no_additional_stake"] and not result["results_used"]
    assert not result["odds_used"] and not result["calibrated"]
    assert result["same_point_count"] and result["point_count_matched"]
    assert len(result["forecast_alternative_bets"]) == len(args[0])
    assert sum(b["virtual_yen"] for b in result["forecast_alternative_bets"]) == 50000
    assert "5-3-1" in {b["combination"] for b in result["forecast_alternative_bets"]}
    assert args == unchanged


def test_uncovered_head_has_independent_model_path_review():
    args = fixture()
    bets, ranked, diagnostic, scenarios, policy = args
    diagnostic["uncovered_top_two_heads"] = [{"lane": 3, "model_relative_share": .19}]
    diagnostic["missing_top_second_pairs"] = []
    r = review(*args, phase="exhibition", exhibition_verified=True)
    assert r["status"] == "PROPOSED_FOR_FORWARD_TEST_ONLY"
    assert r["replacement"]["added"] == "3-1-5"
    assert r["replacement"]["coverage_kind"] == "uncovered_head"


def test_unverified_exhibition_and_invalid_sources_fail_closed():
    args = fixture()
    missing = review(*args, phase="baseline", exhibition_verified=True)
    assert missing["status"] == "NOT_ELIGIBLE"
    assert "forecast_alternative_bets" not in missing
    unverified = review(*args, phase="exhibition", exhibition_verified=False)
    assert unverified["status"] == "NOT_ELIGIBLE"
    invalid = list(deepcopy(args))
    invalid[1][0]["combination"] = invalid[1][1]["combination"]
    result = review(*invalid, phase="exhibition", exhibition_verified=True)
    assert result["status"] == "NOT_ELIGIBLE"
    assert result["reason"] == "invalid_ranking_row"


def test_scenario_absence_or_low_relative_score_does_not_force_ticket():
    args = list(fixture())
    scenarios = deepcopy(args[3])
    scenarios[4]["top_3"][1][0] = "5-1-4"
    args[3] = scenarios
    r = review(*args, phase="exhibition", exhibition_verified=True)
    assert r["status"] == "NO_SUPPORTED_COVERAGE_CANDIDATE"
    assert "forecast_alternative_bets" not in r
    args = list(fixture())
    ranked = deepcopy(args[1])
    for row in ranked:
        if row["combination"] == "5-3-1":
            row["relative_score"] = .00001
    norm = sum(row["relative_score"] for row in ranked)
    for row in ranked:
        row["relative_score"] /= norm
    args[1] = ranked
    weak = review(*args, phase="exhibition", exhibition_verified=True)
    assert weak["status"] == "NO_QUALIFIED_SWAP"
    assert weak["candidate_review"][0]["decision"] == "REJECT"


def test_formal_prediction_unchanged_and_research_field_frozen_with_sha():
    day = "2026-11-11"
    now = datetime.fromisoformat("2026-11-11T09:20:00+09:00")
    data = race(day)
    saved = A.prediction(data, "徳山", 1, "exhibition", now, "fixture")
    assert saved["model_version"] == A.CONDITIONAL_SECOND_MAIN_MODEL
    assert sum(b["virtual_yen"] for b in saved["bets"]) == 50000
    shadow = saved["coverage_reselection_shadow"]
    assert shadow["version"] == VERSION
    assert shadow["model_role"] == "research_shadow"
    assert shadow["formal_bets_sha256"] == A.stable_hash({"bets": saved["bets"]})
    assert shadow["results_used"] is False and shadow["not_formal"] is True
    assert saved["sha256"] == A.stable_hash({k: v for k, v in saved.items()
                                               if k != "sha256"})
    with_results = deepcopy(data)
    with_results["result"] = {"finish": "6-5-4", "payout_per_100": 999999}
    rechecked = A.prediction(with_results, "徳山", 1, "exhibition", now, "fixture")
    assert saved["bets"] == rechecked["bets"]
    assert shadow == rechecked["coverage_reselection_shadow"]
    older = A.prediction(race("2026-11-09"), "徳山", 1, "exhibition",
                         datetime.fromisoformat("2026-11-09T09:20:00+09:00"),
                         "fixture")
    assert "coverage_reselection_shadow" not in older
