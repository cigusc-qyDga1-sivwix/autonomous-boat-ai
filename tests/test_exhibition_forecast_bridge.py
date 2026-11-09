"""End-to-end pre-cutoff exhibitions change (or explicitly preserve) predictions."""
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.exhibition_bridge import inject, available_rows
from scripts.ingest_boatracecsv_exhibition import preview_signature, original_exhibition_signature
from scripts.autonomous_daily import build, preview_complete, numeric_exhibition_matches_snapshot, numeric_exhibition_coverage

JST = ZoneInfo("Asia/Tokyo")

def race():
    return {"closed_at":"2026-10-23 11:20:00",
            "racers":{str(i):{"name":f"選手{i}","national_win_rate":5.2,
                              "motor_top_2_percent":33,"average_start_timing":.16}
                       for i in range(1,7)}}

def source():
    return {"programs":{"stadiums":{"18":{"races":{"3":race()}}}}}

def row():
    sample = {
        "race_code":"202610231803","venue_code":"18","venue":"徳山","race":3,
        "source_status":"historical_research_only_not_frozen_forecast",
        "source_observed_jst":"2026-10-23T11:09:00+09:00",
        "preview_captured_at_utc":"2026-10-23T02:10:00+00:00",
        "boats":[{
            "lane":i,"course":i,"exhibition_st":.08 if i==3 else .20,
            "exhibition_time":6.6 if i==3 else 6.9,
            "tilt":0,"original_exhibition":[
                {"metric":"一周","value":30 if i==3 else 50},
                {"metric":"まわり足","value":4 if i==3 else 15},
                {"metric":"直線","value":5 if i==3 else 12},
            ]} for i in range(1,7)
        ],
        "weather":{"wind_mps":3,"wave_cm":2},
        # Deliberately wrong result: the forecast MUST never inspect it.
        "result":{"finish":"6-5-4"},"payout":{"finish":"6-5-4","yen_per_100":99900},
    }
    sample["preview_sha256"] = preview_signature(sample)
    return sample

def test_missing_csv_yields_only_baseline():
    now=datetime(2026,10,23,11,0,tzinfo=JST)
    _,ui,status=build(None,source(),now,"api",exhibition_rows={})
    assert status["new_baseline"]==1
    assert status["new_exhibition"]==0
    assert ui["forecast_races"][0]["phase"]=="baseline"

def test_six_boat_exhibition_creates_new_frozen_version_with_comparison():
    old,_,_=build(None,source(),datetime(2026,10,23,11,0,tzinfo=JST),"api")
    baseline=deepcopy(old["race_records"]["18-3"]["versions"][0])
    changed,ui,status=build(old,source(),datetime(2026,10,23,11,12,tzinfo=JST),
                            "api",exhibition_rows={row()["race_code"]:row()})
    assert status["new_exhibition"]==1
    assert changed["race_records"]["18-3"]["versions"][0]==baseline
    latest=changed["race_records"]["18-3"]["versions"][-1]
    assert latest["phase"]=="exhibition"
    assert latest["model_version"]=="tactical-outside-start-gap-v0.7-untrained"
    assert latest["model_role"]=="main"
    assert latest["legacy_control"]["model_version"]=="heuristic-0.6-csv-exhibition-test-untrained"
    assert latest["exhibition_origin"]["source"]=="BoatraceCSV"
    assert latest["racers"][2]["original_exhibition"]["lap_time"]==30
    assert latest["racers"][2]["exhibition_time"]==6.6
    assert latest["exhibition_change"]["previous_top"]==baseline["bets"][0]["combination"]
    assert latest["exhibition_change"]["new_top"]==latest["bets"][0]["combination"]
    assert latest["exhibition_change"]["bets_changed"]
    assert latest["start_v07"]["slit_signals"]
    assert latest["legacy_control"]["bets"] != baseline["legacy_control"]["bets"]
    assert latest["legacy_control"]["model_role"]=="shadow_validation"
    assert latest["sha256"]!=baseline["sha256"]
    assert sum(b["virtual_yen"] for b in latest["bets"])==50000
    assert 4<=len(latest["bets"])<=12
    assert ui["official_results"]=={}
    assert ui["forecast_races"][0]["exhibition_change"]==latest["exhibition_change"]

def test_no_late_data_can_rewrite_original_forecast():
    old,_,_=build(None,source(),datetime(2026,10,23,11,0,tzinfo=JST),"api")
    baseline=deepcopy(old["race_records"]["18-3"]["versions"][0])
    late=datetime(2026,10,23,11,25,tzinfo=JST)
    unusable, provenance=inject(race(),row(),late,"18",3)
    assert provenance is None
    assert not preview_complete(unusable)
    same,view,status=build(old,source(),late,"api",exhibition_rows={row()["race_code"]:row()})
    assert status["new_exhibition"]==0
    assert same["race_records"]["18-3"]["versions"]==[baseline]
    assert view["forecast_races"][0]["phase"]=="baseline"

