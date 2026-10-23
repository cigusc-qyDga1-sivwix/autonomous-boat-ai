"""Nationwide intake is research-only; no future/race-result leakage."""
import hashlib
import json
from datetime import date
from scripts import ingest_global_intelligence as collect

DAY=date(2026,10,23)
KEY="202610232301"

def fixture():
    base={"レースコード":KEY,"レース日":DAY.isoformat(),"レース場コード":"23","レース回":"1R"}
    card=dict(base);frame=dict(base);nat=dict(base);local=dict(base)
    for lane in range(1,7):
        root=f"艇{lane}_"
        card.update({root+"登録番号":str(4000+lane),
            root+"選手名":f"選手{lane}",root+"級別":"A1",
            root+"全国勝率":str(6.0+lane/10),
            root+"全国平均ST":"0.14",root+"F本数":str(int(lane==6)),
            root+"当地勝率":"6.55",root+"モーター番号":str(20+lane),
            root+"モーター2連対率":"42.0"})
        card[root+"節D1走1_R番号"]="1"
        card[root+"節D1走1_進入"]=str(lane)
        card[root+"節D1走1_枠"]=str(lane)
        card[root+"節D1走1_ST"]="0.13"
        card[root+"節D1走1_着順"]="2"
        frame[root+"枠番別勝率"]="7.25"
        frame[root+"枠番別平均ST"]="0.12"
        frame[root+"枠番別平均スタート順"]="2.3"
        frame[root+"過去1走_着順"]="1"
        frame[root+"過去1走_進入"]=str(lane)
        frame[root+"過去1走_グレード"]="G1"
        nat[root+"前1節_開始日"]="2026-10-01"
        nat[root+"前1節_終了日"]="2026-10-05"
        nat[root+"前1節_場コード"]="01"
        nat[root+"前1節_着順列"]="２１１"
        local[root+"前1節_開始日"]="2026-09-01"
        local[root+"前1節_終了日"]="2026-09-05"
        local[root+"前1節_着順列"]="１３２"
    motor={"記録日":"2026-10-22","場コード":"23","モーター番号":"21",
        "2連対率":"48.5","3連対率":"60.1","出走数":"58",
        "平均ラップ秒":"14.88","整備種別1回数":"3","直近メンテ日":"2026-10-21"}
    past={"場コード":"23","モーター番号":"21","使用者名":"前節選手",
        "使用開始日":"2026-10-10","使用終了日":"2026-10-16","着順列":"２１２",
        "グレード":"一般"}
    future={**past,"使用終了日":"2026-10-23","着順列":"１１１"}
    return {
        "race_cards":[card],"waku10":[frame],
        "recent_national":[nat],"recent_local":[local],"motor_stats":[motor],
        "motor_history":[past,future],
        "title":[dict(base,レース名="予選",グレード="一般",日次="３日目")]
    }

def states(inputs):
    return {k:{"state":"available","rows":len(v),"url":collect.source_url(k,DAY),
              "fetched_at_utc":"2026-10-23T06:00:00Z",
              "sha256":hashlib.sha256(k.encode()).hexdigest(),"error":None}
             for k,v in inputs.items()}

def test_24_venue_common_racekey_and_research_boundary():
    rows=fixture()
    doc=collect.make_research(DAY,rows,states(rows),"2026-10-23T06:00:00Z")
    assert doc["coverage"]["races"]==1
    assert doc["coverage"]["racer_rows"]==6
    assert doc["coverage"]["venue_count"]==1
    assert doc["coverage"]["motor_stat_rows"]==1
    assert doc["forecast_eligibility"].startswith("research_only")
    assert "results" not in doc and "payouts" not in doc
    race=doc["races"][0]
    assert race["race_code"]==KEY
    assert race["race_title"]=="予選"
    assert race["grade"]=="一般"
    r=race["racers"][0]
    assert r["racer_id"]==4001
    assert r["frame_history"]["frame_st"]==.12
    assert r["past10"][0]["finish"]=="1"
    assert r["session"][0]["start"]==.13
    assert r["recent_national"][0]["finishes"]=="２１１"
    assert r["recent_local"][0]["finishes"]=="１３２"
    assert r["motor_stats"]["wins_pct"]==48.5
    assert r["motor_stats"]["lap_seconds"]==14.88
    assert len(r["motor_previous_users"])==1
    assert r["motor_previous_users"][0]["racer"]=="前節選手"
    assert all(x["end"]<DAY.isoformat() for x in r["motor_previous_users"])
    assert race["racers"][5]["f_count"]==1
    assert race["racers"][5]["motor_stats"] is None

