"""Hidden 1M counterfactuals are pre-cutoff research only."""
from __future__ import annotations
from itertools import permutations
from copy import deepcopy
from datetime import datetime, timedelta

from scripts.hidden_path_shadow import analyze

FROZEN = "2026-11-12T01:15:00+00:00"
CUTOFF = "2026-11-12T10:30:00+09:00"


def source():
    racers = []
    for c in range(1, 7):
        avg, turn, expo, est = .19, 5.70, 6.80, .12
        if c == 4:
            avg, turn, expo, est = .14, 5.61, 6.77, .09
        if c == 5:
            avg, turn, expo, est = .165, 5.62, 6.77, .11
        if c == 2:
            avg, turn, expo, est = .17, 5.67, 6.78, .10
        racers.append({"lane": c, "course": c,
                       "average_start_timing": avg, "exhibition_time": expo,
                       "exhibition_st": est, "original_exhibition": {"turn_time": turn}})
    combos = ["-".join(x) for x in permutations("123456", 3)]
    picks = ["1-2-3", "1-2-4", "1-3-4", "1-3-2", "1-2-5", "1-2-6"]
    weights = {c: 1. for c in combos}
    for c in picks:
        weights[c] = 10.
    weights["4-5-1"] = 20.
    weights["4-1-5"] = 15.
    weights["2-1-4"] = 12.
    denom = sum(weights.values())
    ranked = [{"combination": c, "relative_score": weights[c]/denom} for c in combos]
    bets = [{"combination": c, "virtual_yen": 10000 if i < 4 else 5000}
            for i, c in enumerate(picks)]
    assert sum(x["virtual_yen"] for x in bets) == 50000
    return bets, ranked, racers


def run(bets=None, ranked=None, racers=None, **kw):
    orig = source()
    return analyze(bets if bets is not None else orig[0],
                   ranked if ranked is not None else orig[1],
                   racers if racers is not None else orig[2],
                   phase=kw.get("phase", "exhibition"),
                   exhibition_verified=kw.get("exhibition_verified", True),
                   frozen_at_utc=kw.get("frozen_at_utc", FROZEN),
                   cutoff_at_utc=kw.get("cutoff_at_utc", CUTOFF))


def test_hidden_follow_and_counter_research_swaps():
    bets, ranked, racers = source()
    before = deepcopy((bets, ranked, racers))
    result = run(bets, ranked, racers)
    assert result["version"] == "hidden-1m-counterfactual-shadow-v0.1"
    assert result["status"] == "PRE_CUTOFF_SHADOW_SWAP_ONLY"
    assert result["replacement_candidate"] in ("4-5-1", "4-1-5", "2-1-4")
    assert result["replacement_candidate"] not in {x["combination"] for x in bets}
    assert result["replacement_victim"] not in {x["combination"] for x in bets[:4]}
    assert result["no_additional_stake"] and result["not_formal"]
    assert not result["result_data_used"] and not result["odds_used"]
    assert result["same_point_count"] is True
    assert len(result["shadow_alternative_bets"]) == len(bets)
    assert sum(x["virtual_yen"] for x in result["shadow_alternative_bets"]) == 50000
    assert (bets, ranked, racers) == before
    assert {x["scenario"] for x in result["candidates"]} >= {"OUTER_ATTACK_FOLLOWER",
                                                              "OUTER_ATTACK_INSIDE_SURVIVES"}


def test_unverified_phase_never_produces_candidate():
    assert run(phase="baseline") is None
    assert run(exhibition_verified=False) is None


def test_incomplete_or_invalid_provenance_fails_closed():
    bets, ranked, racers = source()
    bad = deepcopy(racers)
    bad[0]["course"] = 2
    try:
        run(bets, ranked, bad)
    except ValueError:
        pass
    else:
        raise AssertionError("Duplicate actual course accepted")
    bad = deepcopy(racers)
    bad[3]["exhibition_st"] = None
    try:
        run(bets, ranked, bad)
    except ValueError:
        pass
    else:
        raise AssertionError("Missing exhibition accepted")
    for timestamp in ["2026-11-12T01:29:00+00:00", "2026-11-12T02:00:00+00:00"]:
        try:
            run(frozen_at_utc=timestamp)
        except ValueError:
            pass
        else:
            raise AssertionError("Late candidate accepted")


def test_no_hindsight_or_flying_start_shortcuts():
    bets, ranked, racers = source()
    bad = deepcopy(racers)
    bad[3]["actual_finish"] = 1
    try:
        run(bets, ranked, bad)
    except ValueError:
        pass
    else:
        raise AssertionError("Postrace field accepted")
    bad = deepcopy(racers)
    bad[3]["exhibition_st"] = -.01
    out = run(bets, ranked, bad)
    assert not out or all(x["evidence"]["attacking_lane"] != 4
                          for x in out["candidates"])
    bad = deepcopy(racers)
    bad[3]["average_start_timing_imputed"] = True
    out = run(bets, ranked, bad)
    assert not out or all(x["evidence"]["attacking_lane"] != 4
                          for x in out["candidates"])


def test_missing_two_independent_signals_does_not_raise_alarm():
    bets, ranked, racers = source()
    for racer in racers:
        racer["original_exhibition"]["turn_time"] = 5.65
    out = run(bets, ranked, racers)
    assert out["status"] == "NO_SUPPORTED_PATH"
    assert out["candidate_count"] == 0
