"""Future-only head-conditional v2.6 tests, with explicit no-hindsight controls."""
from copy import deepcopy
from itertools import permutations
from scripts.conditional_one_mark_v26 import rescore
import runpy
_fixture = runpy.run_path('tests/test_hidden_path_shadow.py')
source, FROZEN, CUTOFF = (_fixture[x] for x in ('source', 'FROZEN', 'CUTOFF'))


def run(scores=None, racers=None, frozen=FROZEN, cutoff=CUTOFF):
    _bets, base, boats = source()
    return rescore(scores if scores is not None else base,
                   racers if racers is not None else boats,
                   frozen_at_utc=frozen, cutoff_at_utc=cutoff)


def test_changes_conditional_pairs_not_heads():
    _bets, ranked, racers = source()
    before = deepcopy((ranked, racers))
    new, meta = run(ranked, racers)
    assert meta["status"] == "APPLIED_UNCALIBRATED"
    assert meta["head_marginals_preserved"] and meta["head_marginal_max_error"] < 1e-8
    assert meta["adjusted_outcome_count"] > 0
    assert meta["no_additional_stake"] and not meta["result_data_used"]
    assert {x["combination"] for x in new} == {x["combination"] for x in ranked}
    assert abs(sum(x["relative_score"] for x in new) - 1.) < 1e-8
    old = {x["combination"]: x["relative_score"] for x in ranked}
    change = {x["combination"]: x["relative_score"] for x in new}
    assert change["1-4-3"] > old["1-4-3"]
    assert change["4-5-1"] > old["4-5-1"]
    assert (ranked, racers) == before


def test_fail_closed_on_missing_source_and_f():
    _bets, ranked, racers = source()
    bad = deepcopy(racers)
    bad[3]["exhibition_st"] = -.01
    new, info = run(ranked, bad)
    assert info["status"] == "NO_COMPLETE_PRE_CUTOFF_SIX_BOAT_EVIDENCE"
    assert new == ranked
    bad = deepcopy(racers)
    bad[3]["original_exhibition"] = {}
    new, info = run(ranked, bad)
    assert info["status"] == "NO_COMPLETE_PRE_CUTOFF_SIX_BOAT_EVIDENCE"
    assert new == ranked
    bad = deepcopy(racers)
    bad[3]["course"] = 1
    try:
        run(ranked, bad)
    except ValueError:
        pass
    else:
        raise AssertionError("Duplicate course must fail closed")


def test_no_late_or_postrace_or_late_race_rewriting():
    _bets, ranked, racers = source()
    try:
        run(ranked, racers, frozen="2026-11-12T02:00:00+00:00")
    except ValueError:
        pass
    else:
        raise AssertionError("Late frozen estimate accepted")
    bad = deepcopy(racers)
    bad[1]["actual_finish"] = 2
    try:
        run(ranked, bad)
    except ValueError:
        pass
    else:
        raise AssertionError("Result used")


def test_no_blanket_inside_penalty_and_zero_when_no_attacker():
    _bets, ranked, racers = source()
    for boat in racers:
        boat["average_start_timing"] = .19
        boat["original_exhibition"]["turn_time"] = 5.70
    new, meta = run(ranked, racers)
    assert meta["status"] == "NO_INDEPENDENT_ATTACKER_EVIDENCE"
    assert new == ranked


def test_formal_code_holds_future_gate_and_freezes_same_time_control():
    from pathlib import Path
    code = Path("scripts/autonomous_daily.py").read_text(encoding="utf-8")
    assert "FORMAL_CONDITIONAL_V26_ACTIVATION_UTC" in code
    assert "formal_conditional_v26=False" in code
    assert "'control_bets': control_bets" in code
    assert "'same_point_count': len(bets) == len(control_bets)" in code
    assert "pre_cutoff_leg_gate.get('final_eligible') is True" in code

def test_v26_upgrade_requires_explicit_live_exhibition_validation():
    from pathlib import Path
    source = Path("scripts/autonomous_daily.py").read_text(encoding="utf-8")
    assert "numeric_exhibition_matches_snapshot(candidate_now, upgrade)" in source
    assert 'upgrade["exhibition_input_check"] = {' in source
    assert '"verified_before_freeze": True, "six_boats_matched": 6' in source
    assert 'v26_input_recheck = bool(' in source
    assert 'v26展示6艇' not in source or '保存時照合が未確認' in source
    assert 'final_eligible=False, buy_allowed=False' in source
