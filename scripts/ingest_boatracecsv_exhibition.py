"""Read-only BoatraceCSV exhibition backfill. NEVER modifies pre-cutoff forecasts."""
import argparse, csv, hashlib, io, json, math
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
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

def preview_signature(row):
    value = {key: row.get(key) for key in
             ("race_code", "source_observed_jst", "boats", "weather")}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def original_exhibition_signature(row):
    """Fingerprint measured originals independently from ST, weather and results.

    The timestamp of the first actual capture of THESE values must survive
    unrelated CSV revisions. Never infer a historical capture time afterward.
    """
    boats = row.get("boats")
    if not isinstance(boats, list) or len(boats) != 6:
        return None
    values, lanes = [], set()
    for boat in boats:
        if not isinstance(boat, dict) or boat.get("lane") not in range(1, 7):
            return None
        lane = boat["lane"]
        if lane in lanes:
            return None
        lanes.add(lane)
        metrics = sorted(
            (metric.get("metric"), numeric(metric.get("value")))
            for metric in (boat.get("original_exhibition") or [])
            if isinstance(metric, dict)
            and metric.get("metric") in ("一周", "半周ラップ", "まわり足", "直線")
            and numeric(metric.get("value")) is not None
        )
        if not metrics:
            return None
        values.append({"lane": lane, "name": boat.get("name"), "metrics": metrics})
    if lanes != set(range(1, 7)):
        return None
    value = {"race_code": row.get("race_code"), "boats": sorted(values, key=lambda b: b["lane"])}
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def build(day, inputs, prior=None, collected_at=None):
    captured = collected_at or datetime.now(timezone.utc)
    if captured.tzinfo is None:
        raise ValueError("Collection time requires a timezone")
    captured_iso = captured.astimezone(timezone.utc).isoformat()
    # Missing optional feeds must behave like empty CSVs, not crash the importer.
    src={k:index(inputs.get(k) or []) for k in SOURCES}
    merged={r["race_code"]:r for r in (prior or {}).get("records",[])}
    rejected=Counter()
    for code,st in src["stt"].items():
        tk=src["tkz"].get(code)
        su=src["sui"].get(code) or {}
        if (not isinstance(code,str) or len(code)!=12 or not code.isdigit()
                or code[:8]!=day.strftime("%Y%m%d")
                or not 1 <= int(code[8:10]) <= 24 or not 1 <= int(code[10:12]) <= 12):
            rejected["invalid_race_identity"]+=1
            continue
        if not tk:
            rejected["missing_exhibition_times"]+=1
            continue
        try:
            datetime.strptime(st["締切時刻"],"%H:%M")
            observed=datetime.fromisoformat(st["取得日時"])
            if observed.tzinfo is None or observed.astimezone(ZoneInfo("Asia/Tokyo")).date()!=day:
                raise ValueError("Wrong source day")
        except (KeyError,TypeError,ValueError):
            rejected["invalid_preview_timestamp"]+=1
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
        if (len({b["course"] for b in boats})!=6
                or any(b["course"] not in range(1,7)
                       or b["exhibition_time"] is None or not 5 <= b["exhibition_time"] <= 10
                       or b["exhibition_st"] is None or not -.5 <= b["exhibition_st"] <= 1
                       for b in boats)):
            rejected["invalid_or_incomplete_six_boat_preview"]+=1
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
                "decision":rr.get("決まり手") or None,"recorded_jst":rr.get("取得日時"),
                "source":"BoatraceCSV/realtime_unofficial"
            } if rr and all(rr.get(f"{i}着_艇番") for i in (1,2,3)) else None),
            "payout":({
                "finish":pp.get("3連単_組番") or None,
                "yen_per_100":numeric(pp.get("3連単_払戻金")),
                "recorded_jst":pp.get("取得日時"),
                "source":"BoatraceCSV/payouts_unofficial"
            } if pp else None)
        }
        old=merged.get(code)
        # Earliest time THIS importer first persisted the race; never backdate.
        entry["first_seen_at_utc"] = (old or {}).get("first_seen_at_utc") or captured_iso
        if old and old.get("source_observed_jst","")>entry["source_observed_jst"]:
            continue
        # Bind the first actual capture to these exact preview measurements.
        # An old first_seen for the race cannot backdate a later changed value.
        fingerprint = preview_signature(entry)
        same_preview = bool(old and old.get("preview_sha256") == fingerprint)
        entry["preview_sha256"] = fingerprint
        entry["preview_captured_at_utc"] = (
            old.get("preview_captured_at_utc") if same_preview else None
        ) or captured_iso
        # Independent first-capture proof for original exhibition measurements.
        # A later weather/ST or regular-exhibition change must not erase proof
        # that the ORIGINAL values were actually acquired before the cutoff.
        original_hash = original_exhibition_signature(entry)
        entry["original_exhibition_sha256"] = original_hash
        entry["original_exhibition_captured_at_utc"] = (
            (old or {}).get("original_exhibition_captured_at_utc")
            if original_hash and (old or {}).get("original_exhibition_sha256") == original_hash
            else None
        ) or (captured_iso if original_hash else None)
        entry["original_exhibition_observed_jst"] = (
            (old or {}).get("original_exhibition_observed_jst")
            if original_hash and (old or {}).get("original_exhibition_sha256") == original_hash
            else None
        ) or (og.get("取得日時") if original_hash else None)
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
        "source_paths":{k:url(k,day) for k in SOURCES},"records":records,
        "rejected_rows":dict(rejected),
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--date",help="YYYY-MM-DD; default today in JST")
    ap.add_argument("--output",type=Path)
    ap.add_argument("--previews-only",action="store_true",
                    help="Fetch preview inputs before forecasting; defer results to research")
    args=ap.parse_args()
    day=date.fromisoformat(args.date) if args.date else datetime.now(ZoneInfo("Asia/Tokyo")).date()
    path=args.output or Path(f"app/data/exhibition/{day.isoformat()}.json")
    prior=json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    # Independent public CSVs: bound concurrency and keep each request timeout.
    names=[name for name in SOURCES if not args.previews_only or name not in ("result","payout")]
    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        sources={name:[] for name in SOURCES}
        sources.update(zip(names, pool.map(lambda name: fetch(name,day), names)))
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
        "rejected_rows":current.get("rejected_rows",{}),
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
