"""Wind research captures only fresh pre-cutoff observations; no forecast writes."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from scripts.collect_site_weather_research import parse, merge_document, run, SCHEMA

DAY="2026-11-16"
NOW=datetime.fromisoformat("2026-11-16T09:54:00+09:00")
URL="https://boatracecsv.github.io/data/previews/sui/2026/11/16.csv"
COLS=["レースコード","レース日","レース場","レース回","締切時刻","取得日時","気象観測時刻","風速(m)","風向","波の高さ(cm)"]
def csv_fixture(*rows):
    head=",".join(COLS)
    return head+"\n"+"\n".join(",".join(str(row.get(k,"")) for k in COLS) for row in rows)+"\n"
def row(**kw):
    d=dict(zip(COLS,["202611161801",DAY,"18","01R","10:00","2026-11-16T09:52:00+09:00","0951","5","3","4"]))
    return {**d,**kw}

def test_source_wind_direction_wave_and_provenance():
    x, reject=parse(csv_fixture(row()),NOW.date(),NOW,source_url=URL)
    assert not reject
    assert list(x)==[f"{DAY}|徳山|1"]
    got=x[f"{DAY}|徳山|1"]
    assert got["wind_speed_mps"]==5
    assert got["wind_direction_raw"]=="3"
    assert got["wave_height_cm"]==4
    assert got["source_acquired_before_cutoff"]
    assert got["relative_wind_verified"] is False
    assert got["tide_verified"] is False
    assert got["formal_input"] is False
    assert len(got["evidence_sha256"])==64

def test_invalid_timestamp_future_stale_and_wrong_identity_rejected():
    rows=[
      row(**{"レースコード":"202611161802","レース回":"02R","取得日時":"2026-11-16T09:55:00+09:00"}),
      row(**{"レースコード":"202611161803","レース回":"03R","気象観測時刻":"0840"}),
      row(**{"レースコード":"202611161804","レース回":"04R","レース場":"16"}),
      row(**{"レースコード":"202611160301","レース場":"03"}),
      row(**{"レースコード":"202611161805","レース回":"05R","締切時刻":"09:54"}),
    ]
    x,rejected=parse(csv_fixture(*rows),NOW.date(),NOW,source_url=URL)
    assert not x
    assert sum(rejected.values())==len(rows)

def test_null_not_zero_and_unknown_direction_remains_unknown():
    d=row(**{"風速(m)":"","風向":"","波の高さ(cm)":"0"})
    x,_=parse(csv_fixture(d),NOW.date(),NOW,source_url=URL)
    e=next(iter(x.values()))
    assert e["wind_speed_mps"] is None
    assert e["wave_height_cm"]==0
    assert e["wind_direction_raw"] is None
    assert e["wind_direction_status"]=="unavailable"

def test_conflicts_never_overwrite_previous_frozen_evidence():
    from datetime import date
    first,_=parse(csv_fixture(row()),date.fromisoformat(DAY),NOW,source_url=URL)
    older=merge_document(first,{},date.fromisoformat(DAY),NOW,source_url=URL)
    changed,_=parse(csv_fixture(row(**{"風速(m)":"9"})),date.fromisoformat(DAY),NOW,source_url=URL)
    doc=merge_document(changed,older,date.fromisoformat(DAY),NOW,source_url=URL)
    key=f"{DAY}|徳山|1"
    assert doc["records"][key]==older["records"][key]
    assert key in doc["conflicts_this_check"]
    assert doc["formal_model_changed"] is False

def test_live_capture_writer_only_writes_weather_research(tmp_path):
    def fake(day):
        assert day.isoformat()==DAY
        return csv_fixture(row()),URL,None
    result=run(out_dir=tmp_path/"weather-research",now=NOW,downloader=fake)
    assert result["saved_races"]==1
    assert (tmp_path/"weather-research"/"latest.json").exists()
    assert (tmp_path/"weather-research"/f"{DAY}.json").exists()
    assert not (tmp_path/"live").exists()