def test_mismatch_or_future_timestamp_is_rejected():
    sample=row()
    wrong=deepcopy(sample);wrong["boats"][0]["course"]=2
    assert inject(race(),wrong,datetime(2026,10,23,11,12,tzinfo=JST),"18",3)[1] is None
    future=deepcopy(sample);future["source_observed_jst"]="2026-10-23T11:50:00+09:00"
    assert inject(race(),future,datetime(2026,10,23,11,12,tzinfo=JST),"18",3)[1] is None

def test_same_exhibition_is_not_repeated_and_source_revision_is_preserved():
    first,_,_=build(None,source(),datetime(2026,10,23,11,12,tzinfo=JST),"api",
                    exhibition_rows={row()["race_code"]:row()})
    version=deepcopy(first["race_records"]["18-3"]["versions"][-1])
    same,_,stats=build(first,source(),datetime(2026,10,23,11,13,tzinfo=JST),
                       "api",exhibition_rows={row()["race_code"]:row()})
    assert stats["new_exhibition"]==0
    assert same["race_records"]["18-3"]["versions"][-1]==version


def test_capture_evidence_is_bound_to_the_actual_preview_not_the_race_first_seen():
    now=datetime(2026,10,23,11,12,tzinfo=JST)
    sample=row()
    sample["first_seen_at_utc"]="2026-10-23T00:00:00+00:00"
    sample["preview_captured_at_utc"]="2026-10-23T02:25:00+00:00"
    assert inject(race(),sample,now,"18",3)[1] is None
    sample=row();sample.pop("preview_captured_at_utc")
    assert inject(race(),sample,now,"18",3)[1] is None
    sample=row();sample["boats"][0]["exhibition_time"]=6.5
    assert inject(race(),sample,now,"18",3)[1] is None


def test_changed_time_is_reflected_even_when_st_feed_timestamp_is_unchanged():
    first,_,_=build(None,source(),datetime(2026,10,23,11,12,tzinfo=JST),"api",
                    exhibition_rows={row()["race_code"]:row()})
    old=deepcopy(first["race_records"]["18-3"]["versions"])
    revised=row();revised["boats"][2]["exhibition_time"]=6.53
    revised["preview_captured_at_utc"]="2026-10-23T02:13:00+00:00"
    revised["preview_sha256"]=preview_signature(revised)
    updated,view,status=build(first,source(),datetime(2026,10,23,11,14,tzinfo=JST),"api",
                             exhibition_rows={revised["race_code"]:revised})
    versions=updated["race_records"]["18-3"]["versions"]
    assert status["new_exhibition"]==1 and status["revised_exhibition"]==1
    assert versions[:-1]==old
    assert versions[-1]["racers"][2]["exhibition_time"]==6.53
    assert versions[-1]["exhibition_origin"]["measurement_sha256"]==revised["preview_sha256"]


def test_openapi_numeric_exhibition_is_attributed_and_verified_before_freeze():
    payload = source()
    payload["programs"]["stadiums"]["18"]["races"]["3"]["preview"] = {
        "racers": {
            str(i): {"course_number": i, "start_timing": .08 if i == 3 else .20,
                     "exhibition_time": 6.60 if i == 3 else 6.90,
                     "tilt_adjustment": 0}
            for i in range(1, 7)
        }
    }
    ledger, view, status = build(None, payload, datetime(2026, 10, 23, 11, 12, tzinfo=JST), "api")
    versions = ledger["race_records"]["18-3"]["versions"]
    assert status["new_exhibition"] == 1
    assert len(versions) == 2
    assert versions[0]["phase"] == "baseline"
    final = versions[-1]
    assert final["phase"] == "exhibition"
    assert final["exhibition_origin"]["source"] == "BoatraceOpenAPI"
    assert final["exhibition_origin"]["captured_before_cutoff"] is True
    assert final["exhibition_origin"]["source_observation_time"] == "not_provided"
    assert final["exhibition_input_check"]["verified_before_freeze"] is True
    assert final["exhibition_input_check"]["source"] == "openapi"
    assert final["exhibition_input_check"]["six_boats_matched"] == 6
    assert view["forecast_races"][0]["exhibition_input_check"] == final["exhibition_input_check"]
    assert numeric_exhibition_matches_snapshot({
        **payload["programs"]["stadiums"]["18"]["races"]["3"],
        "_exhibition_origin": final["exhibition_origin"],
    }, final)
    wrong = deepcopy(final)
    wrong["racers"][2]["exhibition_time"] = 7.1
    assert not numeric_exhibition_matches_snapshot({
        **payload["programs"]["stadiums"]["18"]["races"]["3"],
        "_exhibition_origin": final["exhibition_origin"],
    }, wrong)


