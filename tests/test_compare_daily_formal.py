from copy import deepcopy
import pytest
from scripts.compare_daily_formal import compare


def report(day, n, hit, head, second, third, paid):
    return {
        "event_date": day,
        "by_model": {"four-factor-v2.2-linked-primary-untrained": {}},
        "by_ticket_status": {
            "formal": {
                "verified_races": n, "hits": hit,
                "head_captured": n-head,
                "first_second_captured": hit+third,
                "head_miss": head, "second_miss": second, "third_miss": third,
                "virtual_stake_yen": n*50000, "virtual_payout_yen": paid,
                "virtual_profit_yen": paid-n*50000,
            },
            "provisional": {"verified_races": 1, "hits": 1},
        },
    }


def test_formal_only_compare_november_8_to_november_7():
    yesterday = report("2026-11-07", 101, 48, 32, 16, 5, 5171900)
    current = report("2026-11-08", 109, 47, 27, 25, 10, 4789500)
    a = compare(current, yesterday)
    assert a["formal_only"] and a["read_only"] and not a["actual_wagers"]
    assert a["current_formal"]["hits"] == 47
    assert a["previous_formal"]["hits"] == 48
    assert a["day_over_day"]["hits"] == -1
    assert a["day_over_day"]["second_miss"] == 9
    assert a["day_over_day"]["return_rate_pp"] < 0
    assert a["day_over_day"]["hit_rate_pp"] < 0
    assert a["current_formal"]["virtual_profit_yen"] == -660500


def test_refuse_nonconsecutive_or_missing_formal_or_inconsistent_stages():
    prior = report("2026-11-07", 101, 48, 32, 16, 5, 5171900)
    current = report("2026-11-08", 109, 47, 27, 25, 10, 4789500)
    with pytest.raises(ValueError, match="consecutive"):
        compare(report("2026-11-10", 109, 47, 27, 25, 10, 4789500), prior)
    p = deepcopy(current)
    del p["by_ticket_status"]["formal"]
    with pytest.raises(ValueError, match="Formal group unavailable"):
        compare(p, prior)
    p = deepcopy(current)
    p["by_ticket_status"]["formal"]["second_miss"] = 99
    with pytest.raises(ValueError, match="Stage accounting"):
        compare(p, prior)
