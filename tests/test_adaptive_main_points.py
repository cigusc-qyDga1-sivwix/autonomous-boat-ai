"""Adaptive PRIMARY ticket count: synthetic distribution and budget checks."""
from itertools import permutations
import pytest
from scripts.adaptive_main_points import allocate_dynamic, stake_dynamic, VERSION

COMBOS = [f"{a}-{b}-{c}" for a,b,c in permutations(range(1,7), 3)]


def ranks(power=0):
    return [{"combination": combo,
             "relative_score": float((120-i)**power)}
            for i, combo in enumerate(COMBOS)]


def test_dynamic_points_expand_under_ambiguity_and_shrink_under_concentration():
    wide, wide_info = allocate_dynamic(ranks(0))
    narrow, narrow_info = allocate_dynamic(ranks(22))
    assert 4 <= len(narrow) < len(wide) <= 120
    assert len(wide) > 20  # not constrained by previous main model points
    assert wide_info["selected_point_count"] == len(wide)
    assert narrow_info["selected_point_count"] == len(narrow)
    assert wide_info["normalized_entropy"] > narrow_info["normalized_entropy"]


def test_100_yen_stakes_exact_50000_for_any_point_count():
    for count in (1, 4, 20, 45, 120):
        selected = ranks(2)[:count]
        bets = stake_dynamic(selected)
        assert len(bets) == count
        assert len({x["combination"] for x in bets}) == count
        assert sum(x["virtual_yen"] for x in bets) == 50000
        assert all(x["virtual_yen"] >= 100 and x["virtual_yen"] % 100 == 0 for x in bets)
        assert bets == stake_dynamic(selected)


def test_input_validation_rejects_duplicated_and_corrupted_tickets():
    arr = ranks()
    arr[1]["combination"] = arr[0]["combination"]
    with pytest.raises(ValueError):
        allocate_dynamic(arr)
    with pytest.raises(ValueError):
        allocate_dynamic(ranks()[:119])
    arr = ranks()
    arr[0]["relative_score"] = -1.0
    with pytest.raises(ValueError):
        allocate_dynamic(arr)
    with pytest.raises(ValueError):
        stake_dynamic([{"combination": "1-1-2", "relative_score": 1}])


def test_rounded_zero_tail_is_safe():
    values = ranks()
    for i in range(4, 120):
        values[i]["relative_score"] = 0.0
    picks, meta = allocate_dynamic(values)
    assert 4 <= len(picks) <= 120
    assert stake_dynamic(picks)
    assert meta["version"] == VERSION
