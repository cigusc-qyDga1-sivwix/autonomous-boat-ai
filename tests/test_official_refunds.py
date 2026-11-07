"""Offline regression coverage for BOAT LAB's independent official returns."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from scripts.autonomous_daily import integrate_official
from scripts.official_refunds import parse_official_refund, official_race_url
from scripts.reconcile_official_backlog import merge_verified

DAY = "2026-11-07"
JST = ZoneInfo("Asia/Tokyo")
DETAIL = official_race_url("20261107", "11", 7)
PAY_URL = "https://www.boatrace.jp/owpc/pc/race/pay?hd=20261107"


def race_html(boat="4", marker="Ｆ", result="5-2-3", payout="¥3,760"):
    return f"""
    <html><body><h2><img alt="びわこ" src="venue.png"></h2>
    <p>11月7日３日目</p><table>
      <tr><th>着</th><th>枠</th><th>ボートレーサー</th></tr>
      <tr><td>{marker}</td><td>{boat}</td><td>事故艇</td></tr>
    </table><table><tr><th>勝式</th><th>組番</th><th>払戻金</th></tr>
      <tr><td>3連単</td><td>{result}</td><td>{payout}</td></tr>
      <tr><td>3連複</td><td>2=3=5</td><td>¥220</td></tr>
    </table><h3>返還</h3><p>{boat}</p><h3>決まり手</h3><p>まくり差し</p>
    </body></html>"""


def test_official_refund_requires_explicit_boat_and_matching_payout():
    actual = parse_official_refund(race_html(), "20261107", "びわこ", "5-2-3", 3760)
    assert actual == {
        "refunded_boats": [4], "refund_reasons": {"4": "F"},
        "void_trifecta": False,
    }
    scratch = parse_official_refund(race_html(boat="6", marker="欠場"),
                                   "20261107", "びわこ", "5-2-3", 3760)
    assert scratch["refunded_boats"] == [6]
    assert scratch["refund_reasons"] == {"6": "欠場"}
    for wrong in [
        ("20261106", "びわこ", "5-2-3", 3760),
        ("20261107", "三国", "5-2-3", 3760),
        ("20261107", "びわこ", "5-3-2", 3760),
        ("20261107", "びわこ", "5-2-3", 3770),
    ]:
        with pytest.raises(ValueError):
            parse_official_refund(race_html(), *wrong)
    with pytest.raises(ValueError):
        parse_official_refund(race_html().replace("<p>4</p><h3>決まり手",
                                                 "<p>未取得</p><h3>決まり手"),
                              "20261107", "びわこ", "5-2-3", 3760)


def test_official_void_trifecta_and_refund():
    page = race_html(result="不成立", payout="返")
    evidence = parse_official_refund(page, "20261107", "びわこ", None, None, True)
    assert evidence["void_trifecta"] is True and evidence["refunded_boats"] == [4]


def fixture():
    bets = [
        {"combination": "5-2-3", "virtual_yen": 10000},
        {"combination": "4-1-2", "virtual_yen": 20000},
        {"combination": "1-2-3", "virtual_yen": 10000},
        {"combination": "6-5-2", "virtual_yen": 10000},
    ]
    record = {
        "venue": "びわこ", "race": 7, "official_review": "refund",
        "versions": [{"bets": bets, "phase": "exhibition",
                      "sha256": "a" * 64,
                      "cutoff_iso_jst": "2026-11-07T13:16:00+09:00"}],
    }
    return ({"event_date": DAY, "race_records": {"11-7": record}},
            {"event_date": DAY, "official_results": {}})


def pay_record(finish="5-2-3", payout=3760, void=False):
    return {
        "date": DAY, "source_url": PAY_URL,
        "retrieved_at_utc": "2026-11-07T05:00:00Z",
        "results": {"11-7": {
            "finish": None if void else finish,
            "payout_per_100": 0 if void else payout,
            "refunded_boats": [4], "refund_reasons": {"4": "F"},
            "refund_source_url": DETAIL, "void_trifecta": void,
        }}, "reviews": {}, "cancellations": {},
    }


def test_accurate_partial_refund_plus_hit_and_idempotence():
    ledger, view = fixture()
    before = str(ledger["race_records"]["11-7"]["versions"])
    now = datetime(2026, 11, 7, 14, 0, tzinfo=JST)
    actual = integrate_official(ledger, view, pay_record(), now)
    r = actual["official_results"][DAY + "|びわこ|7"]
    assert r["hit"] is True
    assert r["virtual_winning_payout"] == 376000
    assert r["virtual_refund"] == 20000
    assert r["virtual_payout"] == 396000
    assert r["virtual_effective_stake"] == 30000
    assert r["virtual_profit"] == 346000
    assert "official_review" not in ledger["race_records"]["11-7"]
    assert str(ledger["race_records"]["11-7"]["versions"]) == before
    assert integrate_official(ledger, view, pay_record(), now)["official_results"][
        DAY + "|びわこ|7"]["virtual_refund"] == 20000


def test_refund_without_hit_and_full_void():
    ledger, view = fixture()
    now = datetime(2026, 11, 7, 14, 0, tzinfo=JST)
    pay = pay_record(finish="1-3-2")
    r = integrate_official(ledger, view, pay, now)["official_results"][DAY + "|びわこ|7"]
    assert r["hit"] is False and r["virtual_refund"] == 20000
    assert r["virtual_profit"] == -30000
    ledger, view = fixture()
    void = integrate_official(ledger, view, pay_record(void=True), now)
    r = void["official_results"][DAY + "|びわこ|7"]
    assert r["hit"] is False
    assert r["virtual_refund"] == 50000
    assert r["virtual_profit"] == 0


def test_no_refund_inferred_from_only_pay_page_marker():
    ledger, view = fixture()
    now = datetime(2026, 11, 7, 14, 0, tzinfo=JST)
    unverified = pay_record()
    unverified["results"]["11-7"].pop("refund_source_url")
    assert integrate_official(ledger, view, unverified, now)["official_results"] == {}
    assert ledger["race_records"]["11-7"]["official_review"] == "refund"


def test_backlog_review_cleared_after_detail_becomes_verified():
    old = {
        "date": DAY, "results": {}, "reviews": {"11-7": {"reason": "refund"}},
        "cancellations": {}, "source_url": PAY_URL,
        "evidence_type": "official_boatrace_pay_snapshot",
        "status": "verified_by_server_fetch",
    }
    new = pay_record()
    new["reviews"] = {}
    report = merge_verified(old, new, DAY)
    assert "11-7" in report["results"]
    assert "11-7" not in report["reviews"]
