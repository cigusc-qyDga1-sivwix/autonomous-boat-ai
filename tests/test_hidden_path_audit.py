"""Forward-only official reconciliation for hidden 1M alternative tickets."""
from copy import deepcopy
import hashlib
import json
from scripts.hidden_path_shadow import analyze as detect
from scripts.forecast_audit import _hidden_path_forward_report
import runpy
_fixture = runpy.run_path('tests/test_hidden_path_shadow.py')
source, FROZEN, CUTOFF = (_fixture[x] for x in ('source', 'FROZEN', 'CUTOFF'))

DAY = "2026-11-12"

def setup():
    bets, scores, racers = source()
    hidden = detect(bets, scores, racers, phase="exhibition",
                    exhibition_verified=True, frozen_at_utc=FROZEN,
                    cutoff_at_utc=CUTOFF)
    assert hidden["status"] == "PRE_CUTOFF_SHADOW_SWAP_ONLY"
    hidden["formal_bets_sha256"] = hashlib.sha256(json.dumps({"bets": bets}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    hidden["ranked_source_sha256"] = "c"*64
    snapshot = {"venue": "三国", "race": 4, "phase": "exhibition",
                "ticket_status": "formal", "cutoff_jst": "10:30",
                "frozen_at_utc": FROZEN, "sha256": "a"*64,
                "model_version": "four-factor-v2.5-evidence-head-switch-untrained",
                "bets": bets, "hidden_path_shadow": hidden}
    official = {f"{DAY}|三国|4": {
        "verified": True, "source": "boatrace_official_pay",
        "snapshot_sha256": snapshot["sha256"], "virtual_stake": 50000,
        "finish": hidden["replacement_candidate"], "payout_per_100": 20000}}
    return snapshot, official

def test_matched_hidden_candidate_recovers_missed_head_and_hit():
    snap, paid = setup()
    report = _hidden_path_forward_report([snap], paid, {}, DAY)
    assert report["official_verified_equal_point_pairs"] == 1
    assert report["formal"]["hits"] == 0
    assert report["research_shadow"]["hits"] == 1
    assert report["head_misses_recovered"] == 1
    assert report["new_head_misses"] == 0
    assert report["research_shadow"]["virtual_stake_yen"] == 50000
    assert report["not_formal_performance"]
    assert report["by_scenario"]["OUTER_ATTACK_FOLLOWER"]["research_shadow"]["hits"] == 1

def test_rejects_retrospective_or_unmatched_controls():
    snap, paid = setup()
    late = deepcopy(snap)
    late["hidden_path_shadow"]["frozen_at_utc"] = "2026-11-12T03:00:00Z"
    report = _hidden_path_forward_report([late], paid, {}, DAY)
    assert report["official_verified_equal_point_pairs"] == 0
    assert report["exclusions"]["invalid_or_unmatched_pre_cutoff_control"] == 1
    changed = deepcopy(snap)
    changed["hidden_path_shadow"]["formal_control_bets"][0]["combination"] = "4-5-1"
    report = _hidden_path_forward_report([changed], paid, {}, DAY)
    assert report["official_verified_equal_point_pairs"] == 0
    assert report["exclusions"]["invalid_or_unmatched_pre_cutoff_control"] == 1

def test_unverified_and_conflicted_not_losses():
    snap, paid = setup()
    unverified = deepcopy(paid)
    unverified[f"{DAY}|三国|4"]["verified"] = False
    report = _hidden_path_forward_report([snap], unverified, {}, DAY)
    assert report["official_verified_equal_point_pairs"] == 0
    assert report["formal"]["verified_races"] == 0
    report = _hidden_path_forward_report([snap], paid, {f"{DAY}|三国|4": "review"}, DAY)
    assert report["official_verified_equal_point_pairs"] == 0
    assert report["exclusions"]["official_refund_or_conflict"] == 1

def test_hidden_path_passes_unchanged_from_frozen_snapshot_to_live_view():
    """Prevent silent disappearance: the live JSON projection must carry
    the signed snapshot's independent research evidence, not regenerate it."""
    import ast
    from pathlib import Path
    tree = ast.parse(Path('scripts/autonomous_daily.py').read_text(encoding='utf-8'))
    candidates = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.For) and isinstance(node.target, ast.Name)
        and node.target.id == 'extra'
        and isinstance(node.iter, ast.Tuple)
        and 'hidden_path_shadow' in [
            el.value for el in node.iter.elts if isinstance(el, ast.Constant)
        ]
    ]
    assert candidates, 'Live view is omitting the frozen hidden-path shadow'
    assert any(
        isinstance(n, ast.Assign)
        and any(
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Name)
            and target.value.id == 'r'
            for target in n.targets
        )
        and isinstance(n.value, ast.Subscript)
        and isinstance(n.value.value, ast.Name)
        and n.value.value.id == 'current'
        for node in candidates for n in ast.walk(node)
    ), 'Live view must copy frozen source, not compute a new forecast'
