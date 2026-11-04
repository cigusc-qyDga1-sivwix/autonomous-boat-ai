"""Venue-stratified, historical ST × winning-technique proxy diagnostics.

23 venues (excludes 03 Edogawa) and coarse location/tactic/ST contrast bins.
No invented venue advantage or intentional marking counts. Winner-conditioned
samples cannot be interpreted as attack-success probabilities.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

try:
    from .start_technique_pressure_proxy import interpret, VERSION as PROXY_VERSION
    from .venue_profiles import VENUE_PROFILES
except ImportError:
    from start_technique_pressure_proxy import interpret, VERSION as PROXY_VERSION
    from venue_profiles import VENUE_PROFILES

VERSION = "venue-start-technique-proxy-v0.1"
VENUES = tuple(sorted(code for code in VENUE_PROFILES if code != "03"))
CATEGORIES = (
    "outer_start_advantage",
    "close_start_possible_course_contest",
    "no_clear_start_advantage",
    "cannot_evaluate_start_interaction",
)
# Empirical-Bayes-like smoothing strength is a research assumption, not fitted.
PRIOR_N = 40
MIN_VENUE_COMPARISONS = 30


def _venue(record):
    code = str(record.get("race_code", ""))
    if len(code) != 12 or not code.isdigit():
        raise ValueError("bad race code")
    venue = code[8:10]
    if venue == "03":
        return None
    if venue not in VENUES:
        raise ValueError("unknown venue")
    return venue


def _valid(record, *, before_date=None):
    if record.get("schema") != PROXY_VERSION:
        raise ValueError("invalid proxy schema")
    code = str(record.get("race_code", ""))
    if record.get("event_date", "").replace("-", "") != code[:8]:
        raise ValueError("race date mismatch")
    event_day = date.fromisoformat(record["event_date"])
    if before_date is not None and event_day >= before_date:
        raise ValueError("current/future outcomes forbidden")
    sha = record.get("source_sha256")
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("missing source proof")
    if record.get("confirmed_mark_count") is not None or record.get("eligible_as_same_race_forecast_input") is not False:
        raise ValueError("result proxy must not be treated as observed marking or current input")
    if record.get("winning_technique") not in ("逃げ", "差し", "まくり", "まくり差し", "抜き", "恵まれ"):
        raise ValueError("missing winning technique")
    if type(record.get("winner_course")) is not int or record["winner_course"] not in range(1, 7):
        raise ValueError("invalid actual course")
    comps = record.get("comparisons")
    if not isinstance(comps, list):
        raise ValueError("missing comparison list")
    for item in comps:
        if not isinstance(item, dict) or item.get("hypothesis") not in CATEGORIES:
            raise ValueError("invalid comparison")
        course = item.get("inside_course")
        if type(course) is not int or not 1 <= course < record["winner_course"]:
            raise ValueError("invalid compared inner course")


def _empty():
    return {name: 0 for name in CATEGORIES}


def summarize_venues(records, *, before_date=None):
    """23 rows, keyed by venue code; details grouped per actual winning course.

    'rate' denominators include only valid ST comparisons; missing/F are
    reported separately. Global reference is trained from the same *past*
    records and only descriptive, not a prospective forecast.
    """
    if isinstance(before_date, str):
        before_date = date.fromisoformat(before_date)
    if before_date is not None and not isinstance(before_date, date):
        raise ValueError("invalid historical cutoff")
    unique = set()
    stats = {code: {
        "venue_name": VENUE_PROFILES[code]["name"], "races": 0,
        "attack_win_races": 0, "counts": Counter(),
        "by_winning_course": defaultdict(Counter),
        "by_winning_technique": defaultdict(Counter),
        "by_inner_course": defaultdict(Counter),
    } for code in VENUES}
    global_counts = Counter()
    for record in records:
        _valid(record, before_date=before_date)
        code = record["race_code"]
        if code in unique:
            raise ValueError("duplicate race")
        unique.add(code)
        venue = _venue(record)
        if venue is None:
            continue  # User deliberately excludes Edogawa
        row = stats[venue]
        row["races"] += 1
        if record["winning_technique"] in ("まくり", "まくり差し"):
            row["attack_win_races"] += 1
        for comp in record["comparisons"]:
            category = comp["hypothesis"]
            row["counts"][category] += 1
            row["by_winning_course"][str(record["winner_course"])][category] += 1
            row["by_winning_technique"][record["winning_technique"]][category] += 1
            row["by_inner_course"][str(comp["inside_course"])][category] += 1
            global_counts[category] += 1
    valid_total = sum(global_counts[k] for k in CATEGORIES[:3])
    # Missing ST is not silently counted as a negative result.
    global_rates = {
        k: (global_counts[k] / valid_total if valid_total else None)
        for k in CATEGORIES[:3]
    }
    venues = {}
    for code, row in stats.items():
        counts = row["counts"]
        valid = sum(counts[k] for k in CATEGORIES[:3])
        rates = {
            k: (counts[k] / valid if valid else None)
            for k in CATEGORIES[:3]
        }
        shrunk = {
            k: ((counts[k] + PRIOR_N * global_rates[k]) / (valid + PRIOR_N)
                if valid and global_rates[k] is not None else None)
            for k in CATEGORIES[:3]
        }
        venues[code] = {
            "venue_name": row["venue_name"], "races": row["races"],
            "attack_win_races": row["attack_win_races"],
            "valid_comparisons": valid,
            "missing_st_comparisons": counts[CATEGORIES[3]],
            "comparison_counts": {k: counts[k] for k in CATEGORIES},
            "descriptive_share_given_attack_win": rates,
            "shrunk_share_given_attack_win": shrunk,
            "by_winning_course": {k: {cat: ct[cat] for cat in CATEGORIES}
                                  for k, ct in sorted(row["by_winning_course"].items())},
            "by_winning_technique": {k: {cat: ct[cat] for cat in CATEGORIES}
                                     for k, ct in sorted(row["by_winning_technique"].items())},
            "by_inner_course": {k: {cat: ct[cat] for cat in CATEGORIES}
                                for k, ct in sorted(row["by_inner_course"].items())},
            "status": ("INSUFFICIENT" if valid < MIN_VENUE_COMPARISONS else
                       "DESCRIPTIVE_ONLY"),
            "eligible_for_formal_forecast": False,
            "confirmed_mark_count": None,
        }
    return {
        "schema": VERSION, "venues": venues, "eligible_venue_codes": list(VENUES),
        "excluded_venue_codes": ["03"], "distinct_races": len(unique),
        "before_date_exclusive": before_date.isoformat() if before_date else None,
        "global_reference": {"valid_comparisons": valid_total,
                             "comparison_counts": {k: global_counts[k] for k in CATEGORIES},
                             "descriptive_share_given_attack_win": global_rates},
        "prior_n": PRIOR_N,
        "caveat": ("Winner-conditioned start contrasts are NOT the chance of winning "
                   "by each tactic, and NOT confirmed marking or obstruction counts."),
        "eligible_for_formal_forecast": False,
    }


def build_from_result_rows(rows, *, before_date):
    """Turn *historical* raw result rows into proxies, without future leakage.

    Each input element has event_date, source_sha256, row. Source snapshots
    must come from a permitted provider. Rejects any event on/after cutoff.
    """
    boundary = date.fromisoformat(before_date)
    result = []
    for item in rows:
        event_date = date.fromisoformat(item["event_date"])
        if event_date >= boundary:
            raise ValueError("current/future race cannot be training evidence")
        result.append(interpret(item["row"], event_date=item["event_date"],
                                source_sha256=item["source_sha256"]))
    return summarize_venues(result, before_date=boundary)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True,
                   help="JSON list of licensed historical {event_date,source_sha256,row}")
    p.add_argument("--before-date", required=True,
                   help="exclusive YYYY-MM-DD; excludes current and future outcomes")
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    rows = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit("input must be a list of historical result rows")
    summary = build_from_result_rows(rows, before_date=args.before_date)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(f"historical races={summary['distinct_races']} venues={len(summary['venues'])}")


if __name__ == "__main__":
    main()
