"""Research importer tests: historical data MUST NOT become frozen forecast data."""
from datetime import date
from scripts.ingest_boatracecsv_exhibition import build, numeric

def fixtures():
    code = "202610231401"
    st = {"レースコード": code, "締切時刻": "08:35", "取得日時": "2026-10-23T08:25:30+09:00"}
    tk = {"レースコード": code}
    su = {"レースコード": code, "風速(m)": "4", "波の高さ(cm)": "4"}
    for i in range(1, 7):
        st[f"艇{i}_コース"] = str(i)
        st[f"艇{i}_スタート展示"] = "-0.12" if i == 6 else "0.15"
        tk[f"艇{i}_展示タイム"] = "6.73" if i == 3 else "6.79"
        tk[f"艇{i}_チルト"] = "-0.5"
    return {"stt": [st], "tkz": [tk], "sui": [su], "original": [], "result": [], "payout": []}

def test_research_snapshot_is_not_frozen_forecast():
    result = build(date(2026, 10, 23), fixtures())
    assert result["coverage"]["race_count"] == 1
    assert result["coverage"]["boat_rows"] == 6
    record = result["records"][0]
    assert record["boats"][5]["exhibition_f"] is True
    assert record["boats"][2]["exhibition_time"] == 6.73
    assert record["result"] is None
    assert "frozen_at_utc" not in str(record)
    assert "historical_research_only" in record["source_status"]

def test_delayed_result_merges_without_erasing_preview():
    original = build(date(2026, 10, 23), fixtures())
    extra = fixtures()
    extra["result"] = [{"レースコード": "202610231401", "1着_艇番": "3",
        "2着_艇番": "1", "3着_艇番": "2", "決まり手": "まくり差し",
        "取得日時": "2026-10-23T08:55:00+09:00"}]
    updated = build(date(2026, 10, 23), extra, original)
    assert updated["records"][0]["result"]["finish"] == "3-1-2"
    assert updated["records"][0]["boats"] == original["records"][0]["boats"]
    final = build(date(2026, 10, 23), fixtures(), updated)
    assert final["records"][0]["result"]["finish"] == "3-1-2"

def test_different_date_not_imported_and_nonnumeric_rejected():
    assert build(date(2026, 10, 22), fixtures())["coverage"]["race_count"] == 0
    assert numeric("NaN") is None

def test_collection_health_is_recorded_when_source_unavailable(tmp_path, monkeypatch):
    import json
    import sys
    import scripts.ingest_boatracecsv_exhibition as exporter
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(exporter, "fetch", lambda _name, _date: [])
    path = tmp_path / "app/data/exhibition/2026-10-23.json"
    monkeypatch.setattr(sys, "argv", ["ingest", "--date", "2026-10-23", "--output", str(path)])
    exporter.main()
    status = json.loads((path.parent / "status-latest.json").read_text(encoding="utf-8"))
    assert status["event_date"] == "2026-10-23"
    assert status["complete_sources"] is False
    assert status["research_races"] == 0
    assert all(value == 0 for value in status["fetch_counts"].values())
    assert not path.exists()  # no fabricated exhibition data

def test_collection_health_and_archive_are_both_written(tmp_path, monkeypatch):
    import json
    import sys
    import scripts.ingest_boatracecsv_exhibition as exporter
    monkeypatch.chdir(tmp_path)
    mock = fixtures()
    monkeypatch.setattr(exporter, "fetch", lambda name, day: mock[name])
    path = tmp_path / "app/data/exhibition/2026-10-23.json"
    monkeypatch.setattr(sys, "argv", ["ingest", "--date", "2026-10-23", "--output", str(path)])
    exporter.main()
    doc = json.loads(path.read_text(encoding="utf-8"))
    status = json.loads((path.parent / "status-latest.json").read_text(encoding="utf-8"))
    assert status["complete_sources"] is True
    assert doc["coverage"]["race_count"] == status["research_races"] == 1
    assert status["fetch_counts"]["stt"] == 1
    assert status["forecast_eligibility"] == "not_certified_by_archived_sources"
