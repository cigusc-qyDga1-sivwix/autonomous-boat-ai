#!/usr/bin/env python3
"""Research-only same-day replay of exhibitions collected AFTER the official freeze.

NEVER writes app/data/live, calls the production build/freeze path, or backdates
a formal prediction. Frozen baseline snapshots supply racer inputs. The
historical exhibition file contains results but ONLY explicitly allowlisted
boat/weather observations reach the model. Official pay is read for scoring
only AFTER all counterfactual bets have been generated.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__:
    from .autonomous_daily import (
        MAIN_WAKE_MODEL, VENUES, prediction, valid_entrants, preview_complete,
    )
    from .exhibition_bridge import inject
else:
    from autonomous_daily import (
        MAIN_WAKE_MODEL, VENUES, prediction, valid_entrants, preview_complete,
    )
    from exhibition_bridge import inject

JST = ZoneInfo("Asia/Tokyo")
UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]
BUDGET = 50_000
MODE = "retrospective_exhibition_replay_NOT_formal"
SOURCE_NOTE = (
    "Archived exhibition observations and original frozen baseline racer features "
    "are applied after races. Historical source timestamps DO NOT prove live "
    "pre-cutoff availability. This is not a forward test, not calibrated ROI, "
    "and never part of formal BUY/WATCH/SKIP performance."
)


def racer_input(frozen: dict, day: str, cutoff_jst: str) -> dict | None:
    """Rebuild permitted pre-race fields from a genuine immutable baseline."""
    try:
        rows = frozen["racers"]
        if frozen.get("phase") != "baseline" or len(rows) != 6:
            return None
        if frozen.get("model_version") != MAIN_WAKE_MODEL:
            return None
        racers = {}
        for row in rows:
            lane = int(row["lane"])
            if lane not in range(1, 7) or str(lane) in racers:
                return None
            racers[str(lane)] = {
                "name": row["name"],
                "national_win_rate": row.get("national_win_rate"),
                "motor_top_2_percent": row.get("motor_top_2_percent"),
                "average_start_timing": row.get("average_start_timing_source_value"),
                # Baseline does not store the original F count; neutral fallback.
                "flying_count": 0,
            }
        race = {
            "closed_at": day + " " + cutoff_jst + ":00",
            "racers": racers,
        }
        return race if valid_entrants(race) else None
    except (ValueError, TypeError, KeyError):
        return None


def sanitized_measurements(row: dict) -> dict:
    """Allowlist only exhibition inputs. Exclude result, decision, and payout."""
    allowed = {
        "race_code", "venue_code", "race", "source_observed_jst",
        "source_status",
    }
    item = {key: row.get(key) for key in allowed}
    item["boats"] = [
        {
            "lane": boat.get("lane"),
            "course": boat.get("course"),
            "exhibition_st": boat.get("exhibition_st"),
            "exhibition_time": boat.get("exhibition_time"),
            "tilt": boat.get("tilt"),
            "original_exhibition": [
                {"metric": m.get("metric"), "value": m.get("value")}
                for m in (boat.get("original_exhibition") or [])
                if isinstance(m, dict)
            ],
        }
        for boat in (row.get("boats") or [])
        if isinstance(boat, dict)
    ]
    item["weather"] = {
        k: v for k, v in (row.get("weather") or {}).items()
        if k in {
            "wind_mps", "wind_direction_number", "wave_cm",
            "weather_number", "air_c", "water_c",
        }
    }
    return item


def score(bets: list, official: dict) -> dict:
    result = official.get("finish")
    payout = official.get("payout_per_100")
    if (not isinstance(result, str) or len(result.split("-")) != 3
            or not isinstance(payout, int) or payout <= 0):
        raise ValueError("Invalid independently verified payout record")
    hit = next((b for b in bets if b["combination"] == result), None)
    stake = sum(b["virtual_yen"] for b in bets)
    if stake != BUDGET:
        raise ValueError("Invalid virtual budget")
    paid = hit["virtual_yen"] * payout // 100 if hit else 0
    top = bets[0]["combination"]
    return {
        "hit": bool(hit),
        "head_captured": any(b["combination"][0] == result[0] for b in bets),
        "first_second_captured": any(
            b["combination"].split("-")[:2] == result.split("-")[:2]
            for b in bets
        ),
        "top_combination": top,
        "virtual_stake_yen": stake,
        "virtual_payout_yen": paid,
        "virtual_profit_yen": paid - stake,
    }


def generate_candidates(day: str, ledger: dict, research: dict, now: datetime):
    """Forecast first. NO result/finish/payout input exists in this function."""
    if ledger.get("event_date") != day or research.get("event_date") != day:
        raise ValueError("All inputs must use the exact same JST date")
    rows = {
        x["race_code"]: x for x in research.get("records", [])
        if isinstance(x, dict) and isinstance(x.get("race_code"), str)
    }
    candidates = []
    skips = Counter()
    existing_formal = 0
    for key, record in (ledger.get("race_records") or {}).items():
        try:
            venue_code = str(int(record["venue_code"]))
            race_no = int(record["race"])
            if (not 1 <= race_no <= 12 or venue_code not in VENUES
                    or key != venue_code + "-" + str(race_no)):
                skips["invalid_race_identity"] += 1
                continue
            cutoff = datetime.fromisoformat(day + "T" + record["cutoff_jst"] + ":00+09:00")
            if now.astimezone(JST) < cutoff + timedelta(minutes=5):
                skips["not_yet_finished"] += 1
                continue
            versions = record["versions"]
            if any(v.get("phase") == "exhibition" for v in versions):
                existing_formal += 1
                continue
            base = next((v for v in versions if v.get("phase") == "baseline"), None)
            if not base or not base.get("sha256"):
                skips["no_immutable_baseline"] += 1
                continue
            source = racer_input(base, day, record["cutoff_jst"])
            if source is None:
                skips["baseline_inputs_unavailable"] += 1
                continue
            race_code = day.replace("-", "") + f"{int(venue_code):02d}{race_no:02d}"
            observed = rows.get(race_code)
            if not observed:
                skips["no_archived_exhibition"] += 1
                continue
            # The simulation clock is ONLY to reuse the validated production
            # formula. It was not an actual observation or a real forecast time.
            simulated = cutoff - timedelta(seconds=181)
            safe, origin = inject(
                source, sanitized_measurements(observed), simulated,
                venue_code, race_no
            )
            if not origin or not preview_complete(safe):
                skips["archived_exhibition_invalid_or_too_late_for_3min_margin"] += 1
                continue
            # Strip the simulated "captured before cutoff" origin. A replay
            # may NEVER emit a formal frozen timestamp or such a claim.
            safe["_exhibition_origin"] = None
            new = prediction(
                safe, record["venue"], race_no, "exhibition", simulated,
                "https://boatracecsv.github.io/docs/data/previews.html"
            )
            candidates.append({
                "race_key": key,
                "venue": record["venue"],
                "venue_code": venue_code,
                "race": race_no,
                "cutoff_jst": record["cutoff_jst"],
                "source_observed_jst": observed["source_observed_jst"],
                "research_first_seen_at_utc": observed.get("first_seen_at_utc"),
                "original_baseline_sha256": base["sha256"],
                "model_version": new["model_version"],
                "model_inputs_from": "original_immutable_baseline_racers_plus_later_archived_exhibition",
                "source": "BoatraceCSV historical research",
                "simulated_clock_not_actual_capture": simulated.isoformat(),
                "bets_before": [
                    {"combination": b["combination"], "virtual_yen": b["virtual_yen"]}
                    for b in base["bets"]
                ],
                "bets_replayed": [
                    {"combination": b["combination"], "virtual_yen": b["virtual_yen"]}
                    for b in new["bets"]
                ],
                "added": sorted(
                    {b["combination"] for b in new["bets"]}
                    - {b["combination"] for b in base["bets"]}
                ),
                "removed": sorted(
                    {b["combination"] for b in base["bets"]}
                    - {b["combination"] for b in new["bets"]}
                ),
                "changed": (
                    {(b["combination"], b["virtual_yen"]) for b in base["bets"]}
                    != {(b["combination"], b["virtual_yen"]) for b in new["bets"]}
                ),
            })
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            skips["invalid_source_or_snapshot"] += 1
            # Don't let an invalid race corrupt the other independent replays.
    return candidates, dict(skips), existing_formal


def score_candidates(candidates: list, official: dict, day: str) -> dict:
    """Only now, after ALL bets exist, reveal the independently verified results."""
    if official.get("date") != day:
        raise ValueError("Official pay date mismatch")
    blocked = (set(official.get("reviews") or {})
               | set(official.get("conflicts") or {})
               | set(official.get("cancellations") or {}))
    results = official.get("results") or {}
    verified = []
    unverified = 0
    for row in candidates:
        key = row["race_key"]
        if key in blocked or key not in results:
            unverified += 1
            continue
        result = results[key]
        try:
            old = score(row["bets_before"], result)
            new = score(row["bets_replayed"], result)
        except (ValueError, KeyError):
            unverified += 1
            continue
        verified.append({
            **row,
            "official_finish": result["finish"],
            "official_payout_per_100_yen": result["payout_per_100"],
            "comparison": {"frozen_baseline": old, "retrospective_replay": new},
        })
    return {"verified": verified, "not_officially_verified": unverified}


def metrics(rows: list, name: str) -> dict:
    values = [x["comparison"][name] for x in rows]
    total = len(values)
    stakes = sum(x["virtual_stake_yen"] for x in values)
    paid = sum(x["virtual_payout_yen"] for x in values)
    return {
        "races": total,
        "hits": sum(x["hit"] for x in values),
        "hit_rate": round(sum(x["hit"] for x in values) / total, 5) if total else None,
        "head_captured": sum(x["head_captured"] for x in values),
        "first_second_captured": sum(x["first_second_captured"] for x in values),
        "virtual_stake_yen": stakes,
        "virtual_payout_yen": paid,
        "virtual_profit_yen": paid - stakes,
        "return_rate": round(paid / stakes, 5) if stakes else None,
    }


def report(day: str, ledger: dict, research: dict, official: dict, now: datetime):
    candidates, skips, existing = generate_candidates(day, ledger, research, now)
    judged = score_candidates(candidates, official, day)
    verified = judged["verified"]
    grouped = defaultdict(list)
    for r in verified:
        grouped[r["venue"]].append(r)
    return {
        "schema": "boatlabs.retrospective_exhibition_replay.v1",
        "event_date": day,
        "mode": MODE,
        "generated_at_utc": now.astimezone(UTC).isoformat(),
        "excluded_from_formal_forecast_and_formal_returns": True,
        "results_are_scored_only_after_all_replay_bets_generated": True,
        "immutable_original_forecasts_unchanged": True,
        "warnings": [
            SOURCE_NOTE,
            "The synthetic replay clock is not evidence of when a source became available.",
            "Prior snapshots omit original flying_count; neutral zero is used in reconstructing model input.",
            "No out-of-sample claim. Post-event archival selection and missing data cause selection bias.",
        ],
        "coverage": {
            "existing_formal_exhibition_races_excluded": existing,
            "retrospective_bets_generated": len(candidates),
            "officially_verifiable_pairs": len(verified),
            "generated_but_official_result_unavailable": judged["not_officially_verified"],
            "skipped": skips,
        },
        "comparison": {
            "frozen_baseline_on_same_replayed_subset": metrics(verified, "frozen_baseline"),
            "retrospective_exhibition_on_same_subset": metrics(verified, "retrospective_replay"),
            "changed_bets_races": sum(x["changed"] for x in verified),
        },
        "by_venue": {
            venue: {
                "frozen_baseline": metrics(rows, "frozen_baseline"),
                "retrospective_replay": metrics(rows, "retrospective_replay"),
            } for venue, rows in sorted(grouped.items())
        },
        "races": verified,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", help="JST date (YYYY-MM-DD); defaults to today")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    now = datetime.now(UTC)
    day = args.date or now.astimezone(JST).date().isoformat()
    if day != now.astimezone(JST).date().isoformat():
        raise SystemExit("Only TODAY can be replayed by this task")
    ledger_path = ROOT / "app" / "data" / "live" / f"{day}.json"
    research_path = ROOT / "app" / "data" / "exhibition" / f"{day}.json"
    official_path = ROOT / "app" / "data" / "live" / "official-pay" / f"{day}.json"
    for path in (ledger_path, research_path, official_path):
        if not path.exists():
            raise SystemExit(f"Required existing input missing: {path}")
    # No network and no writes to source directories.
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    research = json.loads(research_path.read_text(encoding="utf-8"))
    official = json.loads(official_path.read_text(encoding="utf-8"))
    data = report(day, ledger, research, official, now)
    output = args.output or ROOT / "app" / "data" / "retrospective" / f"{day}.json"
    if output.resolve() in (ledger_path.resolve(), research_path.resolve(), official_path.resolve()):
        raise SystemExit("Refusing to overwrite production inputs")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "date": day, "mode": MODE,
        "coverage": data["coverage"],
        "comparison": data["comparison"],
        "output": str(output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
