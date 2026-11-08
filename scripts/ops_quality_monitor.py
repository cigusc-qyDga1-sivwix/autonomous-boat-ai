#!/usr/bin/env python3
"""Read-only BOAT LAB operational integrity monitor.

This reads published JSON, never calls external APIs, rewrites frozen predictions,
changes forecast decisions, or publishes results. A passing audit is NOT proof
of iPhone/PWA visibility or of any public-source capture before cutoff.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))


def timestamp(value):
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp missing")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp timezone missing")
    return result


def evaluate(live, sync, exhibition, audit, *, now, stale_minutes=30):
    """Check invariants using independent views; do not mutate the inputs."""
    now = timestamp(now) if isinstance(now, str) else now
    if now.tzinfo is None:
        raise ValueError("now must have a timezone")
    today = now.astimezone(JST).date().isoformat()
    problems = []

    def mark(severity, code, detail):
        problems.append({"severity": severity, "code": code, "detail": detail})

    if not all(isinstance(v, dict) for v in (live, sync, exhibition, audit)):
        raise ValueError("all source documents must be JSON objects")

    # Missing or stale artifacts are not equivalent to zero forecasts.
    for label, document in (("latest", live), ("forecast_sync", sync),
                            ("exhibition_status", exhibition), ("forecast_audit", audit)):
        if document.get("event_date") != today:
            mark("warning", "DAY_MISMATCH", f"{label}: {document.get('event_date')} vs {today}")

    age_min = None
    try:
        capture = timestamp(sync["captured_at_utc"])
        age_min = round((now - capture).total_seconds() / 60, 1)
        if age_min < -2:
            mark("warning", "FUTURE_CAPTURE", f"forecast captured {age_min} min in future")
        # Official cron may skip runs; this remains a warning, not a code-crash verdict.
        if 6 <= now.astimezone(JST).hour < 24 and age_min > stale_minutes:
            mark("warning", "FORECAST_STALE", f"forecast capture age {age_min} min")
    except (KeyError, ValueError, TypeError):
        mark("critical", "CAPTURE_TIMESTAMP_INVALID", "missing or naive forecast capture timestamp")

    races = live.get("forecast_races")
    if not isinstance(races, list):
        mark("critical", "RACES_SCHEMA_INVALID", "forecast_races must be an array")
        races = []
    officials = live.get("official_results")
    if not isinstance(officials, dict):
        mark("critical", "OFFICIAL_SCHEMA_INVALID", "official_results must be an object")
        officials = {}
    published_count = sum(isinstance(r, dict) for r in races)
    if published_count != len(races):
        mark("critical", "RACE_ENTRY_INVALID", "non-object forecast record")
    if type(sync.get("forecast_races")) is not int or sync["forecast_races"] != len(races):
        mark("warning", "SYNC_COUNT_MISMATCH", "forecast sync count differs from published view")
    if sync.get("status") != "completed":
        mark("warning", "SYNC_NOT_COMPLETED", "latest capture has not completed")

    formal, exhibitions, invalid_times = 0, 0, 0
    by_identity = {}
    for index, race in enumerate(races):
        if not isinstance(race, dict):
            continue
        key = f"{today}|{race.get('venue')}|{race.get('race')}"
        if key in by_identity:
            mark("critical", "DUPLICATE_RACE", key)
        by_identity[key] = race
        if race.get("phase") == "exhibition":
            exhibitions += 1
        if race.get("ticket_status") == "formal":
            formal += 1
            gate = race.get("entry_exhibition_gate") or {}
            if (race.get("phase") != "exhibition" or
                    gate.get("final_eligible") is not True or
                    race.get("formal_snapshot_sha256") != race.get("sha256") or
                    not race.get("sha256")):
                mark("critical", "FORMAL_GATE_MISMATCH", key)
        try:
            freeze = timestamp(race["frozen_at_utc"]).astimezone(JST)
            clock = str(race["cutoff_jst"])
            cutoff = datetime.fromisoformat(f"{today}T{clock}").replace(tzinfo=JST)
            if freeze >= cutoff:
                mark("critical", "POST_CUTOFF_FREEZE", key)
                invalid_times += 1
        except (KeyError, ValueError, TypeError):
            mark("critical", "FREEZE_TIME_INVALID", key)
            invalid_times += 1

    verified = 0
    for key, proof in officials.items():
        if not isinstance(proof, dict) or proof.get("verified") is not True or proof.get("source") != "boatrace_official_pay":
            mark("critical", "UNVERIFIED_OFFICIAL", str(key))
            continue
        verified += 1
        race = by_identity.get(key)
        if race is None:
            mark("critical", "OFFICIAL_WITHOUT_FORECAST", str(key))
        elif proof.get("snapshot_sha256") and proof["snapshot_sha256"] != race.get("sha256"):
            mark("critical", "OFFICIAL_SHA_MISMATCH", str(key))

    if (type(live.get("final_exhibition_verified_races")) is int and
            live["final_exhibition_verified_races"] < formal):
        mark("warning", "FORMAL_COUNT_INCONSISTENT", "more formal tickets than eligible exhibition races")

    # Research acquisition is deliberately NOT used as evidence for formal picks.
    metrics = {
        "forecast_age_minutes": age_min,
        "listed_races": live.get("listed_races"),
        "frozen_forecast_races": len(races),
        "exhibition_phase_races": exhibitions,
        "formal_ticket_races": formal,
        "verified_official_results": verified,
        "invalid_freeze_times": invalid_times,
        "exhibition_research_six_boat": exhibition.get("complete_six_boat_research_races"),
        "official_verified_forecasts_in_audit": (audit.get("coverage") or {}).get("official_verified_forecasts"),
    }
    state = "critical" if any(p["severity"] == "critical" for p in problems) else (
        "warning" if problems else "ok")
    return {
        "schema": "boatlabs.ops_quality.v1", "event_date": today,
        "checked_at_utc": now.astimezone(timezone.utc).isoformat(),
        "status": state, "metrics": metrics, "findings": problems,
        "evidence_scope": "Repository JSON only. PWA display, external freshness, and on-water accuracy remain unverified.",
        "prediction_model_modified": False,
    }


def markdown(report):
    m = report["metrics"]
    lines = [f"## BOAT LAB 品質監視 — {report['event_date']}",
             f"判定：**{report['status']}**（GitHub保存JSONの整合性のみ）", "",
             f"- 予想固定：{m['frozen_forecast_races']}R / 掲載：{m['listed_races']}R",
             f"- 展示phase：{m['exhibition_phase_races']}R / 正式表示：{m['formal_ticket_races']}R",
             f"- 公式確認済み結果：{m['verified_official_results']}R",
             f"- 最終予想取得からの経過：{m['forecast_age_minutes']}分", "",
             "**本番アプリ画面とのSHA一致および実際の取得遅延は、この監視だけでは未確認。**"]
    for item in report["findings"]:
        lines.append(f"- {item['severity'].upper()}: {item['code']} — {item['detail']}")
    if not report["findings"]:
        lines.append("- 保存JSON内では検査対象の不整合を検出せず")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--now-iso")
    parser.add_argument("--stale-minutes", type=int, default=30)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-markdown", type=Path)
    args = parser.parse_args()
    if args.stale_minutes <= 0:
        parser.error("--stale-minutes must be positive")
    paths = ("app/data/live/latest.json", "app/data/live/forecast-sync-latest.json",
             "app/data/exhibition/status-latest.json", "app/data/live/audit-latest.json")
    docs = [json.loads((args.root / path).read_text(encoding="utf-8")) for path in paths]
    report = evaluate(*docs, now=args.now_iso or datetime.now(timezone.utc),
                      stale_minutes=args.stale_minutes)
    if args.output_json:
        args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.output_markdown:
        args.output_markdown.write_text(markdown(report), encoding="utf-8")
    print(markdown(report))
    # An operational warning should not block forecast collection or hide logs.
    # Critical mismatches are surfaced for manual triage, not auto-repaired.


if __name__ == "__main__":
    main()
