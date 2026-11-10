"""Offline invariants for audited immutable predictions and official result labels."""
from copy import deepcopy
from datetime import datetime, timezone

from scripts.forecast_audit import analyze

BETS = [
    {"combination": c, "virtual_yen": amount}
    for c, amount in zip(
        ("1-2-3", "2-1-3", "1-3-2", "3-1-2",
         "1-2-4", "2-3-1", "1-3-4", "1-2-5"),
        (12000, 10000, 8000, 6000, 5000, 4000, 3000, 2000))
]


def make_example():
    races = []
    results = {}
    finishes = ("1-2-3", "1-6-2", "1-2-6", "5-1-2")
    for i, finish in enumerate(finishes, 1):
        race = {
            "venue": "徳山", "race": i,
            "cutoff_jst": "14:00", "frozen_at_utc": "2026-10-22T03:00:00+00:00",
            "model_version": "heuristic-0.2-untrained", "phase": "baseline",
            "classification": "WATCH", "sha256": f"snapshot-{i}",
            "bets": deepcopy(BETS),
        }
        races.append(race)
        results[f"2026-10-22|徳山|{i}"] = {
            "verified": True, "source": "boatrace_official_pay",
            "snapshot_sha256": race["sha256"], "finish": finish,
            "payout_per_100": 1000,
            "virtual_stake": 50000,
        }
    return {
        "event_date": "2026-10-22", "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "auto-live", "listed_races": 8,
        "forecast_races": races, "official_results": results,
        "unforecast_races": [{"venue": "徳山", "race": 5}],
        "settlement_alerts": {}
    }


def test_decomposes_errors_without_counting_missing_races_as_losses():
    report = analyze(make_example())
    metrics = report["metrics"]
    assert metrics["verified_races"] == 4
    assert metrics["hits"] == 1
    assert metrics["head_captured"] == 3
    assert metrics["first_second_captured"] == 2
    assert metrics["head_miss"] == metrics["second_miss"] == metrics["third_miss"] == 1
    assert metrics["virtual_stake_yen"] == 200000
    assert metrics["virtual_payout_yen"] == 120000
    assert metrics["virtual_profit_yen"] == -80000
    assert metrics["return_rate"] == .6
    assert report["coverage"]["unforecast_races"] == 1
    assert report["bias"]["first_bet_head_1_verified"] == 4
    assert report["bias"]["actual_winner_1_verified"] == 3
    assert report["by_model"]["heuristic-0.2-untrained"]["verified_races"] == 4


def test_wrong_snapshot_or_unverified_official_data_is_never_scored():
    payload = make_example()
    payload["official_results"]["2026-10-22|徳山|1"]["snapshot_sha256"] = "tampered"
    payload["official_results"]["2026-10-22|徳山|2"]["verified"] = False
    payload["settlement_alerts"]["2026-10-22|徳山|3"] = {"status": "review"}
    result = analyze(payload)
    assert result["metrics"]["verified_races"] == 1
    assert result["metrics"]["hits"] == 0
    assert result["exclusions"]["snapshot_mismatch"] == 1
    assert result["exclusions"]["unverified"] == 1
    assert result["exclusions"]["refund_cancelled_or_conflict"] == 1


def test_post_cutoff_and_wrong_stake_are_excluded_not_marked_losses():
    payload = make_example()
    payload["forecast_races"][0]["frozen_at_utc"] = "2026-10-22T06:00:00+00:00"
    payload["forecast_races"][1]["bets"][0]["virtual_yen"] = 13000
    report = analyze(payload)
    assert report["metrics"]["verified_races"] == 2
    assert report["exclusions"]["post_cutoff_snapshot"] == 1
    assert report["exclusions"]["budget_mismatch"] == 1


def test_read_only_does_not_mutate_inputs_or_fixed_picks():
    payload = make_example()
    original = deepcopy(payload)
    analyze(payload)
    assert payload == original


def test_v21_audit_supports_24_justified_points_but_not_25_or_subunit_stakes():
    from itertools import permutations
    from scripts.forecast_audit import _verify_race
    payload=make_example()
    race=payload['forecast_races'][0]
    race['model_version']='four-factor-v2.1-actual-entry-primary-untrained'
    names=['-'.join(map(str,p)) for p in permutations(range(1,7),3)]
    race['bets']=[{'combination':name,'virtual_yen':4000 if i==0 else 2000}
                  for i,name in enumerate(names[:24])]
    pay=payload['official_results']['2026-10-22|徳山|1']
    assert _verify_race(race,pay,'2026-10-22')[0]
    race['bets'].append({'combination':names[24],'virtual_yen':1000})
    assert _verify_race(race,pay,'2026-10-22')==(False,'bets_count_invalid')
    race['bets'].pop()
    race['bets'][0]['virtual_yen']=3900
    race['bets'][1]['virtual_yen']=2100
    assert _verify_race(race,pay,'2026-10-22')==(False,'stake_invalid')


