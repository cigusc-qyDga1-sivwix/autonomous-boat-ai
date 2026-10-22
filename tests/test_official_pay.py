"""Official payout parser and immutable settlement regression tests (offline)."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from scripts.official_pay import parse_pay_page
from scripts.autonomous_daily import build, integrate_official

JST = ZoneInfo("Asia/Tokyo")


def payout_table():
    link = lambda v,r: f"/owpc/pc/race/raceresult?rno={r}&jcd={v}&hd=20261022"
    def cells(v,r,combo,pay,pop):
        href = link(v,r)
        return "".join(f'<td data-href="{href}">{item}</td>'
                       for item in (combo,pay,pop))
    return f"""
    <html><body><h3>10月22日レースの払戻金（2場開催）</h3>
    <table class="is-strited1 is-wAuto">
    <thead>
     <tr><th rowspan="2">&nbsp;</th>
      <th colspan="3"><img alt="徳山" src="t.png" />５日目</th>
      <th colspan="3"><img alt="唐津" src="k.png" />３日目</th></tr>
     <tr><th>組番</th><th>3連単</th><th>人気</th>
      <th>組番</th><th>3連単</th><th>人気</th></tr>
    </thead><tbody>
     <tr><th>1R</th>{cells("18",1,"213","¥2,460","7")}
                       {cells("23",1,"123","¥1,530","3")}</tr>
     <tr><th>2R</th>{cells("18",2,"123","¥1,020","返")}
                       {cells("23",2,"3 1 2 4","¥1,530","8")}</tr>
     <tr><th>3R</th><td data-href="{link("18",3)}">13:47</td><td></td><td></td>
                         <td colspan="3">レース中止</td></tr>
     <tr><th>4R</th>{cells("18",4,"132","¥100","1")}
                       {cells("23",4,"123","¥999","1")}</tr>
     <tr><th>5R</th>{cells("18",5,"132","¥1,280","3")}
                       {cells("23",5,"123","¥1,530","3").replace("jcd=23","jcd=12")}</tr>
    </tbody></table></body></html>
    """


def fixture_race(cutoff="2026-10-22 10:00:00"):
    return {
        "closed_at": cutoff,
        "racers": {str(i): {
            "name": f"選手{i}", "national_win_rate": 5.0,
            "motor_top_2_percent": 31.0, "average_start_timing": .16
        } for i in range(1, 7)}
    }


def test_official_pay_parser_separates_verified_refund_cancel_and_pending():
    report = parse_pay_page(payout_table(), "20261022")
    assert set(report["venue_codes"]) == {"18", "23"}
    assert report["results"]["18-1"] == {"finish": "2-1-3", "payout_per_100": 2460}
    assert report["results"]["23-1"] == {"finish": "1-2-3", "payout_per_100": 1530}
    assert report["reviews"]["18-2"]["reason"] == "refund"
    assert report["reviews"]["23-2"]["reason"] == "ambiguous_combination"
    assert report["reviews"]["23-4"]["reason"] == "invalid_payout"
    assert report["reviews"]["23-5"]["reason"] == "race_identifier_mismatch"
    assert report["cancellations"]["23-3"]["reason"] == "レース中止"
    assert "18-3" not in report["results"]
    assert report["pending_count"] == 1


def test_official_page_date_mismatch_rejected():
    with pytest.raises(ValueError, match="heading"):
        parse_pay_page(payout_table(), "20261021")


def test_settlement_never_mutates_pre_race_bets_and_only_scores_verified():
    early = datetime(2026, 10, 22, 8, 30, tzinfo=JST)
    raw = {"programs": {"stadiums": {
        "18": {"races": {"1": fixture_race(), "2": fixture_race()}},
        "23": {"races": {"1": fixture_race(), "3": fixture_race()}},
    }}}
    ledger, view, _ = build(None, raw, early, "unofficial-preview")
    original = {
        k: [v.copy() for v in r["versions"]]
        for k,r in ledger["race_records"].items()
    }
    report = parse_pay_page(payout_table(), "20261022")
    report["source_url"] = "https://www.boatrace.jp/owpc/pc/race/pay?hd=20261022"
    report["retrieved_at_utc"] = "2026-10-22T02:00:00+00:00"
    now = datetime(2026, 10, 22, 11, 0, tzinfo=JST)
    settled = integrate_official(ledger, view, report, now)
    assert len(settled["official_results"]) == 2
    assert settled["official_results"]["2026-10-22|徳山|1"]["finish"] == "2-1-3"
    r = settled["official_results"]["2026-10-22|徳山|1"]
    assert r["verified"] is True
    assert r["source"] == "boatrace_official_pay"
    assert r["virtual_stake"] == 50000
    assert r["snapshot_sha256"] == original["18-1"][0]["sha256"]
    assert r["virtual_payout"] >= 0
    assert len(settled["settlement_alerts"]) == 2  # refund and cancelled on fixed races
    assert "2026-10-22|徳山|2" not in settled["official_results"]
    for k,version in original.items():
        assert ledger["race_records"][k]["versions"] == version

    # Repeat is idempotent and keeps historical result attribution.
    settled2 = integrate_official(ledger, view, report, now)
    assert len(settled2["official_results"]) == 2
    assert settled2["official_pay_info"]["newly_confirmed"] == 0


def test_settlement_must_wait_until_cutoff_and_forecast_exist():
    report = parse_pay_page(payout_table(), "20261022")
    report.update({
        "source_url": "https://www.boatrace.jp/owpc/pc/race/pay?hd=20261022",
        "retrieved_at_utc": "2026-10-22T00:00:00+00:00",
    })
    early = datetime(2026, 10, 22, 9, 0, tzinfo=JST)
    ledger, view, _ = build(None, {"programs":{"stadiums":{
        "18":{"races":{"1":fixture_race("2026-10-22 10:00:00")}},
    }}}, early, "fixture")
    assert integrate_official(ledger, view, report, early)["official_results"] == {}
    no_forecast, ui, _ = build(None, {"programs":{"stadiums":{
        "18":{"races":{"1":fixture_race()}},
    }}}, datetime(2026,10,22,11,0,tzinfo=JST), "fixture")
    assert integrate_official(no_forecast,ui,report,datetime(2026,10,22,11,0,tzinfo=JST))["official_results"] == {}


def test_official_correction_conflict_requires_review():
    early = datetime(2026,10,22,9,0,tzinfo=JST)
    ledger, ui, _ = build(None, {"programs":{"stadiums":{
        "18":{"races":{"1":fixture_race()}},
    }}}, early, "fixture")
    report = parse_pay_page(payout_table(), "20261022")
    report["source_url"]="https://www.boatrace.jp/owpc/pc/race/pay?hd=20261022"
    report["retrieved_at_utc"]="2026-10-22T02:00:00+00:00"
    late=datetime(2026,10,22,11,0,tzinfo=JST)
    integrate_official(ledger,ui,report,late)
    revised=dict(report)
    revised["results"]={**report["results"],"18-1":{"finish":"1-2-3","payout_per_100":2460}}
    settled=integrate_official(ledger,ui,revised,late)
    assert settled["official_results"] == {}
    assert settled["settlement_alerts"]["2026-10-22|徳山|1"]["status"] == "conflict"