def test_missing_data_stays_missing_and_incomplete_venues_are_not_fabricated():
    d=collect.make_research(DAY,{"waku10":[{"レースコード":KEY,
         "艇1_枠番別勝率":"6.44"}]},{},"2026-10-23T06:00:00Z")
    assert d["coverage"]["races"]==1
    assert d["coverage"]["race_cards"]==0
    assert d["races"][0]["racers"][0]["frame_history"]["frame_win"]==6.44
    assert d["races"][0]["racers"][0].get("racer_id") is None
    assert d["coverage"]["has_complete_racers"]==0

def test_outcome_fields_cannot_be_imported_from_source_even_if_present():
    d=fixture()
    d["race_cards"][0]["公式結果"]="1-2-3"
    d["race_cards"][0]["1着"]="1"
    d["race_cards"][0]["払戻金"]="1500"
    doc=collect.make_research(DAY,d,states(d),"2026-10-24T10:00:00Z")
    encoded=json.dumps(doc,ensure_ascii=False)
    assert "公式結果" not in encoded
    assert "払戻金" not in encoded
    assert "2026-10-24" in doc["created_at_utc"]
    assert doc["forecast_eligibility"].startswith("research_only")

def test_schema_rejects_bad_race_keys_and_nan():
    assert collect.numeric("NaN") is None
    assert collect.numeric("Inf") is None
    assert collect.integer("2.5") is None
    rows=fixture()
    rows["race_cards"][0]["レースコード"]="202610222301"
    d=collect.make_research(DAY,rows,states(rows),"2026-10-23T02:00:00Z")
    assert d["coverage"]["race_cards"]==0
    assert len(d["races"])==1

def test_cli_recovers_from_unavailable_sources_and_writes_truthful_health(tmp_path,monkeypatch):
    monkeypatch.setattr(collect,"fetch_csv",lambda name,d:([],{"state":"missing_or_unavailable",
      "rows":0,"url":collect.source_url(name,d),"sha256":None,"error":"404",
      "fetched_at_utc":"2026-10-23T10:00:00Z"}))
    import sys
    monkeypatch.setattr(sys,"argv",["ingest","--date",DAY.isoformat(),
                                  "--out-dir",str(tmp_path),"--history-days","1"])
    collect.main()
    status=json.loads((tmp_path/"status-latest.json").read_text(encoding="utf-8"))
    doc=json.loads((tmp_path/(DAY.isoformat()+".json")).read_text(encoding="utf-8"))
    assert status["research_races"]==0
    assert status["source_status"]["race_cards"]["state"]=="missing_or_unavailable"
    assert doc["races"]==[]
    assert doc["forecast_eligibility"].startswith("research_only")

def test_source_date_and_csv_identity():
    assert collect.source_url("waku10",DAY).endswith("/2026/10/23.csv")
    assert collect.source_url("motor_history",date(2026,10,22)).endswith("/2026/10/22.csv")
    assert collect.MAX_RECORDS==288

def test_previous_meeting_end_dates_not_last_three_calendar_days():
    rows=[
      {"場コード":"23","節開始日":"2026-10-07","節終了日":"2026-10-12"},
      {"場コード":"23","節開始日":"2026-10-16","節終了日":"2026-10-27"},
      {"場コード":"18","節開始日":"2026-10-13","節終了日":"2026-10-19"},
      {"場コード":"11","節開始日":"2026-10-15","節終了日":"2026-10-20"},
      {"場コード":"02","節開始日":"2026-10-13","節終了日":"2026-10-22"},
    ]
    found=collect.previous_meeting_end_dates(DAY,rows,{23,18,11})
    assert found==[date(2026,10,20),date(2026,10,19),date(2026,10,12)]
    assert collect.source_url("monthly_schedule",DAY).endswith("/2026/10.csv")
    assert collect.previous_meeting_end_dates(DAY,rows,{2})==[date(2026,10,22)]