def test_shimonoseki_8r_checkpoint_requires_frozen_v02_provenance():
    payload = make_example()
    payload["event_date"] = "2026-11-10"
    payload["listed_races"] = 4
    payload["unforecast_races"] = []
    payload["official_results"] = {}
    freezes = ("2026-11-10T09:29:09+00:00",
               "2026-11-10T09:34:00+00:00",
               "2026-11-10T09:35:00+00:00",
               "2026-11-10T09:36:00+00:00")
    for idx, row in enumerate(payload["forecast_races"]):
        row.update({"venue": "下関", "race": 8 + idx,
                    "cutoff_jst": "21:00",
                    "frozen_at_utc": freezes[idx],
                    "ticket_status": "formal", "phase": "exhibition"})
        payload["official_results"][f"2026-11-10|下関|{8 + idx}"] = {
            "verified": True, "source": "boatrace_official_pay",
            "snapshot_sha256": row["sha256"],
            "finish": ("1-2-3", "1-6-2", "1-2-6", "5-1-2")[idx],
            "payout_per_100": 1000, "virtual_stake": 50000,
        }
    approved = {"version": "strong-field-parity-diagnostic-v0.2-readonly-coverage",
                "coverage_diagnostics_read_only": True,
                "changes_bets": False, "changes_stake": False}
    payload["forecast_races"][1]["strong_field_diagnostic"] = deepcopy(approved)
    payload["forecast_races"][2]["strong_field_diagnostic"] = {
        **approved, "version": "strong-field-parity-diagnostic-v0.1-untrained"}
    payload["forecast_races"][3]["ticket_status"] = "provisional"

    frozen = deepcopy(payload)
    audit = analyze(payload)
    breakpoint = audit["head_risk_breakpoint"]
    assert breakpoint["anchor_snapshot"]["provenance_group"] == "before_checkpoint"
    assert breakpoint["anchor_snapshot"]["snapshot_sha256"] == "snapshot-1"
    assert breakpoint["frozen_formal_counts"] == {
        "before_checkpoint": 1, "after_v02_verified": 1, "after_unconfirmed": 1}
    assert breakpoint["official_verified_formal"]["before_checkpoint"]["verified_races"] == 1
    assert breakpoint["official_verified_formal"]["before_checkpoint"]["hits"] == 1
    assert breakpoint["official_verified_formal"]["after_v02_verified"]["verified_races"] == 1
    assert breakpoint["official_verified_formal"]["after_v02_verified"]["hits"] == 0
    assert breakpoint["official_verified_formal"]["after_unconfirmed"]["verified_races"] == 1
    assert audit["metrics"]["verified_races"] == 4
    assert payload == frozen


def test_shimonoseki_checkpoint_never_attributes_after_without_version():
    from scripts.forecast_audit import _head_risk_breakpoint_report
    race = {
        "venue": "下関", "race": 9,
        "ticket_status": "formal", "phase": "exhibition",
        "frozen_at_utc": "2026-11-10T09:35:00+00:00",
        "sha256": "s9",
        "strong_field_diagnostic": {
            "version": "strong-field-parity-diagnostic-v0.2-readonly-coverage",
            "coverage_diagnostics_read_only": True, "changes_bets": False,
            "changes_stake": True,
        },
    }
    rep = _head_risk_breakpoint_report([race], [], "2026-11-10")
    assert rep["frozen_formal_counts"]["after_v02_verified"] == 0
    assert rep["frozen_formal_counts"]["after_unconfirmed"] == 1
    assert rep["official_verified_formal"]["after_v02_verified"]["return_rate"] is None


