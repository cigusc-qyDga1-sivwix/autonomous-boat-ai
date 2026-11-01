"""Research importer tests: historical data MUST NOT become frozen forecast data."""
from datetime import date, datetime, timezone, timedelta
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


def test_changed_preview_gets_its_actual_capture_not_the_races_old_first_seen():
    first=datetime(2026,10,23,0,20,tzinfo=timezone.utc)
    old=build(date(2026,10,23),fixtures(),collected_at=first)
    same=build(date(2026,10,23),fixtures(),old,collected_at=first+timedelta(minutes=10))
    assert same["records"][0]["preview_captured_at_utc"]==first.isoformat()
    changed=fixtures();changed["tkz"][0]["艇1_展示タイム"]="6.65"
    later=first+timedelta(hours=1)
    new=build(date(2026,10,23),changed,old,collected_at=later)
    a,b=old["records"][0],new["records"][0]
    assert a["first_seen_at_utc"]==b["first_seen_at_utc"]
    assert b["preview_captured_at_utc"]==later.isoformat()
    assert a["preview_sha256"]!=b["preview_sha256"]


def test_previews_only_does_not_request_result_or_payout_feeds(tmp_path, monkeypatch):
    import sys
    import scripts.ingest_boatracecsv_exhibition as exporter
    requested=[];data=fixtures()
    def fetch(name,day):
        requested.append(name)
        assert name not in ('result','payout')
        return data[name]
    monkeypatch.setattr(exporter,'fetch',fetch)
    path=tmp_path/'2026-10-23.json'
    monkeypatch.setattr(sys,'argv',['ingest','--date','2026-10-23','--output',str(path),'--previews-only'])
    exporter.main()
    assert set(requested)=={'stt','tkz','sui','original'}


def test_bad_feed_rows_are_counted_without_stopping_valid_venues():
    data=fixtures()
    for code in ('202610230001','202610232501','202610231413'):
        st={**data['stt'][0],'レースコード':code}
        tk={**data['tkz'][0],'レースコード':code}
        data['stt'].append(st);data['tkz'].append(tk)
    result=build(date(2026,10,23),data)
    assert result['coverage']['race_count']==1
    assert result['rejected_rows']['invalid_race_identity']==3
    data=fixtures();data['stt'][0]['艇6_コース']='1'
    result=build(date(2026,10,23),data)
    assert result['coverage']['race_count']==0
    assert result['rejected_rows']['invalid_or_incomplete_six_boat_preview']==1
