"""Read-only BoatraceCSV exhibition backfill. NEVER modifies pre-cutoff forecasts."""
import argparse, csv, io, json, math
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from zoneinfo import ZoneInfo

ROOT = "https://boatracecsv.github.io/data/"
SOURCES = {"stt":"previews/stt","tkz":"previews/tkz","sui":"previews/sui",
           "original":"previews/original_exhibition","result":"results/realtime",
           "payout":"results/payouts"}
VENUES = ["桐生","戸田","江戸川","平和島","多摩川","浜名湖","蒲郡","常滑","津","三国",
          "びわこ","住之江","尼崎","鳴門","丸亀","児島","宮島","徳山","下関","若松",
          "芦屋","福岡","唐津","大村"]

def url(name, day):
    return f"{ROOT}{SOURCES[name]}/{day:%Y/%m/%d}.csv"

def fetch(name, day):
    try:
        request = Request(url(name,day),headers={"User-Agent":"boat-lab-research-import/1.0"})
        with urlopen(request,timeout=12) as response:
            return list(csv.DictReader(io.StringIO(response.read().decode("utf-8-sig"))))
    except (HTTPError,URLError,TimeoutError,UnicodeError) as exc:
        print(f"[research] {name}: unavailable ({type(exc).__name__})")
        return []

def numeric(value):
    if value is None or value == "":
        return None
    try:
        v=float(value)
        return v if math.isfinite(v) else None
    except (ValueError,TypeError):
        return None

def index(rows):
    return {r["レースコード"]:r for r in rows if r.get("レースコード")}

