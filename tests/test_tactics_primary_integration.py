"""Precutoff course tactics integration; no evidence means unchanged tickets."""
from datetime import datetime, timezone
import pytest
from scripts.autonomous_daily import interaction_primary

REF = {"observed_until_utc": "2026-11-03T12:00:00+00:00",
       "source_sha256": "b" * 64,
       "technique": {k: .1 for k in
       ("escape", "sashi", "makuri", "makurizashi", "nuki", "megumare")},
       "defense": {"makurare": .2, "sasare": .2, "nigasashi": .2}}
NOW = "2026-11-04T01:00:00+00:00"
CUT = datetime(2026, 11, 4, 2, 0, tzinfo=timezone.utc)


def riders():
    return [{"lane": i, "course": i, "racer_id": 7000 + i,
             "relative_weight": 1 + i*.1,
             "average_start_timing": .15,
             "exhibition_time": 6.8} for i in range(1, 7)]


def evidence():
    return {"reference": REF, "profiles": {
        str(i): {"racer_id": 7000+i, "course": i, "starts": 60,
                 "wins_by_technique": {"makuri": 12 if i == 4 else 1},
                 "defended": {"makurare": {"opportunities": 40, "occurrences": i+3},
                              "sasare": {"opportunities": 40, "occurrences": 6}},
                 "observed_until_utc": "2026-11-03T20:00:00+00:00",
                 "source_sha256": "a" * 64} for i in range(1, 7)}}


def prior():
    return {"model_version": "old-main", "bets": [
        {"combination": "1-2-3", "virtual_yen": 20000},
        {"combination": "1-3-2", "virtual_yen": 10000},
        {"combination": "2-1-3", "virtual_yen": 10000},
        {"combination": "3-2-1", "virtual_yen": 10000}
    ]}


def test_valid_evidence_applies_only_bounded_adjustment():
    tickets, meta = interaction_primary(prior(), riders(), NOW, CUT, evidence())
    assert meta["racer_course_tactics"]["applied"] is True
    assert meta["racer_course_tactics"]["status"] == "APPLIED_UNCALIBRATED"
    assert len(tickets) == 4
    assert sum(t["virtual_yen"] for t in tickets) == 50000
    assert len({t["combination"] for t in tickets}) == 4
    assert meta["old_main_bets"] == prior()["bets"]


def test_missing_evidence_does_not_change_tickets():
    a, meta = interaction_primary(prior(), riders(), NOW, CUT)
    b, _ = interaction_primary(prior(), riders(), NOW, CUT, None)
    assert a == b
    assert meta["racer_course_tactics"]["status"] == "UNAVAILABLE"


def test_postcutoff_and_identity_mismatch_fail_closed():
    baseline, _ = interaction_primary(prior(), riders(), NOW, CUT)
    future = evidence()
    future["profiles"]["4"]["observed_until_utc"] = CUT.isoformat()
    after, meta = interaction_primary(prior(), riders(), NOW, CUT, future)
    assert after == baseline
    assert meta["racer_course_tactics"]["status"] == "REJECTED"
    wrong = evidence()
    wrong["profiles"]["3"]["racer_id"] = 9999
    after, meta = interaction_primary(prior(), riders(), NOW, CUT, wrong)
    assert after == baseline
    assert meta["racer_course_tactics"]["status"] == "REJECTED"


def test_insufficient_history_neutral():
    baseline, _ = interaction_primary(prior(), riders(), NOW, CUT)
    sparse = evidence()
    sparse["profiles"]["4"]["starts"] = 10
    sparse["profiles"]["4"]["wins_by_technique"]["makuri"] = 3
    after, meta = interaction_primary(prior(), riders(), NOW, CUT, sparse)
    assert after == baseline
    assert meta["racer_course_tactics"]["status"] == "REJECTED"


def test_future_reference_neutral():
    baseline, _ = interaction_primary(prior(), riders(), NOW, CUT)
    bad = evidence()
    bad["reference"] = {**REF, "observed_until_utc": CUT.isoformat()}
    actual, meta = interaction_primary(prior(), riders(), NOW, CUT, bad)
    assert actual == baseline
    assert meta["racer_course_tactics"]["status"] == "REJECTED"


def test_tactics_reweighting_keeps_rank_marginals_synchronized():
    _, neutral = interaction_primary(prior(), riders(), NOW, CUT)
    _, adjusted = interaction_primary(prior(), riders(), NOW, CUT, evidence())
    assert adjusted["racer_course_tactics"]["applied"]
    assert adjusted["main_role_shares"] != neutral["main_role_shares"]
    assert adjusted["role_evaluation_source"] == "same_final_ranked_120_as_primary_bets"
    for share in adjusted["new_head_course_shares"]:
        assert adjusted["main_role_shares"][str(share["lane"])]["first"] == pytest.approx(
            share["relative_share"], abs=.0001)
    for key in ("first", "second", "third"):
        assert sum(v[key] for v in adjusted["main_role_shares"].values()) == pytest.approx(
            1, abs=1e-6)