def test_nationwide_breakpoint_reports_each_eligible_venue_without_backfilling():
    from scripts.forecast_audit import _head_risk_breakpoint_report
    frozen = [
        {"venue": "下関", "race": 8, "ticket_status": "formal",
         "phase": "exhibition", "frozen_at_utc": "2026-11-10T09:29:18+00:00",
         "sha256": "shimonoseki-old",
         "strong_field_diagnostic": {"version": "strong-field-parity-diagnostic-v0.1-untrained"}},
        {"venue": "福岡", "race": 11, "ticket_status": "formal",
         "phase": "exhibition", "frozen_at_utc": "2026-11-10T09:45:00+00:00",
         "sha256": "fukuoka-new",
         "strong_field_diagnostic": {
             "version": "strong-field-parity-diagnostic-v0.2-readonly-coverage",
             "coverage_diagnostics_read_only": True,
             "changes_bets": False, "changes_stake": False,
             "head_coverage_outside_parity_warning": True,
             "second_pair_coverage_warning": True}},
        {"venue": "平和島", "race": 11, "ticket_status": "formal",
         "phase": "exhibition", "frozen_at_utc": "2026-11-10T09:46:00+00:00",
         "sha256": "heiwajima-unverified",
         "strong_field_diagnostic": {
             "version": "strong-field-parity-diagnostic-v0.1-untrained"}},
        {"venue": "福岡", "race": 12, "ticket_status": "baseline",
         "phase": "baseline", "frozen_at_utc": "2026-11-10T09:47:00+00:00",
         "sha256": "fukuoka-provisional"},
    ]
    verified = [
        {"venue": "下関", "race": 8, "ticket_status": "formal",
         "snapshot_sha256": "shimonoseki-old", "stage": "hit",
         "virtual_stake_yen": 50000, "virtual_payout_yen": 100000},
        {"venue": "福岡", "race": 11, "ticket_status": "formal",
         "snapshot_sha256": "fukuoka-new", "stage": "second_miss",
         "virtual_stake_yen": 50000, "virtual_payout_yen": 0},
        # Mismatched SHA must not be included in the report's venue cohort.
        {"venue": "平和島", "race": 11, "ticket_status": "formal",
         "snapshot_sha256": "mismatched-sha", "stage": "hit",
         "virtual_stake_yen": 50000, "virtual_payout_yen": 200000},
    ]
    source = deepcopy(frozen)
    out = _head_risk_breakpoint_report(frozen, verified, "2026-11-10")
    assert len(out["eligible_venues"]) == 23
    assert out["excluded_venue"] == "江戸川"
    assert "江戸川" not in out["by_venue"]
    venues = out["by_venue"]
    assert venues["下関"]["status"] == "BEFORE_CHECKPOINT_ONLY"
    assert venues["下関"]["official_verified_formal"]["before_checkpoint"]["hits"] == 1
    assert venues["福岡"]["status"] == "AFTER_V02_VERIFIED"
    assert venues["福岡"]["formal_frozen_counts"]["after_v02_verified"] == 1
    assert venues["福岡"]["official_verified_formal"]["after_v02_verified"]["second_miss"] == 1
    assert venues["福岡"]["first_v02_pre_cutoff_snapshot"]["snapshot_sha256"] == "fukuoka-new"
    assert venues["福岡"]["new_diagnostic_warning_counts"] == {
        "uncovered_head_alerts": 1, "missing_second_pair_alerts": 1}
    assert venues["平和島"]["status"] == "AFTER_NOT_VERIFIED"
    assert venues["平和島"]["official_verified_formal"]["after_unconfirmed"]["verified_races"] == 0
    assert venues["戸田"]["status"] == "NO_FORMAL_FORECAST_RECORDED"
    assert venues["戸田"]["official_verified_formal"]["after_v02_verified"]["return_rate"] is None
    assert frozen == source


def test_venue_breakpoint_tracks_first_confirmed_snapshot_by_actual_freeze():
    from scripts.forecast_audit import _head_risk_breakpoint_report
    version = "strong-field-parity-diagnostic-v0.2-readonly-coverage"
    rows = [
        {"venue": "三国", "race": 12, "ticket_status": "formal",
         "phase": "exhibition", "frozen_at_utc": "2026-11-10T10:30:00+00:00",
         "sha256": "later", "strong_field_diagnostic": {
             "version": version, "coverage_diagnostics_read_only": True,
             "changes_bets": False, "changes_stake": False}},
        {"venue": "三国", "race": 11, "ticket_status": "formal",
         "phase": "exhibition", "frozen_at_utc": "2026-11-10T10:10:00+00:00",
         "sha256": "earlier", "strong_field_diagnostic": {
             "version": version, "coverage_diagnostics_read_only": True,
             "changes_bets": False, "changes_stake": False}},
    ]
    results = _head_risk_breakpoint_report(rows, [], "2026-11-10")
    first = results["by_venue"]["三国"]["first_v02_pre_cutoff_snapshot"]
    assert first["race"] == 11
    assert first["snapshot_sha256"] == "earlier"
    assert results["by_venue"]["三国"]["formal_frozen_counts"]["after_v02_verified"] == 2
    assert results["by_venue"]["三国"]["official_verified_formal"]["after_v02_verified"]["verified_races"] == 0
