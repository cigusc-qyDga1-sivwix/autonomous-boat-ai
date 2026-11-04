"""Postrace-only ST formation and conditional finishing-place diagnostics.

Input is licensed BoatraceCSV-style *result* data. Observed ST and winning
techniques are NOT observable at forecast time; this module cannot generate
formal pre-race bets or infer intentional interference/turn trajectories.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

try:
    from .start_technique_pressure_proxy import interpret as interpret_result
    from .venue_profiles import VENUE_PROFILES
except ImportError:
    from start_technique_pressure_proxy import interpret as interpret_result
    from venue_profiles import VENUE_PROFILES

VERSION = "conditional-st-coupling-study-v0.1-postrace"
VENUES = tuple(sorted(k for k in VENUE_PROFILES if k != "03"))
SLIT_GROUPS = (
    "inside_clear_start_lead",
    "near_even_start",
    "inside_behind_middle",
    "inside_behind_outer",
    "unknown_st",
)
# Research thresholds, not calibrated transition probabilities.
SLIT_NEAR_SEC = .04
MIN_PAIR_RACES = 20


def _finish_boat(row, place):
    raw = str(row.get(f"{place}着_艇番", "")).strip()
    if raw not in "123456" or len(raw) != 1:
        raise ValueError("three unambiguous finish boats required")
    return int(raw)


def label_result(row, *, event_date: str, source_sha256: str) -> dict:
    """Describe actual positions AFTER the race; no 1M geometry is inferred."""
    proxy = interpret_result(row, event_date=event_date, source_sha256=source_sha256)
    finish = tuple(_finish_boat(row, n) for n in (1, 2, 3))
    if len(set(finish)) != 3 or finish[0] != proxy["winner_lane"]:
        raise ValueError("winner or top-three finish mismatch")
    actual_courses = proxy["actual_course_order"]
    finish_courses = tuple(actual_courses.index(lane) + 1 for lane in finish)
    st_by_course = [proxy["st_by_lane"][str(lane)] for lane in actual_courses]
    st_statuses = [proxy["st_status_by_lane"][str(lane)] for lane in actual_courses]
    if any(x != "LEGAL" for x in st_statuses):
        slit = "unknown_st"
        in_gap = None
    else:
        # Sign: + means course 1 ahead of every outside course at slit.
        min_out = min(st_by_course[1:])
        in_gap = round(min_out - st_by_course[0], 4)
        if in_gap >= SLIT_NEAR_SEC:
            slit = "inside_clear_start_lead"
        elif in_gap >= -SLIT_NEAR_SEC:
            slit = "near_even_start"
        else:
            fastest_out = min(range(2, 7), key=lambda c: (st_by_course[c-1], c))
            slit = ("inside_behind_middle" if fastest_out <= 4
                    else "inside_behind_outer")
    return {
        "schema": VERSION,
        "race_code": proxy["race_code"],
        "event_date": proxy["event_date"],
        "source_sha256": source_sha256,
        "venue_code": proxy["race_code"][8:10],
        "winning_technique": proxy["winning_technique"],
        "winner_course": finish_courses[0],
        "second_course": finish_courses[1],
        "third_course": finish_courses[2],
        "course1_finish": (finish_courses.index(1) + 1
                           if 1 in finish_courses else "outside_top3"),
        "actual_course_order": actual_courses,
        "observed_slit_group": slit,
        "course1_vs_fastest_out_st_gap_seconds": in_gap,
        "confirmed_mark_count": None,
        "confirmed_1m_path": None,
        "eligible_for_current_race_forecast": False,
        "source_type": "postrace_observed_start_and_finish",
    }


def _empty_venue(code):
    return {
        "venue": VENUE_PROFILES[code]["name"],
        "races": 0,
        "winner_courses": Counter(),
        "methods": Counter(),
        "course1_positions": Counter(),
        "by_slit": defaultdict(lambda: {
            "races": 0, "winner_courses": Counter(),
            "course1_outside_top3": 0}),
        "by_winner": defaultdict(lambda: {
            "races": 0, "second_courses": Counter(), "third_courses": Counter(),
            "top3_partner_courses": Counter()}),
    }


def summarize(rows, *, before_date: str) -> dict:
    """Preceding dates only, separate venue/head/2nd/3rd/slit groups."""
    cutoff = date.fromisoformat(before_date)
    data = {v: _empty_venue(v) for v in VENUES}
    seen = set()
    total = 0
    excluded = 0
    for row in rows:
        if not isinstance(row, dict) or row.get("schema") != VERSION:
            raise ValueError("unrecognized study label")
        code = row["race_code"]
        event_date = date.fromisoformat(row["event_date"])
        if code[:8] != event_date.strftime("%Y%m%d") or event_date >= cutoff:
            raise ValueError("future/current race label prohibited")
        if code in seen:
            raise ValueError("duplicate race outcome")
        seen.add(code)
        venue = code[8:10]
        if venue != row.get("venue_code") or venue not in VENUE_PROFILES:
            raise ValueError("venue mismatch")
        if row.get("confirmed_mark_count") is not None or row.get("eligible_for_current_race_forecast") is not False:
            raise ValueError("postrace label falsely promoted")
        if row.get("observed_slit_group") not in SLIT_GROUPS:
            raise ValueError("unknown slit group")
        if venue == "03":
            excluded += 1
            continue
        c1, c2, c3 = (row[field] for field in
                      ("winner_course", "second_course", "third_course"))
        if any(type(x) is not int or x not in range(1, 7)
               for x in (c1, c2, c3)) or len({c1, c2, c3}) != 3:
            raise ValueError("invalid course finish")
        v = data[venue]
        total += 1
        v["races"] += 1
        v["winner_courses"][str(c1)] += 1
        v["methods"][row["winning_technique"]] += 1
        position = row["course1_finish"]
        if position != "outside_top3" and position not in (1, 2, 3):
            raise ValueError("course1 finish invalid")
        if position != (("outside_top3") if 1 not in (c1, c2, c3)
                        else (c1, c2, c3).index(1) + 1):
            raise ValueError("course1 finish inconsistent")
        v["course1_positions"][str(position)] += 1
        slit = v["by_slit"][row["observed_slit_group"]]
        slit["races"] += 1
        slit["winner_courses"][str(c1)] += 1
        if position == "outside_top3":
            slit["course1_outside_top3"] += 1
        head = v["by_winner"][str(c1)]
        head["races"] += 1
        head["second_courses"][str(c2)] += 1
        head["third_courses"][str(c3)] += 1
        head["top3_partner_courses"][str(c2)] += 1
        head["top3_partner_courses"][str(c3)] += 1

    report = {}
    for venue, d in data.items():
        by_winner = {}
        for head_course in range(1, 7):
            key = str(head_course)
            slot = d["by_winner"][key]
            n = slot["races"]
            by_winner[key] = {
                "races": n,
                "second_course_counts": {str(c): slot["second_courses"][str(c)]
                                         for c in range(1, 7)},
                "third_course_counts": {str(c): slot["third_courses"][str(c)]
                                        for c in range(1, 7)},
                "partner_top3_counts": {str(c): slot["top3_partner_courses"][str(c)]
                                        for c in range(1, 7)},
                "sample_status": "DESCRIPTIVE" if n >= MIN_PAIR_RACES else "INSUFFICIENT",
            }

        # Condition on head vs other head; never use the head-conditioned
        # outcome as a feature for THAT SAME race.
        neighbor_comparisons = {}
        for head_course in range(2, 7):
            inner = head_course - 1
            head = d["by_winner"][str(head_course)]
            n_head = head["races"]
            head_inner_top3 = head["top3_partner_courses"][str(inner)]
            n_other = d["races"] - n_head
            inner_other_top3 = sum(
                h["top3_partner_courses"][str(inner)]
                for label, h in d["by_winner"].items() if label != str(head_course))
            enough = n_head >= MIN_PAIR_RACES and n_other >= MIN_PAIR_RACES
            neighbor_comparisons[f"{head_course}head_{inner}partner"] = {
                "head_races": n_head, "other_races": n_other,
                "inner_top3_given_head_count": head_inner_top3,
                "inner_top3_given_other_head_count": inner_other_top3,
                "inner_top3_given_head_rate": (head_inner_top3/n_head if enough else None),
                "inner_top3_given_other_head_rate": (inner_other_top3/n_other if enough else None),
                "status": "DESCRIPTIVE" if enough else "INSUFFICIENT",
                "meaning": "finish correlation, not observed marking or attack",
            }

        report[venue] = {
            "name": d["venue"], "races": d["races"],
            "winner_course_counts": {str(c): d["winner_courses"][str(c)]
                                     for c in range(1, 7)},
            "decision_counts": dict(sorted(d["methods"].items())),
            "course1_finish_counts": {str(p): d["course1_positions"][str(p)]
                                      for p in (1, 2, 3, "outside_top3")},
            "by_observed_slit": {k: {
                "races": d["by_slit"][k]["races"],
                "winner_courses": {str(c): d["by_slit"][k]["winner_courses"][str(c)]
                                   for c in range(1, 7)},
                "course1_outside_top3": d["by_slit"][k]["course1_outside_top3"],
            } for k in SLIT_GROUPS},
            "conditional_followups_by_winner_course": by_winner,
            "adjacent_course_conditional_finish": neighbor_comparisons,
            "status": "DESCRIPTIVE_ONLY" if d["races"] >= 100 else "INSUFFICIENT",
        }
    return {
        "schema": VERSION,
        "before_date_exclusive": cutoff.isoformat(),
        "venues": report,
        "included_races": total,
        "excluded_edogawa_races": excluded,
        "excluded_venue_codes": ["03"],
        "no_1m_maneuver_observed": True,
        "eligible_for_formal_forecast": False,
        "interpretation": ("Actual ST and finish are used postrace only. Conditional "
                           "second/third finishing patterns cannot prove tactical interference."),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True,
                        help="Authorized historical BoatraceCSV results file")
    parser.add_argument("--event-date", required=True,
                        help="YYYY-MM-DD of this results file")
    parser.add_argument("--before-date", required=True,
                        help="Exclusive date strictly after all input races")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    encoded = args.input.read_bytes()
    sha = hashlib.sha256(encoded).hexdigest()
    rows = list(csv.DictReader(encoded.decode("utf-8-sig").splitlines()))
    labels = [label_result(row, event_date=args.event_date, source_sha256=sha)
              for row in rows]
    result = summarize(labels, before_date=args.before_date)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(f"studied={result['included_races']} excluded_edogawa={result['excluded_edogawa_races']}")


if __name__ == "__main__":
    main()
