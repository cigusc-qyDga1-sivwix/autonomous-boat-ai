"""Read-only proof that today's formal v2.4 reached saved LIVE forecasts.

No network. No mutation. No outcomes/odds. This tool inspects the frozen
forecast view stored in the repo. It is safe to execute in CI on a checked-out
snapshot; it does not retroactively generate or change wagers.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

UTC = timezone.utc
JST = timezone(timedelta(hours=9))
V24 = "four-factor-v2.4-entry-exhibition-balance-untrained"
V23 = "four-factor-v2.3-conditional-second-primary-untrained"


def summarize(payload: dict) -> dict:
    rows = payload.get("forecast_races") or []
    if not isinstance(rows, list):
        raise ValueError("Malformed forecast_races")
    models, phases, by_venue = Counter(), Counter(), defaultdict(lambda: {
        "forecast": 0, "exhibition": 0, "formal": 0, "v24": 0,
        "v24_formal": 0, "venue_tactics_saved": 0,
        "venue_tactics_effect_active": 0, "balance_applied": 0,
        "head_pressure_applied": 0, "original_exhibition_available": 0,
    })
    alerts, samples = [], []
    for race in rows:
        venue = str(race.get("venue") or "UNKNOWN")
        group = by_venue[venue]
        model, phase = race.get("model_version"), race.get("phase")
        models[str(model)] += 1
        phases[str(phase)] += 1
        group["forecast"] += 1
        group["exhibition"] += phase == "exhibition"
        group["formal"] += race.get("ticket_status") == "formal"
        group["v24"] += model == V24
        meta = race.get("formal_insight_v24")
        tactics = race.get("venue_tactics_v2")
        group["venue_tactics_saved"] += isinstance(tactics, dict)
        group["venue_tactics_effect_active"] += isinstance(tactics, dict) and tactics.get("applied") is True
        group["balance_applied"] += isinstance(meta, dict) and meta.get("exhibition_balance", {}).get("applied") is True
        group["head_pressure_applied"] += isinstance(meta, dict) and meta.get("inside_pressure", {}).get("applied") is True
        group["original_exhibition_available"] += any(
            bool(x.get("original_exhibition")) for x in race.get("racers") or [] if isinstance(x, dict)
        )
        if phase == "exhibition" and race.get("ticket_status") == "formal":
            if model == V24:
                group["v24_formal"] += 1
                issues = []
                if not isinstance(meta, dict) or meta.get("formal_component") is not True:
                    issues.append("v24_metadata_missing")
                if not isinstance(tactics, dict):
                    issues.append("venue_tactics_provenance_missing")
                if not isinstance(race.get("postrace_conditional_v13"), dict):
                    issues.append("second_third_provenance_missing")
                if not isinstance(race.get("venue_profile"), dict):
                    issues.append("venue_profile_missing")
                if sum(int(x.get("virtual_yen") or 0) for x in race.get("bets") or []) != 50000:
                    issues.append("formal_budget_not_50000")
                if not isinstance(race.get("sha256"), str) or len(race["sha256"]) != 64:
                    issues.append("frozen_sha_missing")
                if isinstance(meta, dict):
                    if not isinstance(meta.get("control_bets"), list):
                        issues.append("same_input_v23_control_missing")
                    if meta.get("pre_cutoff_only") is not True or meta.get("result_data_used") is not False:
                        issues.append("unsafe_v24_provenance")
                cutoff = race.get("cutoff_jst")
                frozen = race.get("frozen_at_utc")
                day = payload.get("event_date")
                try:
                    freeze_time = datetime.fromisoformat(frozen).astimezone(JST)
                    cutoff_time = datetime.fromisoformat(f"{day}T{cutoff}:00+09:00")
                    if freeze_time > cutoff_time - timedelta(seconds=120):
                        issues.append("late_freeze")
                except (ValueError, TypeError, AttributeError):
                    issues.append("timestamp_missing")
                if issues:
                    alerts.append({"venue": venue, "race": race.get("race"), "issues": issues})
                if len(samples) < 12:
                    samples.append({
                        "venue": venue, "race": race.get("race"),
                        "model": model, "phase": phase,
                        "ticket_status": race.get("ticket_status"),
                        "frozen_at_utc": frozen, "cutoff_jst": cutoff,
                        "sha": race.get("sha256"),
                        "venue_tactics_saved": isinstance(tactics, dict),
                        "venue_tactics_applied": tactics.get("applied") if isinstance(tactics, dict) else None,
                        "v24_exhibition_balance_applied": meta.get("exhibition_balance", {}).get("applied") if isinstance(meta, dict) else None,
                        "v24_head_pressure_applied": meta.get("inside_pressure", {}).get("applied") if isinstance(meta, dict) else None,
                        "same_input_v23_control_saved": isinstance(meta.get("control_bets"), list) if isinstance(meta, dict) else False,
                        "point_count": len(race.get("bets") or []),
                        "issues": issues,
                    })
    return {
        "event_date": payload.get("event_date"),
        "source_updated_at_utc": payload.get("updated_at_utc"),
        "listed_races": payload.get("listed_races"),
        "forecast_count": len(rows),
        "model_counts": dict(sorted(models.items())),
        "phase_counts": dict(sorted(phases.items())),
        "formal_v24_count": sum(x["v24_formal"] for x in by_venue.values()),
        "venue_count": len(by_venue),
        "by_venue": dict(sorted(by_venue.items())),
        "v24_samples": samples,
        "v24_alerts": alerts,
        "audit_limitation": ("This checks already-saved exhibition predictions, "
            "not results or future performance. Formal predictions may be absent "
            "until pre-cutoff exhibitions arrive. Existing snapshots are immutable."),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="app/data/live/latest.json")
    ap.add_argument("--fail-on-alert", action="store_true", help="Strict mode for new post-fix snapshots only")
    args = ap.parse_args()
    p = Path(args.input)
    report = summarize(json.loads(p.read_text(encoding="utf-8")))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 1 if args.fail_on_alert and report["v24_alerts"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