def test_csv_numeric_reflection_includes_original_metrics_and_rejects_mismatch():
    sample = row()
    ledger, view, status = build(
        None, source(), datetime(2026, 10, 23, 11, 12, tzinfo=JST), "api",
        exhibition_rows={sample["race_code"]: sample})
    assert status["new_exhibition"] == 1
    saved = ledger["race_records"]["18-3"]["versions"][-1]
    assert saved["exhibition_origin"]["source"] == "BoatraceCSV"
    assert saved["exhibition_input_check"]["source"] == "boatracecsv"
    assert set(saved["exhibition_input_check"]["original_metrics_matched"]) == {
        "lap_time", "turn_time", "straight_time"}
    assert saved["racers"][2]["original_exhibition"]["turn_time"] == 4
    assert saved["exhibition_input_check"]["no_result_or_payout_used"] is True
    assert status["exhibition_input_mismatch_rejected_this_run"] == 0
    assert view["forecast_races"][0]["phase"] == "exhibition"


def test_numeric_coverage_counts_actual_source_without_reclassifying_baselines():
    first, _, _ = build(None, source(), datetime(2026, 10, 23, 11, 0, tzinfo=JST), "api")
    audit = numeric_exhibition_coverage(first["race_records"], "2026-10-23")
    assert audit["total"]["listed_races"] == 1
    assert audit["total"]["baseline_or_unverified"] == 1
    assert audit["total"]["verified_exhibition"] == 0

    sample = row()
    updated, ui, _ = build(first, source(), datetime(2026, 10, 23, 11, 12, tzinfo=JST),
                           "api", exhibition_rows={sample["race_code"]: sample})
    audit = numeric_exhibition_coverage(updated["race_records"], "2026-10-23")
    assert audit["total"]["verified_exhibition"] == 1
    assert audit["total"]["csv_source"] == 1
    assert audit["total"]["six_boat_input_checked"] == 1
    assert ui["numeric_exhibition_coverage"]["by_venue"]["徳山"]["verified_exhibition"] == 1


def test_changed_openapi_six_boat_values_create_new_immutable_exhibition_version():
    payload = source()
    racers = {str(i): {
        "course_number": i, "start_timing": .20,
        "exhibition_time": 6.8 + i / 100, "tilt_adjustment": 0
    } for i in range(1, 7)}
    payload["programs"]["stadiums"]["18"]["races"]["3"]["preview"] = {"racers": racers}
    first, _, status = build(None, payload, datetime(2026, 10, 23, 11, 10, tzinfo=JST), "api")
    versions_before = deepcopy(first["race_records"]["18-3"]["versions"])
    assert status["new_exhibition"] == 1
    assert len(versions_before) == 2

    revised = deepcopy(payload)
    revised["programs"]["stadiums"]["18"]["races"]["3"]["preview"]["racers"]["3"]["exhibition_time"] = 6.63
    second, view, stats = build(first, revised, datetime(2026, 10, 23, 11, 14, tzinfo=JST), "api")
    versions_after = second["race_records"]["18-3"]["versions"]
    assert stats["new_exhibition"] == 1
    assert stats["revised_exhibition"] == 1
    assert versions_after[:-1] == versions_before
    assert versions_after[-1]["sha256"] != versions_before[-1]["sha256"]
    assert versions_after[-1]["racers"][2]["exhibition_time"] == 6.63
    assert versions_after[-1]["exhibition_input_check"]["verified_before_freeze"] is True
    assert view["numeric_exhibition_coverage"]["total"]["verified_exhibition"] == 1

    third, _, unchanged = build(second, revised, datetime(2026, 10, 23, 11, 15, tzinfo=JST), "api")
    assert unchanged["new_exhibition"] == 0
    assert third["race_records"]["18-3"]["versions"] == versions_after