def build(day, inputs, prior=None):
    # Missing optional feeds must behave like empty CSVs, not crash the importer.
    src={k:index(inputs.get(k) or []) for k in SOURCES}
    merged={r["race_code"]:r for r in (prior or {}).get("records",[])}
    for code,st in src["stt"].items():
        tk=src["tkz"].get(code)
        su=src["sui"].get(code) or {}
        if not tk or len(code)!=12 or code[:8]!=day.strftime("%Y%m%d"):
            continue
        og=src["original"].get(code,{})
        rr=src["result"].get(code)
        pp=src["payout"].get(code)
        boats=[]
        for lane in range(1,7):
            stval=numeric(st.get(f"艇{lane}_スタート展示"))
            original=[{"metric":og.get(f"計測項目{k}"),"value":numeric(og.get(f"艇{lane}_値{k}"))} for k in (1,2,3)]
            boats.append({
                "lane":lane,"name":og.get(f"艇{lane}_選手名") or None,
                "course":numeric(st.get(f"艇{lane}_コース")),
                "exhibition_st":stval,"exhibition_f":stval is not None and stval<0,
                "exhibition_time":numeric(tk.get(f"艇{lane}_展示タイム")),
                "tilt":numeric(tk.get(f"艇{lane}_チルト")),
                "weight_kg":numeric(tk.get(f"艇{lane}_体重(kg)")),
                "original_exhibition":[v for v in original if v["metric"] and v["value"] is not None]
            })
        if any(b["course"] is None or b["exhibition_time"] is None or b["exhibition_st"] is None for b in boats):
            continue
        entry={
            "race_code":code,"venue":VENUES[int(code[8:10])-1],
            "venue_code":code[8:10],"race":int(code[10:12]),
            "cutoff_jst":st["締切時刻"],"source_observed_jst":st["取得日時"],
            "source_status":"historical_research_only_not_frozen_forecast",
            "boats":boats,
            "weather":{
                "wind_mps":numeric(su.get("風速(m)")),
                "wind_direction_number":numeric(su.get("風向")),
                "wave_cm":numeric(su.get("波の高さ(cm)")),
                "weather_number":numeric(su.get("天候")),
                "air_c":numeric(su.get("気温(℃)")),
                "water_c":numeric(su.get("水温(℃)")),
                "observed_time_jst":su.get("気象観測時刻")
            },
            "result":({
                "finish":"-".join(rr.get(f"{i}着_艇番","") for i in (1,2,3)),
                "decision":rr.get("決まり手") or None,"recorded_jst":rr["取得日時"],
                "source":"BoatraceCSV/realtime_unofficial"
            } if rr and all(rr.get(f"{i}着_艇番") for i in (1,2,3)) else None),
            "payout":({
                "finish":pp.get("3連単_組番") or None,
                "yen_per_100":numeric(pp.get("3連単_払戻金")),
                "recorded_jst":pp["取得日時"],
                "source":"BoatraceCSV/payouts_unofficial"
            } if pp else None)
        }
        old=merged.get(code)
        # Earliest time THIS importer first persisted the race; never backdate.
        entry["first_seen_at_utc"] = (old or {}).get("first_seen_at_utc") or datetime.now(timezone.utc).isoformat()
        if old and old.get("source_observed_jst","")>entry["source_observed_jst"]:
            continue
        if old:
            for kind in ("result","payout"):
                if entry[kind] is None:
                    entry[kind]=old.get(kind)
        merged[code]=entry
    records=sorted(merged.values(),key=lambda r:(r["cutoff_jst"],r["race_code"]))
    return {
        "schema":"boatlabs.exhibition_research.v1","event_date":day.isoformat(),
        "created_at_utc":datetime.now(timezone.utc).isoformat(),
        "source_root":"https://boatracecsv.github.io/",
        "source_docs":"https://boatracecsv.github.io/docs/data/previews.html",
        "data_provenance":"Public BoatraceCSV previews and results joined by race code; import can occur after the race.",
        "use_policy":"Historical research only. NEVER change frozen predictions, official payout ledger or pretend retrospective predictions were pre-cutoff.",
        "coverage":{
            "race_count":len(records),
            "venue_count":len({r["venue_code"] for r in records}),
            "results_from_realtime":sum(bool(r["result"]) for r in records),
            "payout_rows":sum(bool(r["payout"]) for r in records),
            "boat_rows":len(records)*6
        },
        "source_paths":{k:url(k,day) for k in SOURCES},"records":records
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--date",help="YYYY-MM-DD; default today in JST")
    ap.add_argument("--output",type=Path)
    args=ap.parse_args()
    day=date.fromisoformat(args.date) if args.date else datetime.now(ZoneInfo("Asia/Tokyo")).date()
    path=args.output or Path(f"app/data/exhibition/{day.isoformat()}.json")
    prior=json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    # Independent public CSVs: bound concurrency and keep each request timeout.
    with ThreadPoolExecutor(max_workers=6) as pool:
        sources=dict(zip(SOURCES, pool.map(lambda name: fetch(name,day), SOURCES)))
    has_essential=all(sources[k] for k in ("stt","tkz"))
    # Weather (sui) is optional: a missing weather feed must not suppress
    # otherwise complete six-boat exhibition readings.
    new=build(day,sources,prior) if has_essential else None
    if new and (not prior or new["records"]!=prior.get("records")):
        path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(new,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        tmp.replace(path)
        print(f"[research] Saved {path}: {new['coverage']}")
    elif has_essential:
        print(f"[research] Unchanged: {len((prior or {}).get('records',[]))}R")
    else:
        print("[research] Missing preview source, preserving previous file.")
    # Always write a dated fetch heartbeat, even if no new rows are published.
    # Do not advertise historical source timestamps as proof of cutoff-time capture.
    current=new if new is not None else prior or {}
    records=current.get("records",[])
    status={
        "event_date":day.isoformat(),
        "collected_at_utc":datetime.now(timezone.utc).isoformat(),
        "complete_sources":has_essential,
        "weather_source_available":bool(sources["sui"]),
        "fetch_counts":{k:len(rows) for k,rows in sources.items()},
        "research_races":len(records),
        "research_venues":len({r.get("venue_code") for r in records}),
        "complete_six_boat_research_races":sum(len(r.get("boats") or []) == 6 for r in records),
        "research_only_not_formal_count":len(records),
        "latest_source_observed_jst":max((r.get("source_observed_jst") or "" for r in records),default=""),
        "forecast_eligibility":"not_certified_by_archived_sources",
        "warning":"Historical source timestamps do not prove ingestion before cutoff. Review immutable forecast ledger separately.",
    }
    status_path=path.parent/"status-latest.json"
    status_path.parent.mkdir(parents=True,exist_ok=True)
    status_path.write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("[research] Source health: "+json.dumps(status,ensure_ascii=False))

if __name__ == "__main__":
    main()
