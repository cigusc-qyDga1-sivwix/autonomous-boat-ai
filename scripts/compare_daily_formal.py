"""Read-only BOAT LAB formal-vs-yesterday daily audit. No postrace retuning."""
from __future__ import annotations
import argparse
import json
from datetime import date, timedelta
from pathlib import Path

KEYS = ("verified_races", "hits", "head_captured", "first_second_captured",
        "head_miss", "second_miss", "third_miss", "virtual_stake_yen",
        "virtual_payout_yen", "virtual_profit_yen")
PERCENT_KEYS = ("hit_rate", "return_rate", "head_capture_rate", "first_second_capture_rate")


def _formal(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("event_date"), str):
        raise ValueError("Dated audit required")
    raw = (payload.get("by_ticket_status") or {}).get("formal")
    if not isinstance(raw, dict):
        raise ValueError("Formal group unavailable: never substitute provisional")
    n = raw.get("verified_races")
    if type(n) is not int or n < 0 or any(type(raw.get(key)) is not int
                                          for key in KEYS):
        raise ValueError("Malformed formal metrics")
    if raw["hits"] > n or raw["head_miss"] + raw["second_miss"] + raw["third_miss"] + raw["hits"] != n:
        raise ValueError("Stage accounting mismatch")
    result = {key: raw[key] for key in KEYS}
    result["hit_rate"] = round(raw["hits"] / n, 5) if n else None
    stake = raw["virtual_stake_yen"]
    result["return_rate"] = round(raw["virtual_payout_yen"] / stake, 5) if stake else None
    result["head_capture_rate"] = round(raw["head_captured"] / n, 5) if n else None
    result["first_second_capture_rate"] = round(raw["first_second_captured"] / n, 5) if n else None
    return result



def _strong_field_groups(payload):
    """Only prospective, explicitly labeled and official-verified formal rows."""
    groups = payload.get("by_strong_field_formal") or {}
    out = {}
    if not isinstance(groups, dict):
        return out
    for label, metric in groups.items():
        if (label in ("NOT_ASSESSED", "INSUFFICIENT_EVIDENCE")
                or not isinstance(metric, dict)):
            continue
        n, hits, head_miss, stake = (
            metric.get("verified_races"), metric.get("hits"),
            metric.get("head_miss"), metric.get("virtual_stake_yen"))
        payout = metric.get("virtual_payout_yen")
        if not all(type(value) is int and value >= 0
                   for value in (n, hits, head_miss, stake, payout)):
            continue
        if n == 0 or hits + head_miss > n:
            continue
        out[label] = {
            "verified_races": n, "hits": hits, "head_miss": head_miss,
            "head_miss_rate": round(head_miss / n, 5),
            "hit_rate": round(hits / n, 5),
            "return_rate": round(payout / stake, 5) if stake else None,
            "virtual_stake_yen": stake,
            "virtual_payout_yen": payout,
        }
    return out

def compare(current, previous):
    day = date.fromisoformat(current["event_date"])
    before = date.fromisoformat(previous["event_date"])
    if day - before != timedelta(days=1):
        raise ValueError("Exactly consecutive JST dates required")
    latest = _formal(current)
    earlier = _formal(previous)
    d = {key: latest[key] - earlier[key] for key in KEYS}
    d.update({key + "_pp": round((latest[key] - earlier[key]) * 100, 3)
              if latest[key] is not None and earlier[key] is not None else None
              for key in PERCENT_KEYS})
    return {
        "schema": "boatlabs.formal_day_over_day_v1",
        "date_jst": current["event_date"],
        "comparison_date_jst": previous["event_date"],
        "previous_formal": earlier, "current_formal": latest,
        "day_over_day": d,
        "strong_field_previous_formal": _strong_field_groups(previous),
        "strong_field_current_formal": _strong_field_groups(current),
        "strong_field_note": "Comparisons require pre-cutoff diagnostic labels; no retrospective parity relabeling.",
        "current_models_observed_all_statuses": sorted((current.get("by_model") or {}).keys()),
        "previous_models_observed_all_statuses": sorted((previous.get("by_model") or {}).keys()),
        "previous_official_evidence_at_utc": previous.get("official_evidence_at_utc"),
        "current_official_evidence_at_utc": current.get("official_evidence_at_utc"),
        "formal_only": True, "actual_wagers": False,
        "read_only": True, "calibration_claim": False,
        "interpretation": (
            "Comparing official-verified formal forecasts on different race/venue mixes; "
            "a daily change is descriptive, not evidence that model v2.3 caused it. "
            "Watch/SKIP hypothetical stakes are never actual betting. "
            "Unconfirmed, canceled, reviewed and provisional races are excluded."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = compare(json.loads(args.current.read_text(encoding="utf-8")),
                     json.loads(args.previous.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"date": result["date_jst"], "formal_races": result["current_formal"]["verified_races"],
                      "hit_rate_delta_pp": result["day_over_day"]["hit_rate_pp"],
                      "return_rate_delta_pp": result["day_over_day"]["return_rate_pp"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