def test_official_withdrawal_holds_update_without_rewriting_snapshot(monkeypatch):
    from scripts import autonomous_daily as daily

    before = datetime(2026, 10, 23, 11, 0, tzinfo=JST)
    observed = datetime(2026, 10, 23, 11, 12, tzinfo=JST)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return observed.astimezone(tz)

    ledger, _, _ = build(None, source(), before, "api")
    versions = deepcopy(ledger["race_records"]["18-3"]["versions"])
    monkeypatch.setattr(daily, "datetime", Clock)
    monkeypatch.setattr(daily, "fetch_notices", lambda day, venue: ([(3, "選手4")], "official"))
    ledger, view, status = build(ledger, source(), observed, "api", enforce_wall_clock=True)
    record = ledger["race_records"]["18-3"]
    assert record["versions"] == versions
    assert record["official_withdrawal"]["lanes"] == [4]
    assert status["new_exhibition"] == 0
    displayed = view["forecast_races"][0]
    assert displayed["ticket_status"] == "provisional"
    assert not displayed["entry_exhibition_gate"]["buy_allowed"]
    assert "4号艇" in displayed["entry_exhibition_gate"]["reason"]

    monkeypatch.setattr(daily, "fetch_notices", lambda day, venue: ([], "official"))
    clean, _, status = build(None, source(), observed, "api", enforce_wall_clock=True)
    assert "official_withdrawal" not in clean["race_records"]["18-3"]
    assert status["new_baseline"] == 1


def test_official_notice_requires_matching_venue_date_race_and_name():
    from scripts.official_withdrawals import match_lanes, parse_notices

    html = """
    <img src="/static_extra/pc/images/text_place2_18.png">
    <h3>欠場・帰郷</h3>
    <table>
      <tr><td>10/23</td><td>選手　４</td><td>３R欠場（公傷のため）</td></tr>
      <tr><td>10/23</td><td>選手５</td><td>帰郷</td></tr>
      <tr><td>10/22</td><td>選手６</td><td>3R欠場</td></tr>
    </table>
    """
    day = datetime(2026, 10, 23, tzinfo=JST).date()
    notices = parse_notices(html, day, "18")
    assert notices == [(3, "選手4")]
    assert parse_notices(html, day, "19") == []
    racers = race()["racers"]
    assert match_lanes(notices, 3, racers) == [4]
    assert match_lanes(notices, 4, racers) == []
    assert match_lanes(notices, 3, {**racers, "5": racers["4"]}) == []


def openapi_same_as_csv(sample):
    payload = source()
    payload["programs"]["stadiums"]["18"]["races"]["3"]["preview"] = {
        "racers": {
            str(b["lane"]): {
                "course_number": b["course"],
                "start_timing": b["exhibition_st"],
                "exhibition_time": b["exhibition_time"],
                "tilt_adjustment": b["tilt"],
            } for b in sample["boats"]
        }
    }
    return payload


def test_openapi_exhibition_enriches_unchanged_preview_from_timely_csv():
    sample = row()
    payload = openapi_same_as_csv(sample)
    ledger, view, status = build(
        None, payload, datetime(2026, 10, 23, 11, 12, tzinfo=JST),
        "api", exhibition_rows={sample["race_code"]: sample})
    assert status["new_exhibition"] == 1
    final = ledger["race_records"]["18-3"]["versions"][-1]
    assert final["phase"] == "exhibition"
    assert final["exhibition_origin"]["source"] == "BoatraceOpenAPI"
    assert final["exhibition_origin"]["original_exhibition_source"] == "BoatraceCSV"
    assert final["exhibition_origin"]["original_exhibition_six_boat_preview_matched"] is True
    assert final["exhibition_origin"]["original_exhibition_measurement_sha256"] == sample["preview_sha256"]
    assert final["exhibition_input_check"]["source"] == "openapi"
    assert set(final["exhibition_input_check"]["original_metrics_matched"]) == {
        "lap_time", "turn_time", "straight_time"}
    assert final["racers"][2]["original_exhibition"] == {
        "lap_time": 30, "turn_time": 4, "straight_time": 5}
    assert final["racers"][2]["exhibition_time"] == sample["boats"][2]["exhibition_time"]
    assert view["forecast_races"][0]["exhibition_origin"]["source"] == "BoatraceOpenAPI"


def test_openapi_exhibition_rejects_mismatched_or_late_csv_extras():
    sample = row()
    payload = openapi_same_as_csv(sample)
    mismatched = deepcopy(sample)
    mismatched["boats"][2]["exhibition_time"] += .01
    mismatched["preview_sha256"] = preview_signature(mismatched)
    first, _, _ = build(
        None, payload, datetime(2026, 10, 23, 11, 12, tzinfo=JST),
        "api", exhibition_rows={sample["race_code"]: mismatched})
    final = first["race_records"]["18-3"]["versions"][-1]
    assert final["phase"] == "exhibition"
    assert final["exhibition_origin"]["source"] == "BoatraceOpenAPI"
    assert "original_exhibition_source" not in final["exhibition_origin"]
    assert final["racers"][2]["original_exhibition"] == {}
    late = deepcopy(sample)
    late["preview_captured_at_utc"] = "2026-10-23T02:19:00+00:00"
    second, _, _ = build(
        None, payload, datetime(2026, 10, 23, 11, 12, tzinfo=JST),
        "api", exhibition_rows={sample["race_code"]: late})
    assert "original_exhibition_source" not in second["race_records"]["18-3"]["versions"][-1]["exhibition_origin"]


