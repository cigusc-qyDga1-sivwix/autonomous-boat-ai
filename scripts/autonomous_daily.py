"""Nationwide read-only BOAT LAB ingestion and PRE-CUTOFF prediction snapshots.

One GET downloads the daily JSON for all 24 venues. The source is unofficial and
may lag by several minutes. NEVER use results to construct predictions. Predictions
created after the published cutoff are forbidden, including on retries.
No betting, notifications, video downloads, or claims of calibrated probabilities.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from itertools import permutations
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
UTC = timezone.utc
SOURCE = "https://boatraceopenapi.github.io/api/v1"
APP_DATA = Path("app/data/live")
VENUES = {
    "1": "桐生", "2": "戸田", "3": "江戸川", "4": "平和島", "5": "多摩川",
    "6": "浜名湖", "7": "蒲郡", "8": "常滑", "9": "津", "10": "三国",
    "11": "びわこ", "12": "住之江", "13": "尼崎", "14": "鳴門", "15": "丸亀",
    "16": "児島", "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村",
}
STAKES = [12000, 10000, 8000, 6000, 5000, 4000, 3000, 2000]
COURSE = [1.75, 1.27, 1.05, 0.90, 0.79, 0.69]
SAFE_MARGIN_SECONDS = 120  # Avoid a Git commit landing after cutoff.


def stable_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def cutoff_of(race: dict) -> datetime | None:
    try:
        value = datetime.strptime(race["closed_at"], "%Y-%m-%d %H:%M:%S")
        return value.replace(tzinfo=JST)
    except (ValueError, KeyError, TypeError):
        return None


def number(value, default=None):
    try:
        n = float(value)
        if math.isfinite(n):
            return n
    except (TypeError, ValueError):
        pass
    return default


def valid_entrants(race: dict) -> bool:
    racers = race.get("racers")
    return isinstance(racers, dict) and all(
        isinstance(racers.get(str(i)), dict)
        and str(racers[str(i)].get("name", "")).strip()
        for i in range(1, 7)
    )


def preview_complete(race: dict) -> bool:
    preview = race.get("preview")
    if not isinstance(preview, dict):
        return False
    racers = preview.get("racers") or {}
    if number(preview.get("wind_speed")) is None or number(preview.get("wave_height")) is None:
        return False
    return all(
        isinstance(racers.get(str(i)), dict) and all(
            number(racers[str(i)].get(field)) is not None
            for field in ("course_number", "start_timing", "exhibition_time")
        ) for i in range(1, 7)
    )


def features(race: dict, phase: str) -> tuple[list[float], list[dict]]:
    runners = race["racers"]
    preview = race.get("preview") or {}
    prev_racers = preview.get("racers") or {}
    expo_times = [number((prev_racers.get(str(i)) or {}).get("exhibition_time"))
                  for i in range(1, 7)]
    reference = min(t for t in expo_times if t is not None) if all(
        t is not None for t in expo_times) else None
    weights, detail = [], []
    for i in range(1, 7):
        racer = runners[str(i)]
        pr = prev_racers.get(str(i)) or {}
        course = int(number(pr.get("course_number"), i)) if phase == "exhibition" else i
        course = max(1, min(6, course))
        win = number(racer.get("national_win_rate"), 4.5)
        motor = number(racer.get("motor_top_2_percent"), 30.0)
        avg_st = number(racer.get("average_start_timing"), .17)
        f_count = number(racer.get("flying_count"), 0)
        score = COURSE[course - 1] * (1 + .11 * (win - 4.5)
                                     + .004 * (motor - 30)
                                     - .60 * (avg_st - .17))
        score *= 0.96 ** min(3, max(0, f_count))
        if phase == "exhibition" and reference is not None:
            expo = number(pr.get("exhibition_time"))
            est = number(pr.get("start_timing"))
            # Mild, capped adjustments: exhibition ST is not a race-day guarantee.
            score *= max(.75, min(1.23, 1 + .7 * (reference - expo)))
            score *= max(.90, min(1.10, 1 + .18 * (.16 - est)))
        weights.append(max(.12, score))
        detail.append({
            "lane": i,
            "name": str(racer.get("name", "")).strip(),
            "course": course,
            "national_win_rate": number(racer.get("national_win_rate")),
            "average_start_timing": number(racer.get("average_start_timing")),
            "motor_top_2_percent": number(racer.get("motor_top_2_percent")),
            "exhibition_st": number(pr.get("start_timing")) if phase == "exhibition" else None,
            "exhibition_time": number(pr.get("exhibition_time")) if phase == "exhibition" else None,
            "tilt": number(pr.get("tilt_adjustment")) if phase == "exhibition" else None,
        })
    return weights, detail


def combinations(weights: list[float]) -> list[tuple[str, float]]:
    total = sum(weights)
    ranked = []
    for a, b, c in permutations(range(6), 3):
        prob = (weights[a] / total) * (weights[b] / (total - weights[a])) * (
            weights[c] / (total - weights[a] - weights[b]))
        ranked.append((f"{a+1}-{b+1}-{c+1}", prob))
    ranked.sort(key=lambda item: (-item[1], item[0]))
    # Preserve some plausible alternate winners; still an uncalibrated baseline.
    selected = ranked[:6]
    heads = {s[0][0] for s in selected}
    for runner, _ in sorted(enumerate(weights, start=1), key=lambda x: -x[1])[:3]:
        if str(runner) not in heads:
            extra = next((row for row in ranked if row[0][0] == str(runner)), None)
            if extra:
                selected.append(extra)
                heads.add(str(runner))
        if len(selected) >= 8:
            break
    for row in ranked:
        if len(selected) >= 8:
            break
        if row not in selected:
            selected.append(row)
    return selected[:8]


def prediction(race: dict, venue: str, race_number: int, phase: str,
               now: datetime, source_url: str) -> dict:
    if phase not in ("baseline", "exhibition"):
        raise ValueError("Unknown phase")
    cutoff = cutoff_of(race)
    if cutoff is None or now.astimezone(JST) >= cutoff - timedelta(seconds=SAFE_MARGIN_SECONDS):
        raise ValueError("Too late to safely commit prediction before cutoff")
    if not valid_entrants(race):
        raise ValueError("Missing six confirmed entrants")
    if phase == "exhibition" and not preview_complete(race):
        raise ValueError("Incomplete exhibition readings")
    weights, racers = features(race, phase)
    ranked = combinations(weights)
    bets = [{"combination": combo, "virtual_yen": STAKES[i]}
            for i, (combo, _) in enumerate(ranked)]
    leader = racers[int(ranked[0][0][0]) - 1]
    follower = racers[int(ranked[0][0][2]) - 1]
    weather = None
    if phase == "exhibition":
        p = race["preview"]
        weather = {
            "wind_speed": number(p.get("wind_speed")),
            "wind_direction_number": number(p.get("wind_direction_number")),
            "wave_height": number(p.get("wave_height")),
            "weather_number": number(p.get("weather_number")),
            "air_temperature": number(p.get("air_temperature")),
            "water_temperature": number(p.get("water_temperature")),
        }
    body = {
        "model_version": "heuristic-0.2-untrained",
        "phase": phase,
        "venue": venue,
        "race": race_number,
        "cutoff_jst": cutoff.strftime("%H:%M"),
        "cutoff_iso_jst": cutoff.isoformat(),
        "frozen_at_utc": now.astimezone(UTC).isoformat(),
        "source_url": source_url,
        "scenario": f"{leader['lane']}号艇{leader['name']}中心・"
                    f"{follower['lane']}号艇{follower['name']}の残存を検証"
                    + ("（展示数値を参照）" if phase == "exhibition" else "（展示前仮説）"),
        "bets": bets,
        "racers": racers,
        "weather_observed": weather,
        "evidence": "直前情報あり" if phase == "exhibition" else "出走表のみ・直前気象なし",
        "classification": "WATCH",  # No validated edge or live odds; never BUY automatically.
    }
    return {**body, "sha256": stable_hash(body)}


def payout_records(race: dict) -> list[dict]:
    result = race.get("result")
    if not isinstance(result, dict):
        return []
    payouts = (result.get("payouts") or {}).get("trifecta") or []
    cleaned = []
    for p in payouts:
        combo = str(p.get("combination", ""))
        amount = number(p.get("amount"))
        parts = combo.split("-")
        if len(parts) == 3 and len(set(parts)) == 3 and all(
            x in "123456" and len(x) == 1 for x in parts
        ) and amount is not None and amount >= 100:
            cleaned.append({"combination": combo, "amount": int(amount)})
    return cleaned


def build(existing: dict | None, payload: dict, now: datetime, source_url: str) -> tuple[dict, dict]:
    if now.tzinfo is None:
        raise ValueError("Timezone-aware now is mandatory")
    local_day = now.astimezone(JST).date().isoformat()
    ledger = existing if isinstance(existing, dict) and existing.get("event_date") == local_day else {
        "event_date": local_day, "race_records": {},
        "created_at_utc": now.astimezone(UTC).isoformat()
    }
    records = ledger["race_records"]
    venues_seen = set()
    new_baseline, new_exhibition = 0, 0
    race_source = (payload.get("programs") or {}).get("stadiums") or {}
    for venue_code, stadium in race_source.items():
        if venue_code not in VENUES or not isinstance(stadium, dict):
            continue
        races = stadium.get("races") or {}
        if not isinstance(races, dict):
            continue
        if races:
            venues_seen.add(venue_code)
        for n_str, race in races.items():
            if not n_str.isdigit() or not 1 <= int(n_str) <= 12 or not isinstance(race, dict):
                continue
            n = int(n_str)
            cutoff = cutoff_of(race)
            if not cutoff or cutoff.date() != now.astimezone(JST).date():
                continue
            key = f"{venue_code}-{n}"
            record = records.setdefault(key, {
                "venue_code": venue_code, "venue": VENUES[venue_code], "race": n,
                "cutoff_jst": cutoff.strftime("%H:%M"), "versions": [], "payouts": []
            })
            if record["venue_code"] != venue_code or record["race"] != n:
                raise ValueError("Recorded race identity mismatch")
            phases = {entry["phase"] for entry in record["versions"]}
            if now.astimezone(JST) < cutoff - timedelta(seconds=SAFE_MARGIN_SECONDS) and valid_entrants(race):
                if "baseline" not in phases:
                    record["versions"].append(prediction(race, VENUES[venue_code], n,
                                                         "baseline", now, source_url))
                    new_baseline += 1
                if "exhibition" not in phases and preview_complete(race):
                    record["versions"].append(prediction(race, VENUES[venue_code], n,
                                                         "exhibition", now, source_url))
                    new_exhibition += 1
            if now.astimezone(JST) >= cutoff:
                record["payouts"] = payout_records(race) or record.get("payouts", [])
    # Preserve previous records even if a subsequent source request is incomplete.
    ledger["last_updated_at_utc"] = now.astimezone(UTC).isoformat()
    ledger["source_url"] = source_url
    ledger["source_note"] = "非公式・数分遅延の可能性あり。予測は未訓練モデル。"
    ledger["venues_with_races"] = len(venues_seen)
    latest_races, official_results, unavailable = [], {}, []
    for record in records.values():
        versions = record["versions"]
        if not versions:
            unavailable.append({"venue": record["venue"], "race": record["race"],
                                "cutoff_jst": record["cutoff_jst"],
                                "reason": "締切前の予想を固定できなかった"})
            continue
        current = versions[-1]
        r = {k: current[k] for k in (
            "venue", "race", "cutoff_jst", "classification", "scenario", "bets",
            "model_version", "phase", "frozen_at_utc", "sha256",
            "racers", "weather_observed", "evidence", "source_url"
        )}
        r["version_count"] = len(versions)
        latest_races.append(r)
        if record.get("payouts"):
            p = record["payouts"][0]
            official_results[f"{local_day}|{record['venue']}|{record['race']}"] = {
                "finish": p["combination"], "payout_per_100": p["amount"],
                "source": "unofficial-api", "recorded_at": ledger["last_updated_at_utc"]
            }
    latest_races.sort(key=lambda r: (r["cutoff_jst"], r["venue"], r["race"]))
    out = {
        "event_date": local_day,
        "mode": "auto-live",
        "updated_at_utc": ledger["last_updated_at_utc"],
        "timezone": "Asia/Tokyo",
        "method": "国内24場対応・未訓練Plackett–Luceヒューリスティック／展示前・展示後の発走前固定",
        "freeze_reference": "GitHub app/data/live/{date}.json のcommit履歴＋SHA256",
        "forecast_races": latest_races,
        "official_results": official_results,
        "unforecast_races": sorted(unavailable, key=lambda r: (r["cutoff_jst"], r["venue"])),
        "listed_races": sum(len(s.get("races", {})) for s in race_source.values()
                            if isinstance(s, dict)),
        "venues_with_races": len(venues_seen),
        "disclaimer": "非公式・数分遅延あり。展示動画と直前オッズは未対応。BUY判定は実施しません。仮想5万円は検証用で、実投票ではありません。",
    }
    status = {"event_date": local_day, "source": source_url,
              "listed_races": out["listed_races"], "venue_count": len(venues_seen),
              "forecast_races": len(latest_races),
              "missed_or_unavailable": len(unavailable),
              "new_baseline": new_baseline, "new_exhibition": new_exhibition,
              "official_results": len(official_results)}
    return ledger, out, status


def retrieve(day: str) -> tuple[dict, str]:
    url = f"{SOURCE}/{day[:4]}/{day}.json"
    req = Request(url, headers={"User-Agent": "BOAT-LAB-research/0.2 (read-only)"})
    with urlopen(req, timeout=25) as response:
        raw = response.read(10_000_000)
    return json.loads(raw), url


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="JST YYYY-MM-DD; only for tests")
    parser.add_argument("--input-json", type=Path, help="Local fixture; no network")
    parser.add_argument("--now-iso", help="Clock override (test only)")
    parser.add_argument("--out-dir", type=Path, default=APP_DATA)
    args = parser.parse_args()
    now = datetime.fromisoformat(args.now_iso) if args.now_iso else datetime.now(UTC)
    day = now.astimezone(JST).date().isoformat()
    if args.date and args.date != day:
        raise SystemExit("Date must match current JST day to avoid post-race forecasts")
    compact = day.replace("-", "")
    if args.input_json:
        source, source_url = json.loads(args.input_json.read_text(encoding="utf-8")), str(args.input_json)
    else:
        source, source_url = retrieve(compact)
    path = args.out_dir / f"{day}.json"
    previous = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    ledger, webapp, summary = build(previous, source, now, source_url)
    # A successful GET with no scheduled races still writes a factual empty dashboard.
    write_json(path, ledger)
    write_json(args.out_dir / "latest.json", webapp)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
