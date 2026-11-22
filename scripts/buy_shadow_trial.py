"""Forward-only, read-only BUY/WATCH/SKIP research shadow.

This module NEVER changes formal tickets, classifications, model weights, or
payout ledgers. BUY means only a pre-registered *research candidate*, not
positive expected value, profitability, or a recommendation to wager.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

UTC = timezone.utc
JST = ZoneInfo("Asia/Tokyo")
START_DAY = "2026-11-17"
SCHEMA = "boatlabs.buy-shadow-forward.v1"
RULE_V1 = "relative-head-separation-v0.1"
RULE = "relative-head-separation-point-neutral-v0.2"
POINT_NEUTRAL_FROM_DAY = "2026-11-23"
# Uncalibrated head-separation cutoffs. Preserve v0.1 for all historical days.
# No official results, payoffs, or odds are used to set an individual decision.
THRESHOLDS_V1 = {
    "buy_head_concentration_gte": 0.62,
    "buy_head_gap_gte": 0.40,
    "buy_ticket_count_lte": 10,
    "skip_head_concentration_lt": 0.37,
    "skip_head_gap_lt": 0.12,
}
THRESHOLDS = {key: value for key, value in THRESHOLDS_V1.items()
              if key != "buy_ticket_count_lte"}


def _policy_for_day(day):
    return (RULE, THRESHOLDS) if day >= POINT_NEUTRAL_FROM_DAY else (RULE_V1, THRESHOLDS_V1)
SAFE_LEAD = timedelta(minutes=2)
COMBO = re.compile(r"^[1-6]-[1-6]-[1-6]$")
SHA = re.compile(r"^[a-f0-9]{64}$", re.I)


def _combo(text):
    return isinstance(text, str) and COMBO.fullmatch(text) and len(set(text.split("-"))) == 3


def _cutoff(day, clock):
    if not isinstance(clock, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", clock):
        return None
    try:
        return datetime.fromisoformat(f"{day}T{clock}:00+09:00")
    except ValueError:
        return None


def _datetime(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result if result.tzinfo else None
    except ValueError:
        return None


def classify(race, *, rule=RULE):
    """Study-only heuristic, not a calibrated win chance or EV.

    The prospective v0.2 policy never downgrades BUY solely for ticket count.
    Historical v0.1 decisions retain their original <=10-ticket restriction.
    """
    if rule not in (RULE_V1, RULE):
        raise ValueError("Unknown BUY research policy")
    concentration, gap = race.get("head_weight_concentration"), race.get("head_weight_gap")
    if not all(isinstance(x, (int, float)) and math.isfinite(x)
               for x in (concentration, gap)):
        return "WATCH", "missing_unscaled_head_metrics"
    if concentration >= 0.62 and gap >= 0.40:
        if rule == RULE_V1 and len(race.get("bets") or []) > THRESHOLDS_V1["buy_ticket_count_lte"]:
            return "WATCH", "intermediate_relative_head_separation"
        return "BUY", "strong_relative_head_separation"
    if concentration < 0.37 or gap < 0.12:
        return "SKIP", "weak_or_competing_head_paths"
    return "WATCH", "intermediate_relative_head_separation"


def _eligible(race, day, now):
    if race.get("venue") == "江戸川" or race.get("phase") != "exhibition":
        return False
    if race.get("classification") == "SKIP" or race.get("ticket_status") != "formal":
        return False
    if race.get("entry_exhibition_gate", {}).get("final_eligible") is not True:
        return False
    verified = race.get("exhibition_input_check") or {}
    if verified.get("verified_before_freeze") is not True:
        return False
    if verified.get("six_boats_matched") != 6 or len(race.get("racers") or []) != 6:
        return False
    sha = race.get("sha256")
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        return False
    if race.get("formal_snapshot_sha256") != sha:
        return False
    if not isinstance(race.get("race"), int) or not 1 <= race["race"] <= 12:
        return False
    cutoff, frozen = _cutoff(day, race.get("cutoff_jst")), _datetime(race.get("frozen_at_utc"))
    if cutoff is None or frozen is None:
        return False
    if not (frozen <= now < cutoff - SAFE_LEAD and frozen <= cutoff - SAFE_LEAD):
        return False
    bets = race.get("bets") or []
    if not bets or not all(_combo(b.get("combination")) for b in bets if isinstance(b, dict)):
        return False
    if not all(isinstance(b, dict) for b in bets):
        return False
    return True


def _verify_decision_sha(row):
    stored = row.get("decision_sha256")
    payload = {key: value for key, value in row.items() if key != "decision_sha256"}
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return isinstance(stored, str) and stored == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def freeze(payload, now, previous=None):
    """Only append new, before-cutoff decisions for the real calendar day."""
    now = now.astimezone(UTC)
    day = now.astimezone(JST).date().isoformat()
    if day < START_DAY or payload.get("event_date") != day or payload.get("mode") != "auto-live":
        raise ValueError("Only current JST trial-day auto-live forecasts are eligible")
    rule, thresholds = _policy_for_day(day)
    prior = previous or {}
    if prior and (prior.get("schema") != SCHEMA or prior.get("event_date") != day
                  or prior.get("rule") != rule):
        raise ValueError("Existing trial ledger has the wrong schema, date, or policy")
    records = list(prior.get("entries") or [])
    if any(not _verify_decision_sha(row) for row in records):
        raise ValueError("Previously frozen decision SHA does not match")
    seen = {r["race_id"] for r in records}
    for race in payload.get("forecast_races") or []:
        if not isinstance(race, dict) or not _eligible(race, day, now):
            continue
        key = f"{day}|{race['venue']}|{race['race']}"
        if key in seen:
            continue  # A decision never changes after its initial freeze.
        decision, reason = classify(race, rule=rule)
        head = race.get("head_course_shares") or []
        eligible_heads = [row for row in head if isinstance(row, dict)
                          and isinstance(row.get("relative_share"), (int, float))
                          and math.isfinite(row["relative_share"])]
        top_lane = max(eligible_heads, key=lambda x: x["relative_share"]).get("lane") if eligible_heads else None
        decision_entry = {
            "race_id": key,
            "event_date": day,
            "venue": race["venue"],
            "race": race["race"],
            "cutoff_jst": race["cutoff_jst"],
            "source_model": race.get("model_version"),
            "source_sha256": race["sha256"],
            "source_frozen_at_utc": race["frozen_at_utc"],
            "decision_frozen_at_utc": now.isoformat(),
            "decision": decision,
            "reason": reason,
            "head_concentration": race.get("head_weight_concentration"),
            "head_gap": race.get("head_weight_gap"),
            "ticket_count": len(race["bets"]),
            "head_lane_reference": top_lane,
            "bet_combinations": [b["combination"] for b in race["bets"]],
            "original_classification": race["classification"],
            "research_only": True,
        }
        canonical = json.dumps(decision_entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        decision_entry["decision_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        records.append(decision_entry)
        seen.add(key)
    records.sort(key=lambda r: (r["cutoff_jst"], r["venue"], r["race"]))
    return {
        "schema": SCHEMA, "rule": rule, "event_date": day,
        "created_before_official_results": True,
        "no_odds_or_payout_inputs": True,
        "no_formal_ticket_or_classification_changes": True,
        "thresholds": thresholds,
        "entries": records,
    }


def _miss_reason(bets, actual):
    if actual in bets:
        return "hit"
    first, second, _ = actual.split("-")
    if not any(b.startswith(first + "-") for b in bets):
        return "head_miss"
    if not any(b.startswith(first + "-" + second + "-") for b in bets):
        return "second_miss"
    return "third_miss"


def evaluate(trial, payload):
    """Post-race, official-only read of immutable shadow decisions; no reclassification."""
    if trial.get("schema") != SCHEMA or trial.get("event_date") != payload.get("event_date"):
        raise ValueError("Day/schema mismatch; no cross-date settlement allowed")
    expected_rule, _ = _policy_for_day(trial["event_date"])
    if trial.get("rule") != expected_rule:
        raise ValueError("Frozen BUY policy does not match its effective date")
    official, alerts = payload.get("official_results") or {}, payload.get("settlement_alerts") or {}
    tally = {k: {"frozen": 0, "verified": 0, "hits": 0, "head_miss": 0,
                 "second_miss": 0, "third_miss": 0, "unresolved": 0} for k in ("BUY", "WATCH", "SKIP")}
    verified = []
    for row in trial.get("entries") or []:
        if not _verify_decision_sha(row):
            raise ValueError("Frozen decision SHA mismatch")
        category = row.get("decision")
        if category not in tally:
            raise ValueError("Unknown frozen decision")
        cohort = tally[category]
        cohort["frozen"] += 1
        key = row["race_id"]
        result = official.get(key)
        if (key in alerts or not isinstance(result, dict)
                or result.get("source") != "boatrace_official_pay"
                or result.get("verified") is not True
                or result.get("snapshot_sha256") != row["source_sha256"]
                or not _combo(result.get("finish"))
                or result.get("void_trifecta") is True
                or bool(result.get("refunded_boats"))):
            cohort["unresolved"] += 1
            continue
        outcome = _miss_reason(row["bet_combinations"], result["finish"])
        cohort["verified"] += 1
        if outcome == "hit":
            cohort["hits"] += 1
        else:
            cohort[outcome] += 1
        verified.append({
            "race_id": key, "decision": category, "frozen_source_sha256": row["source_sha256"],
            "official_finish": result["finish"], "outcome": outcome,
        })
    return {
        "schema": "boatlabs.buy-shadow-official-audit.v1",
        "event_date": trial["event_date"], "rule": trial["rule"], "research_only": True,
        "outcome_not_used_to_reclassify": True, "no_real_or_virtual_roi_claim": True,
        "cohorts": tally, "verified_rows": verified,
    }


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == serialized:
        return False
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(serialized, encoding="utf-8")
    os.replace(tmp, path)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["freeze", "evaluate"])
    parser.add_argument("--input", type=Path, default=Path("app/data/live/latest.json"))
    parser.add_argument("--trial", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    payload = _read(args.input)
    if args.mode == "freeze":
        now = datetime.now(UTC)
        day = now.astimezone(JST).date().isoformat()
        if day < START_DAY or payload.get("event_date") != day:
            print(json.dumps({"status": "source_not_current_or_trial_not_started", "day": day}))
            return
        target = args.out or Path(f"app/data/experiments/buy-shadow-{day}.json")
        prior = _read(target) if target.exists() else None
        result = freeze(payload, now, prior)
    else:
        day = payload.get("event_date")
        source = args.trial or Path(f"app/data/experiments/buy-shadow-{day}.json")
        if not source.exists():
            print(json.dumps({"status": "no_frozen_trial", "day": day}))
            return
        target = args.out or Path("app/data/experiments/buy-shadow-eval-latest.json")
        result = evaluate(_read(source), payload)
    changed = _save(target, result)
    print(json.dumps({"status": "updated" if changed else "unchanged",
                      "path": str(target), "entries": len(result.get("entries") or []),
                      "cohorts": result.get("cohorts")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