def test_new_original_metrics_create_forward_only_openapi_revision():
    sample = row()
    payload = openapi_same_as_csv(sample)
    before, _, _ = build(
        None, payload, datetime(2026, 10, 23, 11, 10, tzinfo=JST), "api")
    unchanged_versions = deepcopy(before["race_records"]["18-3"]["versions"])
    assert len(unchanged_versions) == 2
    assert unchanged_versions[-1]["racers"][2]["original_exhibition"] == {}
    after, _, status = build(
        before, payload, datetime(2026, 10, 23, 11, 12, tzinfo=JST),
        "api", exhibition_rows={sample["race_code"]: sample})
    assert status["new_exhibition"] == 1
    assert status["revised_exhibition"] == 1
    versions = after["race_records"]["18-3"]["versions"]
    assert versions[:-1] == unchanged_versions
    assert versions[-1]["racers"][2]["original_exhibition"]["straight_time"] == 5
    assert versions[-1]["sha256"] != unchanged_versions[-1]["sha256"]
    same, _, stats = build(
        after, payload, datetime(2026, 10, 23, 11, 13, tzinfo=JST),
        "api", exhibition_rows={sample["race_code"]: sample})
    assert stats["new_exhibition"] == 0
    assert same["race_records"]["18-3"]["versions"] == versions


def test_independent_original_capture_survives_late_composite_preview_revision():
    sample = row()
    payload = openapi_same_as_csv(sample)
    sample["original_exhibition_sha256"] = original_exhibition_signature(sample)
    sample["original_exhibition_captured_at_utc"] = "2026-10-23T02:10:00+00:00"
    sample["original_exhibition_observed_jst"] = "2026-10-23T11:09:00+09:00"
    # Other CSV components changed later; the whole preview was first
    # captured AFTER the safe cutoff, but these exact originals were not.
    sample["preview_captured_at_utc"] = "2026-10-23T02:19:00+00:00"
    sample["weather"]["wind_mps"] = 5
    sample["preview_sha256"] = preview_signature(sample)
    ledger, _, status = build(
        None, payload, datetime(2026, 10, 23, 11, 12, tzinfo=JST),
        "api", exhibition_rows={sample["race_code"]: sample})
    assert status["new_exhibition"] == 1
    final = ledger["race_records"]["18-3"]["versions"][-1]
    assert final["exhibition_origin"]["source"] == "BoatraceOpenAPI"
    assert final["exhibition_origin"]["original_exhibition_source"] == "BoatraceCSV"
    assert final["exhibition_origin"]["original_exhibition_measurement_sha256"] == sample["original_exhibition_sha256"]
    assert final["racers"][2]["original_exhibition"]["straight_time"] == 5
    assert final["weather_used"] is None  # CSV weather is not copied into canonical OpenAPI


def test_independent_original_capture_rejects_late_or_tampered_values():
    sample = row()
    payload = openapi_same_as_csv(sample)
    sample["original_exhibition_sha256"] = original_exhibition_signature(sample)
    sample["original_exhibition_captured_at_utc"] = "2026-10-23T02:19:00+00:00"
    sample["original_exhibition_observed_jst"] = "2026-10-23T11:09:00+09:00"
    sample["preview_captured_at_utc"] = "2026-10-23T02:19:00+00:00"
    one, _, _ = build(
        None, payload, datetime(2026, 10, 23, 11, 12, tzinfo=JST),
        "api", exhibition_rows={sample["race_code"]: sample})
    assert one["race_records"]["18-3"]["versions"][-1]["racers"][2]["original_exhibition"] == {}
    tampered = deepcopy(sample)
    tampered["original_exhibition_captured_at_utc"] = "2026-10-23T02:10:00+00:00"
    tampered["boats"][2]["original_exhibition"][2]["value"] = 5.25
    two, _, _ = build(
        None, payload, datetime(2026, 10, 23, 11, 12, tzinfo=JST),
        "api", exhibition_rows={sample["race_code"]: tampered})
    assert two["race_records"]["18-3"]["versions"][-1]["racers"][2]["original_exhibition"] == {}
