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
import subprocess
from datetime import date, datetime, timedelta, timezone
from itertools import permutations
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

if __package__:
    from .racer_context import collect as collect_racer_context, validated as validate_racer_context
    from .official_pay import fetch_official_pay
    from .venue_weather import fetch_weather, weather_at, VENUE_POINTS
    from .exhibition_bridge import available_rows, inject
    from .entry_exhibition_gate import validated_preview, summarize_gate
    from .venue_profiles import get_profile, adjust_weights as adjust_venue_weights
    from .interaction_scenarios import evaluate as evaluate_interactions, VERSION as INTERACTION_VERSION
    from .racer_course_tactics import profile as validate_tactics_profile, pairwise_note as tactic_pair
else:
    from racer_context import collect as collect_racer_context, validated as validate_racer_context
    from official_pay import fetch_official_pay
    from venue_weather import fetch_weather, weather_at, VENUE_POINTS
    from exhibition_bridge import available_rows, inject
    from entry_exhibition_gate import validated_preview, summarize_gate
    from venue_profiles import get_profile, adjust_weights as adjust_venue_weights
    from interaction_scenarios import evaluate as evaluate_interactions, VERSION as INTERACTION_VERSION
    from racer_course_tactics import profile as validate_tactics_profile, pairwise_note as tactic_pair

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
MAIN_MODEL = "tactical-outside-start-gap-v0.7-untrained"
MAIN_WAKE_MODEL = "tactical-outside-start-wake-v0.9-untrained"
WAKE_PROMOTION_DATE = date(2026, 10, 25)
MAIN_BRIDGE = Path(__file__).resolve().parent / "main_v07_bridge.js"
WAKE_BRIDGE = Path(__file__).resolve().parent / "main_v09_bridge.js"
FOUR_FACTOR_DATE = date(2026, 10, 27)
FOUR_FACTOR_MODEL = 'four-factor-v1.1-untrained'
HEAD_COVERAGE_MODEL = 'four-factor-v1.2-head-coverage-untrained'
POSTRACE_CONDITIONAL_MODEL = 'four-factor-v1.3-conditional-scenarios-untrained'
# Activation is a forward-time gate, not an assertion that older forecasts used v1.3.
POSTRACE_ACTIVATION_UTC = datetime.fromisoformat("2026-10-27T07:30:00+00:00")
VENUE_TACTICS_MODEL = 'four-factor-v1.4-venue-aware-23-untrained'
# Forward-only: 江戸川 excluded from venue tactics, prior snapshots immutable.
VENUE_TACTICS_ACTIVATION_UTC = datetime.fromisoformat("2026-10-27T09:30:00+00:00")
HEAD_COVERAGE_ROLLOUT = json.loads((Path(__file__).resolve().parents[1] / 'config/head-coverage-2026-10-27.json').read_text())
FOUR_FACTOR_BRIDGE = Path(__file__).resolve().parent / 'main_four_factor_bridge.js'
POINT_FREE_DATE = date(2026, 10, 28)
POINT_FREE_MODEL = 'four-factor-v1.5-point-free-untrained'
POINT_FREE_BRIDGE = Path(__file__).resolve().parent / 'main_point_free_bridge.js'
INTERACTION_MAIN_MODEL = 'four-factor-v1.7-interaction-inside-failure-untrained'
INTERACTION_MAIN_ACTIVATION_UTC = datetime.fromisoformat('2026-11-04T03:30:00+00:00')
VIRTUAL_BUDGET_YEN = 50_000
MIN_POINTS, MAX_POINTS = 4, 12
STAKE_UNIT_YEN = 1_000
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
    """Require six unambiguous, *unique* exhibition positions and measurements.

    A duplicate 2-course, fractional position or missing preview must NEVER
    be marked exhibition-confirmed. Entry changes must not be silently
    coerced into lane order. Exhibition F is valid but not rewarded for speed.
    """
    preview = race.get("preview")
    return validated_preview(preview) is not None


def select_exhibition_source(race: dict, research_row: dict | None, now: datetime,
                             venue_code: str, race_number: int):
    """Keep one complete source per race: live OpenAPI first, validated CSV fallback.

    The bridge itself enforces date, observed-time, and safe-cutoff constraints.
    This helper cannot make an incomplete preview exhibition-confirmed.
    """
    if preview_complete(race):
        # The OpenAPI preview was fetched in the current forecast run, unlike
        # retrospective research. Attribute it to the per-race processing clock;
        # never claim an unknown upstream publication time.
        cutoff = cutoff_of(race)
        if (now.tzinfo is None or cutoff is None
                or now.astimezone(JST) >= cutoff - timedelta(seconds=SAFE_MARGIN_SECONDS)):
            return race, None, "unavailable"
        captured = now.astimezone(UTC).isoformat()
        live = {**race, "_exhibition_origin": {
            "source": "BoatraceOpenAPI",
            "captured_at_utc": captured,
            "forecast_run_utc": captured,
            "captured_before_cutoff": True,
            "source_observation_time": "not_provided",
            "metrics": [],
        }}
        return live, None, "openapi"
    bridged, csv_origin = inject(race, research_row, now, venue_code, race_number)
    if csv_origin and preview_complete(bridged):
        return bridged, csv_origin, "boatracecsv"
    return race, None, "unavailable"


def numeric_exhibition_matches_snapshot(candidate: dict, snapshot: dict) -> bool:
    """Fail closed if ANY displayed six-boat input differs from frozen output.

    This is an input/output invariant, NOT proof that the new bets outperform
    baseline. Check before persisting; never reconstruct an old frozen version.
    """
    if snapshot.get("phase") != "exhibition" or not preview_complete(candidate):
        return False
    origin = candidate.get("_exhibition_origin") or {}
    if (origin.get("source") not in ("BoatraceOpenAPI", "BoatraceCSV")
            or origin.get("captured_before_cutoff") is not True):
        return False
    applied = snapshot.get("racers")
    preview = candidate["preview"]["racers"]
    if not isinstance(applied, list) or len(applied) != 6:
        return False
    for lane, saved in enumerate(applied, 1):
        if not isinstance(saved, dict) or saved.get("lane") != lane:
            return False
        source = preview[str(lane)]
        for input_key, output_key in (
                ("course_number", "course"),
                ("exhibition_time", "exhibition_time"),
                ("start_timing", "exhibition_st")):
            expected, observed = number(source.get(input_key)), number(saved.get(output_key))
            if (expected is None or observed is None
                    or abs(expected - observed) > 0.000001):
                return False
        for metric, boat_values in (candidate.get("_exhibition_original") or {}).items():
            if (not isinstance(boat_values, dict) or len(boat_values) != 6
                    or metric not in ("lap_time", "turn_time", "straight_time")):
                return False
            expected = number(boat_values.get(str(lane)))
            observed = number((saved.get("original_exhibition") or {}).get(metric))
            if (expected is None or observed is None
                    or abs(expected - observed) > 0.000001):
                return False
    return True


def numeric_exhibition_coverage(records: dict, day: str) -> dict:
    """Read-only per-venue outcome audit, never a new prediction or eligibility override."""
    grouped = {}
    totals = {
        "listed_races": 0, "verified_exhibition": 0, "baseline_or_unverified": 0,
        "six_boat_input_checked": 0, "openapi_source": 0,
        "csv_source": 0, "unknown_source": 0, "actual_ticket_changes": 0,
    }
    for rec in records.values():
        venue = rec["venue"]
        row = grouped.setdefault(venue, {key: 0 for key in totals})
        row["listed_races"] += 1
        versions = rec.get("versions") or []
        latest = versions[-1] if versions else None
        verified = bool(latest and summarize_gate(latest, day).get("final_eligible"))
        if verified:
            row["verified_exhibition"] += 1
            checked = bool((latest.get("exhibition_input_check") or {}).get(
                "verified_before_freeze"))
            row["six_boat_input_checked"] += int(checked)
            origin = (latest.get("exhibition_origin") or {}).get("source")
            source_key = (
                "openapi_source" if origin == "BoatraceOpenAPI" else
                "csv_source" if origin == "BoatraceCSV" else "unknown_source")
            row[source_key] += 1
            row["actual_ticket_changes"] += int(bool(
                (latest.get("exhibition_change") or {}).get("bets_changed")))
        else:
            row["baseline_or_unverified"] += 1
    for row in grouped.values():
        for key in totals:
            totals[key] += row[key]
    return {
        "scope": "immutable latest snapshots; pre-cutoff six-boat eligibility, not source availability",
        "total": totals,
        "by_venue": dict(sorted(grouped.items())),
        "note": "A score/order change is not a ticket/allocation change. Old frozen snapshots "
                "are never labeled input-checked retrospectively.",
    }


def valid_average_st(value) -> float | None:
    """0.00 / out-of-range average ST can be an unfilled source field.

    Neutralize rather than assuming an impossible persistent perfect start.
    This does not imply exhibition ST=0.00 is invalid.
    """
    v = number(value)
    return v if v is not None and .01 <= v <= .40 else None


def usable_exhibition_st(value) -> float | None:
    """Exhibition F (negative ST) is timing evidence, not a fast legal start."""
    v = number(value)
    return v if v is not None and 0 <= v <= .50 else None


def features(race: dict, phase: str) -> tuple[list[float], list[dict]]:
    runners = race["racers"]
    preview = race.get("preview") or {}
    prev_racers = preview.get("racers") or {}
    expo_times = [number((prev_racers.get(str(i)) or {}).get("exhibition_time"))
                  for i in range(1, 7)]
    if not all(t is not None and 5.0 <= t <= 10.0 for t in expo_times):
        expo_times = [None] * 6
    reference = min(t for t in expo_times if t is not None) if all(
        t is not None for t in expo_times) else None
    # A complete six-boat original-exhibition field is used only in test mode.
    # Individual missing boats must not create artificial rankings.
    original = race.get("_exhibition_original") or {} if phase == "exhibition" else {}
    valid_ranges = {"lap_time": (30, 50, .09), "turn_time": (4, 15, .15),
                    "straight_time": (5, 12, .12)}
    normalised = {}
    for key,(lower,upper,rate) in valid_ranges.items():
        values = [number((original.get(key) or {}).get(str(i))) for i in range(1,7)]
        if all(v is not None and lower <= v <= upper for v in values):
            normalised[key] = (values, sum(values)/6, rate)
    weights, detail = [] , []
    for i in range(1, 7):
        racer = runners[str(i)]
        pr = prev_racers.get(str(i)) or {}
        course = int(number(pr.get("course_number"), i)) if phase == "exhibition" else i
        course = max(1, min(6, course))
        win = number(racer.get("national_win_rate"), 4.5)
        motor = number(racer.get("motor_top_2_percent"), 30.0)
        measured_avg_st = valid_average_st(racer.get("average_start_timing"))
        avg_st = measured_avg_st if measured_avg_st is not None else .17
        f_count = number(racer.get("flying_count"), 0)
        score = COURSE[course - 1] * (1 + .11 * (win - 4.5)
                                     + .004 * (motor - 30)
                                     - .60 * (avg_st - .17))
        score *= 0.96 ** min(3, max(0, f_count))
        if phase == "exhibition" and reference is not None:
            expo = number(pr.get("exhibition_time"))
            est = usable_exhibition_st(pr.get("start_timing"))
            # Exhibition F is never rewarded as "an exceptionally quick start".
            score *= max(.75, min(1.23, 1 + .7 * (reference - expo)))
            if est is not None:
                score *= max(.90, min(1.10, 1 + .18 * (.16 - est)))
            for values, mean, rate in normalised.values():
                # Lower time = better within the same venue/race, conservative bounded gain.
                score *= max(.83, min(1.17, 1 + rate * (mean - values[i-1])))
        weights.append(max(.12, score))
        registration = number(racer.get("number"))
        detail.append({
            "lane": i,
            **({"racer_context": (race.get("_racer_context") or {}).get(str(i)),
                "racer_id": int(registration) if registration is not None and registration.is_integer() else None}
               if race.get("_racer_context") else {}),
            "name": str(racer.get("name", "")).strip(),
            "course": course,
            "national_win_rate": number(racer.get("national_win_rate")),
            "average_start_timing": measured_avg_st,
            "average_start_timing_source_value": number(racer.get("average_start_timing")),
            "average_start_timing_imputed": measured_avg_st is None,
            "motor_top_2_percent": number(racer.get("motor_top_2_percent")),
            "exhibition_st": number(pr.get("start_timing")) if phase == "exhibition" else None,
            "exhibition_time": number(pr.get("exhibition_time")) if phase == "exhibition" else None,
            "tilt": number(pr.get("tilt_adjustment")) if phase == "exhibition" else None,
            "relative_weight": round(max(.12, score), 5),
            "original_exhibition": {
                key: vals[i-1] for key, (vals, _, _) in normalised.items()
            } if phase == "exhibition" else {},
        })
    return weights, detail


def point_count(weights: list[float]) -> tuple[int, str, float, float]:
    """Choose 4–12 trifecta scenarios from *uncalibrated relative* head weights.

    All thresholds are provisional rules for controlled comparisons. These are
    not measured hit probabilities. Concentration and leader/runner-up gap
    decide how much 2nd/3rd-place branching to retain.
    """
    if len(weights) != 6 or any(not math.isfinite(x) or x <= 0 for x in weights):
        raise ValueError("Need six positive finite head weights")
    ordered = sorted(weights, reverse=True)
    total = sum(ordered)
    head_share = ordered[0] / total
    gap = (ordered[0] - ordered[1]) / total
    thresholds = [
        (.40, .14, 4), (.36, .10, 5), (.33, .07, 6),
        (.30, .05, 7), (.28, .04, 8), (.26, .025, 9),
        (.245, .015, 10), (.23, .010, 11),
    ]
    count = next((n for share, lead, n in thresholds
                  if head_share >= share and gap >= lead), MAX_POINTS)
    label = ("主導権が比較的明確・買い目を集中" if count <= 6 else
             "対抗ラインと2・3着の分岐を重視" if count <= 9 else
             "先頭争いが接近・展開分岐を広めに検証")
    reason = f"{label}（頭評価の相対重み {head_share:.1%}・次点差 {gap:.1%}、未校正）"
    return count, reason, head_share, gap


def combinations(weights: list[float]) -> list[tuple[str, float]]:
    total = sum(weights)
    count, _, _, _ = point_count(weights)
    ranked = []
    for a, b, c in permutations(range(6), 3):
        probability_like_weight = (weights[a] / total) * (weights[b] / (total - weights[a])) * (
            weights[c] / (total - weights[a] - weights[b]))
        ranked.append((f"{a+1}-{b+1}-{c+1}", probability_like_weight))
    ranked.sort(key=lambda item: (-item[1], item[0]))
    selected = ranked[:count]
    # With reasonably competitive second head, protect its best scenario rather
    # than allowing all 4–12 combinations to share the same leading boat.
    heads = {row[0][0] for row in selected}
    runner_up = sorted(enumerate(weights, start=1), key=lambda x: -x[1])[1]
    if len(heads) == 1 and runner_up[1] >= .62 * max(weights):
        alternative = next((row for row in ranked if row[0][0] == str(runner_up[0])), None)
        if alternative:
            selected[-1] = alternative
            selected.sort(key=lambda item: (-item[1], item[0]))
    return selected


def allocate_stakes(ranked: list[tuple[str, float]]) -> list[dict]:
    """Non-flat descending allocations in 1000-yen units, exactly ¥50,000."""
    count = len(ranked)
    if not MIN_POINTS <= count <= MAX_POINTS:
        raise ValueError("Selection must contain 4–12 unique trifectas")
    if len({x[0] for x in ranked}) != count:
        raise ValueError("Duplicate trifecta")
    budget_units = VIRTUAL_BUDGET_YEN // STAKE_UNIT_YEN
    residual_units = budget_units - count
    strengths = [max(0.0, score) ** .8 for _, score in ranked]
    denom = sum(strengths)
    if denom <= 0:
        raise ValueError("Invalid combination weights")
    quotas = [residual_units * strength / denom for strength in strengths]
    awarded = [int(math.floor(quota)) for quota in quotas]
    leftover = residual_units - sum(awarded)
    order = sorted(range(count), key=lambda i: (-(quotas[i] - awarded[i]), i))
    for i in order[:leftover]:
        awarded[i] += 1
    bets = [
        {"combination": combination, "virtual_yen": (1 + awarded[i]) * STAKE_UNIT_YEN}
        for i, (combination, _) in enumerate(ranked)
    ]
    assert sum(row["virtual_yen"] for row in bets) == VIRTUAL_BUDGET_YEN
    return bets

def weather_for_prediction(race: dict, nearby_forecast: dict | None) -> tuple[dict | None, dict | None]:
    """Return track observation and selected input with unambiguous provenance.

    A current source preview may have partial racecourse weather even while
    its 6 competitors' exhibitions are incomplete. Prefer track wind to nearby
    weather-grid estimates only if available *before cutoff*.
    """
    preview = race.get("preview")
    preview = preview if isinstance(preview, dict) else {}
    wind = number(preview.get("wind_speed"))
    wave = number(preview.get("wave_height"))
    observed = None
    if wind is not None or wave is not None:
        observed = {
            "wind_speed": wind,
            "wind_direction_number": number(preview.get("wind_direction_number")),
            "wave_height": wave,
            "weather_number": number(preview.get("weather_number")),
            "air_temperature": number(preview.get("air_temperature")),
            "water_temperature": number(preview.get("water_temperature")),
        }
    if observed and wind is not None and 0 <= wind <= 65:
        return observed, {
            **observed, "source": "boatrace_preview",
            "source_label": "展示時の場内観測（非公式API経由）",
            "site_observed": True,
            "source_note": "発走時の実測ではなく、取得時点の展示観測",
        }
    if nearby_forecast and number(nearby_forecast.get("wind_speed")) is not None:
        return observed, {
            **nearby_forecast,
            "wave_height": observed.get("wave_height") if observed else None,
            "wave_source": "boatrace_preview" if observed and observed.get("wave_height") is not None else "unavailable",
        }
    return observed, None


def condition_weights(weights: list[float], weather: dict | None) -> tuple[list[float], dict]:
    """Conservative, provisional broadening in rough conditions.

    NO per-course headwind claims: wind bearing relative to each racecourse
    straight is unverified. No fitted accuracy gain is claimed. Only the
    concentration of relative head weights is flattened slightly for
    strong wind / high waves; later A/B results must validate this.
    """
    if not weather:
        return weights, {
            "applied": False, "why": "気象値未取得・既存の相対評価を維持",
            "uncertainty_exponent": 1.0,
        }
    speed = number(weather.get("wind_speed"))
    gust = number(weather.get("wind_gust"))
    wave = number(weather.get("wave_height"))
    alpha = 1.0
    signals = []
    if speed is not None and speed >= 8:
        alpha *= .82
        signals.append(f"風速{speed:g}m/s・強風")
    elif speed is not None and speed >= 6:
        alpha *= .87
        signals.append(f"風速{speed:g}m/s")
    elif speed is not None and speed >= 4:
        alpha *= .93
        signals.append(f"風速{speed:g}m/s")
    if gust is not None and gust >= 12:
        alpha *= .95
        signals.append(f"突風{gust:g}m/s")
    if wave is not None and wave >= 8:
        alpha *= .93
        signals.append(f"波高{wave:g}cm")
    elif wave is not None and wave >= 4:
        alpha *= .96
        signals.append(f"波高{wave:g}cm")
    alpha = max(.77, alpha)
    return [max(.06, value) ** alpha for value in weights], {
        "applied": alpha < .999,
        "why": "・".join(signals) + "：頭候補の確信度を抑えて展開分岐を試験評価"
        if signals else "気象値あり・通常条件のため相対評価を維持",
        "uncertainty_exponent": round(alpha, 3),
        "method": "weather-uncertainty-shrinkage-experimental-untrained-v0",
        "limitation": "風向からコース有利不利を機械的に推定しない。効果は未検証",
    }


def promoted_v07(venue: str, phase: str, racers: list[dict],
                 profile: dict | None, weather: dict | None,
                 frozen_at_utc: str) -> dict:
    """Invoke the exact browser v0.7 engine to avoid divergent implementations.

    This is a strict, fail-closed adapter. Never silently revert to the legacy
    model (which would mislabel the primary 3-trifecta selection). All inputs
    come from the source race and weather already collected BEFORE cutoff.
    """
    inputs = {
        "venue": venue, "phase": phase, "racers": [
            {key: r.get(key) for key in (
                "lane", "course", "national_win_rate",
                "motor_top_2_percent", "average_start_timing",
                "exhibition_st", "exhibition_time", "original_exhibition"
            )} for r in racers
        ],
        "venue_profile": profile, "weather_used": weather,
        "frozen_at_utc": frozen_at_utc,
    }
    try:
        result = subprocess.run(
            ["node", str(MAIN_BRIDGE)], input=json.dumps(inputs, ensure_ascii=False),
            text=True, capture_output=True, timeout=12, check=True
        )
        answer = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        raise RuntimeError("v0.7 primary unavailable: fail closed, do not freeze legacy") from exc
    bets = answer.get("bets")
    if answer.get("model_version") != MAIN_MODEL or not isinstance(bets, list):
        raise ValueError("Wrong model version in primary bridge")
    if not MIN_POINTS <= len(bets) <= MAX_POINTS or len({
        b.get("combination") for b in bets
    }) != len(bets) or any(
        not isinstance(b.get("virtual_yen"), int)
        or b["virtual_yen"] < STAKE_UNIT_YEN
        or b["virtual_yen"] % STAKE_UNIT_YEN
        or not isinstance(b.get("combination"), str)
        or len(b["combination"].split("-")) != 3
        or len(set(b["combination"].split("-"))) != 3
        or any(x not in "123456" for x in b["combination"].split("-"))
        for b in bets
    ) or sum(b["virtual_yen"] for b in bets) != VIRTUAL_BUDGET_YEN:
        raise ValueError("Invalid primary allocation: no frozen forecast written")
    return answer


def promoted_v09(venue: str, phase: str, racers: list[dict],
                 profile: dict | None, weather: dict | None,
                 frozen_at_utc: str, four_factor: bool = False, head_coverage: bool = False,
                 postrace_conditional: bool = False, venue_tactics: bool = False, point_free: bool = False,
                 role_skill_trial: bool = False,
                 role_skill_preserve_heads: bool = False,
                 venue_motor_exhibition_trial: bool = False) -> dict:
    """Invoke one explicit model identity; never fall back on bridge failure."""
    inputs = {
        "venue": venue, "phase": phase,
        "racers": [{key: r.get(key) for key in (
            "lane", "course", "national_win_rate", "motor_top_2_percent",
            "average_start_timing", "exhibition_st", "exhibition_time",
            "original_exhibition", "racer_context"
        )} for r in racers],
        "venue_profile": profile, "weather_used": weather,
        "frozen_at_utc": frozen_at_utc,
        "head_coverage_trial": head_coverage,
        "postrace_conditional_trial": postrace_conditional,
        "venue_tactics_trial": venue_tactics,
        "role_skill_shadow_trial": bool(role_skill_trial and four_factor),
        "role_skill_head_preserved_trial": bool(role_skill_trial and four_factor
                                                and role_skill_preserve_heads),
        "venue_motor_exhibition_shadow_trial": bool(venue_motor_exhibition_trial and four_factor),
    }
    try:
        job = subprocess.run(
            ["node", str(POINT_FREE_BRIDGE if four_factor and point_free else FOUR_FACTOR_BRIDGE if four_factor else WAKE_BRIDGE)], input=json.dumps(inputs, ensure_ascii=False),
            text=True, capture_output=True, timeout=12, check=True
        )
        answer = json.loads(job.stdout)
    except (OSError, ValueError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        raise RuntimeError("v0.9 bridge unavailable: fail closed, no fallback freeze") from exc
    bets = answer.get("bets")
    expected = (POINT_FREE_MODEL if four_factor and point_free else VENUE_TACTICS_MODEL if four_factor and venue_tactics else
                 POSTRACE_CONDITIONAL_MODEL if four_factor and postrace_conditional else
                HEAD_COVERAGE_MODEL if four_factor and head_coverage else
                FOUR_FACTOR_MODEL if four_factor else MAIN_WAKE_MODEL)
    if answer.get("model_version") != expected or not isinstance(bets, list):
        raise ValueError("Wrong new main bridge model identity")
    bounded_max = 20 if four_factor and datetime.fromisoformat(frozen_at_utc).astimezone(JST).date() >= date(2026, 10, 29) else MAX_POINTS
    min_points, max_points, unit = (1, 120, 100) if expected == POINT_FREE_MODEL else (MIN_POINTS, bounded_max, STAKE_UNIT_YEN)
    if not min_points <= len(bets) <= max_points or len({
        b.get("combination") for b in bets
    }) != len(bets) or any(
        not isinstance(b.get("virtual_yen"), int)
        or b["virtual_yen"] < unit
        or b["virtual_yen"] % unit
        or not isinstance(b.get("combination"), str)
        or len(b["combination"].split("-")) != 3
        or len(set(b["combination"].split("-"))) != 3
        or any(x not in "123456" for x in b["combination"].split("-"))
        for b in bets
    ) or sum(b["virtual_yen"] for b in bets) != VIRTUAL_BUDGET_YEN:
        raise ValueError("Invalid v0.9 ticket allocation")
    if not answer.get("wake_v09", {}).get("pre_cutoff_only"):
        raise ValueError("Wake provenance missing")
    return answer


def head_coverage_eligible(record: dict, key: str, now: datetime, cutoff: datetime) -> bool:
    """Explicit pending cohort; never promote an existing exhibition prediction."""
    rollout = HEAD_COVERAGE_ROLLOUT
    if (cutoff.date().isoformat() != rollout['event_date'] or key not in rollout['targets']
            or now < datetime.fromisoformat(rollout['created_at_utc'])
            or now >= cutoff - timedelta(seconds=180)):
        return False
    versions = record.get('versions') or []
    if any(v.get('model_version') == HEAD_COVERAGE_MODEL for v in versions):
        return True
    return bool(versions) and all(v.get('phase') == 'baseline' for v in versions)



def interaction_primary(previous: dict, racers: list[dict], frozen_at: str, cutoff: datetime,
                        tactics: dict | None = None,
                        scored_weights: list[float] | None = None) -> tuple[list[dict], dict]:
    """Forward-only main tickets. Existing main forecast is an A/B control."""
    if scored_weights is not None and (len(scored_weights) != 6 or
            any(number(value) is None or value <= 0 for value in scored_weights)):
        raise ValueError("Need six positive venue/weather adjusted weights")
    supplied = []
    for r in racers:
        relative = number(scored_weights[r["lane"] - 1] if scored_weights is not None
                          else r.get("relative_weight"))
        if relative is None or relative <= 0:
            raise ValueError("Missing pre-cutoff racer weight")
        supplied.append({"lane": r["lane"], "strength": min(100., max(.01, relative * 20)),
                         "start_mean": r.get("average_start_timing"),
                         "exhibition_time": r.get("exhibition_time")})
    result = evaluate_interactions(supplied, captured_at_utc=frozen_at,
                                   cutoff_at_utc=cutoff.isoformat())
    count = len(previous["bets"])
    if not (4 <= count <= 20):
        raise ValueError("Unsupported previous main point count")
    # This option is engaged ONLY with independently validated, historical
    # course-by-racer evidence. No data => exactly the prior primary model.
    tactics_report = {"status": "UNAVAILABLE", "applied": False}
    ranked = result["top_combinations"]
    if tactics is not None:
        try:
            if not isinstance(tactics, dict) or set(tactics) != {"profiles", "reference"}:
                raise ValueError("Invalid tactics envelope")
            reference = tactics["reference"]
            # Training reference rates must also be frozen before this race.
            if not isinstance(reference, dict) or not isinstance(reference.get("observed_until_utc"), str):
                raise ValueError("Missing historical reference provenance")
            reference_stamp = datetime.fromisoformat(reference["observed_until_utc"].replace("Z", "+00:00"))
            if reference_stamp.tzinfo is None or reference_stamp >= cutoff:
                raise ValueError("Reference rates include post-cutoff observations")
            ref_sha = reference.get("source_sha256")
            if not isinstance(ref_sha, str) or len(ref_sha) != 64 or any(ch not in "0123456789abcdef" for ch in ref_sha):
                raise ValueError("Invalid historical reference source SHA")
            rows = tactics["profiles"]
            if not isinstance(rows, dict) or set(rows) != set(str(i) for i in range(1, 7)):
                raise ValueError("Incomplete six-racer tactics data")
            validated = {}
            for racer in racers:
                ident = racer.get("racer_id")
                course = racer.get("course")
                if type(ident) is not int or type(course) is not int:
                    raise ValueError("Missing racer ID or actual course")
                validated[racer["lane"]] = validate_tactics_profile(
                    rows[str(racer["lane"])], tactics["reference"],
                    target_racer_id=ident, course=course,
                    cutoff_at_utc=cutoff.isoformat())
            if not all(p["status"] == "RESEARCH_READY" for p in validated.values()):
                raise ValueError("Insufficient past starts")
            # A bounded tie-breaker for ranked combinations, not a measured
            # probability. Explicitly retain identical point-count comparison.
            rescored = []
            for entry in ranked:
                first, second, third = (int(i) for i in entry["combination"].split("-"))
                attack = validated[first]
                if first == 1:
                    candidate = attack["technique_per_start"]["escape"]
                else:
                    candidate = max(attack["technique_per_start"][k] for k in ("makuri", "makurizashi", "sashi"))
                # Distinguish attack skill from the inside defender's demonstrated
                # vulnerability. "Marking" intent cannot be read from these stats.
                defender_delta = 0.0
                if first != 1:
                    inner_course = attack["course"] - 1
                    inside = next((v for v in validated.values() if v["course"] == inner_course), None)
                    tactic = max(("makuri", "makurizashi", "sashi"),
                                key=lambda k: attack["technique_per_start"][k])
                    exposure = "makurare" if tactic == "makuri" else "sasare"
                    if inside and inside["defense_opportunities"].get(exposure, 0) >= 20:
                        baseline_rate = tactics["reference"]["defense"][exposure]
                        defender_delta = inside["defense_per_opportunity"][exposure] - baseline_rate
                # Bounded uncalibrated change; unchanged if historical data missing.
                adjustment = max(-.12, min(.12, (candidate - .10) * .4 + defender_delta * .1))
                rescored.append({"combination": entry["combination"],
                                 "relative_score": entry["relative_score"] * (1 + adjustment)})
            ranked = sorted(rescored, key=lambda x: (-x["relative_score"], x["combination"]))
            tactics_report = {"status": "APPLIED_UNCALIBRATED", "applied": True,
                              "source_sha256": {str(k): v["source_sha256"] for k, v in validated.items()},
                              "racer_courses": {str(k): v["course"] for k, v in validated.items()},
                              "max_abs_weight_change": .12,
                              "method": "bounded_pre_cutoff_tactic_tiebreaker"}
        except (KeyError, TypeError, ValueError) as exc:
            tactics_report = {"status": "REJECTED", "applied": False, "reason": str(exc)}
    selected = list(ranked[:count])
    # A single mixture ranking can erase a plausible 1-outside-top3 path
    # even when its aggregate relative mass is material. Preserve ONE
    # candidate only if it is not dramatically weaker than the cutoff bet.
    # These are research coverage thresholds, not calibrated probabilities.
    inside_out_mass = result["course1_outside_top3_relative_mass"]
    selected_without_one = sum("1" not in x["combination"].split("-") for x in selected)
    excluded_candidates = [x for x in ranked if "1" not in x["combination"].split("-")]
    conditional_coverage = bool(
        inside_out_mass >= .25 and selected_without_one == 0 and excluded_candidates
        and excluded_candidates[0]["relative_score"] >= .55 * selected[-1]["relative_score"])
    if conditional_coverage:
        selected[-1] = excluded_candidates[0]
        selected.sort(key=lambda x: (-x["relative_score"], x["combination"]))
    if len(selected) != count:
        raise ValueError("Insufficient scenarios")
    units = 50 - count
    scores = [max(0., x["relative_score"]) for x in selected]
    total = sum(scores)
    if total <= 0:
        raise ValueError("Invalid scenario weights")
    quotas = [units * x / total for x in scores]
    base = [int(x) for x in quotas]
    remain = units - sum(base)
    for i in sorted(range(count), key=lambda i: (-(quotas[i] - base[i]), i))[:remain]:
        base[i] += 1
    bets = [{"combination": x["combination"], "virtual_yen": 1000 * (1 + base[i])}
            for i, x in enumerate(selected)]
    if sum(x["virtual_yen"] for x in bets) != VIRTUAL_BUDGET_YEN:
        raise ValueError("Scenario stake allocation failed")
    # The old bridge's head shares describe old bets, not this mixture.
    # Recompute all six first-place shares from the 120 ordered outcomes.
    head_mass = {lane: 0.0 for lane in range(1, 7)}
    for entry in result["top_combinations"]:
        head_mass[int(entry["combination"].split("-")[0])] += entry["relative_score"]
    total_mass = sum(head_mass.values())
    if total_mass <= 0:
        raise ValueError("Invalid first-place marginal")
    new_head_shares = [
        {"course": r["course"], "lane": r["lane"],
         "relative_share": round(head_mass[r["lane"]] / total_mass, 4),
         "tactic": "条件付き5展開・未校正"}
        for r in racers
    ]
    meta = {"version": INTERACTION_VERSION, "uncalibrated": True,
            "new_head_course_shares": new_head_shares,
            "previous_head_course_shares": previous.get("head_course_shares"),
            "course1_outside_top3_relative_mass": inside_out_mass,
            "course1_outside_top3_by_path": result["course1_outside_top3_by_path"],
            "uses_venue_weather_adjusted_base": scored_weights is not None,
            "course1_outside_top3_selected": sum("1" not in b["combination"].split("-") for b in bets),
            "conditional_coverage_applied": conditional_coverage,
            "conditional_coverage_rule": "relative_mass>=.25, candidate>=.55*last_selected",
            "racer_course_tactics": tactics_report,
            "scenario_assumptions": result["scenario_assumptions"],
            "conditional_places_by_head": result["conditional_places_by_head"],
            "conditional_places_are_uncalibrated": True,
            "old_main_model_version": previous["model_version"],
            "old_main_bets": previous["bets"],
            "comparison": "same input, point count, 50000 virtual yen",
            "result_data_used": False}
    return bets, meta


def prediction(race: dict, venue: str, race_number: int, phase: str,
               now: datetime, source_url: str, nearby_weather: dict | None = None) -> dict:
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
    observed, selected_weather = weather_for_prediction(race, nearby_weather)
    # Historical venue rates are weak trial priors, not fixed win probabilities.
    venue_code = next((code for code, name in VENUES.items() if name == venue), None)
    venue_weights, venue_adjustment = (
        adjust_venue_weights(weights, racers, venue_code, selected_weather)
        if venue_code else (weights, {"applied": False, "reason": "場コード不明・補正なし"}))
    # Weather counterfactual retains the SAME venue profile for fair A/B.
    control_bets = allocate_stakes(combinations(venue_weights))
    weathered, weather_adjustment = condition_weights(venue_weights, selected_weather)
    ranked = combinations(weathered)
    bets = allocate_stakes(ranked)
    count, reason, concentration, gap = point_count(weathered)
    if weather_adjustment['applied']:
        reason += ' ／ 気象補正試験：' + weather_adjustment['why']
    # Preserve the previous canonical Python prediction as a deterministic
    # same-time SHADOW control. It does not generate a second official stake.
    legacy_name = ("heuristic-0.6-csv-exhibition-test-untrained"
                   if phase == "exhibition" and race.get("_exhibition_origin")
                   else "heuristic-0.7-venue-priors-test-untrained")
    frozen_at = now.astimezone(UTC).isoformat()
    legacy_control = {
        "model_version": legacy_name,
        "bets": bets,
        "point_count": len(bets),
        "point_reason": reason,
        "frozen_at_utc": frozen_at,
        "model_role": "shadow_validation",
        "source_note": "Same pre-cutoff input, original Python heuristic; no hindsight",
    }
    if selected_weather:
        legacy_control["weather_ab"] = {
            "control_model": "old_heuristic_without_weather",
            "control_bets": control_bets,
            "weather_bets": bets,
            "generated_pre_cutoff": True,
            "scope": "old_shadow_only_never_count_as_primary_weather_ab",
        }
    legacy_control["sha256"] = stable_hash(legacy_control)
    profile = get_profile(venue_code) if venue_code else None
    four_factor = cutoff.date() >= FOUR_FACTOR_DATE
    postrace_active = four_factor and now.astimezone(UTC) >= POSTRACE_ACTIVATION_UTC
    venue_active = postrace_active and venue != "江戸川" and now.astimezone(UTC) >= VENUE_TACTICS_ACTIVATION_UTC
    point_free_active = cutoff.date() == POINT_FREE_DATE and now.astimezone(JST).date() == POINT_FREE_DATE
    role_skill_active = four_factor and cutoff.date() >= date(2026, 10, 31) and now.astimezone(JST).date() >= date(2026, 10, 31)
    motor_exhibition_shadow_active = (four_factor and phase == "exhibition"
                                      and cutoff.date() >= date(2026, 11, 2)
                                      and now.astimezone(JST).date() >= date(2026, 11, 2))
    new_primary = cutoff.date() >= WAKE_PROMOTION_DATE
    if new_primary:
        same_time_old = (promoted_v09(venue, phase, racers, profile, selected_weather, frozen_at) if four_factor else
                         promoted_v07(venue, phase, racers, profile, selected_weather, frozen_at))
        legacy_control = {
            "model_version": same_time_old["model_version"],
            "bets": same_time_old["bets"],
            "point_count": len(same_time_old["bets"]),
            "frozen_at_utc": frozen_at,
            "model_role": "shadow_validation",
            "source_note": ("v0.9 previous main frozen at same pre-cutoff instant; no result" if four_factor else
                            "v0.7 old main frozen at same pre-cutoff instant; no result"),
        }
        legacy_control["sha256"] = stable_hash(legacy_control)
        promoted = promoted_v09(venue, phase, racers, profile, selected_weather, frozen_at, four_factor=four_factor,
                                head_coverage=bool(race.get("_head_coverage_trial")) and not postrace_active,
                                postrace_conditional=postrace_active and not venue_active,
                                venue_tactics=venue_active, point_free=point_free_active,
                                role_skill_trial=role_skill_active,
                                role_skill_preserve_heads=(role_skill_active
                                    and cutoff.date() >= date(2026, 11, 2)
                                    and now.astimezone(JST).date() >= date(2026, 11, 2)),
                                venue_motor_exhibition_trial=motor_exhibition_shadow_active)
        chosen_model = promoted["model_version"]
    else:
        promoted = promoted_v07(venue, phase, racers, profile, selected_weather, frozen_at)
        chosen_model = MAIN_MODEL
    bets = promoted["bets"]
    interaction_active = (four_factor and venue != "江戸川"
                          and now.astimezone(UTC) >= INTERACTION_MAIN_ACTIVATION_UTC
                          and cutoff.astimezone(UTC) > INTERACTION_MAIN_ACTIVATION_UTC)
    interaction_meta = None
    if interaction_active:
        bets, interaction_meta = interaction_primary(promoted, racers, frozen_at, cutoff,
                                                      tactics=race.get("_course_tactics"),
                                                      scored_weights=weathered)
        chosen_model = INTERACTION_MAIN_MODEL
    count = len(bets)
    shares = interaction_meta["new_head_course_shares"] if interaction_meta else promoted["head_course_shares"]
    concentration = max(x["relative_share"] for x in shares)
    top_two = sorted((x["relative_share"] for x in shares), reverse=True)
    gap = top_two[0] - top_two[1]
    reason = ("6艇連動＋平均ST／展示ST＋1M・2M引き波回避の着順分岐"
              if new_primary else
              "6艇連動＋平均ST／展示STと内艇の先行差による着順分岐")
    reason += "（4〜12点・未訓練・確率未校正）"
    top_combo = bets[0]["combination"].split("-")
    leader = racers[int(top_combo[0]) - 1]
    follower = racers[int(top_combo[1]) - 1]
    weather = observed
    if four_factor:
        reason = "選手60・モーター25・展示10・気象5の基礎倍率＋2・3着の全艇評価（追走固定なし・試験・未校正）"
        if chosen_model == HEAD_COVERAGE_MODEL:
            reason += "／頭候補保持・点数維持の試験修正"
        if point_free_active:
            reason = "点数枠なしv1.5：組合せの条件付き評価で採否を決め、点数・100円単位の仮想配分を後から算出（試験・未校正）"
        if chosen_model == POSTRACE_CONDITIONAL_MODEL:
            reason += "／展示タイム突出・外枠追走・内残りの条件付き試験（確率未校正）"
        if chosen_model == VENUE_TACTICS_MODEL:
            reason += "／23場別の決まり手構成と実進入・合法STに基づく着順連動v1.4（未校正）"
        if interaction_active:
            reason = ("艇間連動v1.7：コース・ST・展示の二重計上を除去し、"
                      "攻め成功・抵抗・攻め流れ・1号艇着外の5展開を評価（未校正）")
    body = {
        "model_version": chosen_model,
        **({"interaction_primary": interaction_meta} if interaction_meta else {}),
        **({"role_skill_shadow": promoted["role_skill_shadow"]} if promoted.get("role_skill_shadow") else {}),
        **({"venue_motor_exhibition_shadow": promoted["venue_motor_exhibition_shadow"]}
           if promoted.get("venue_motor_exhibition_shadow") else {}),
        **({"point_free_control": promoted["point_free_control"],
            "point_free_provenance": promoted["point_free_provenance"]} if point_free_active else {}),
        **({"head_coverage_control": promoted["head_coverage_control"]} if promoted.get("head_coverage_control") else {}),
        **({"venue_tactics_v2": promoted["venue_tactics_v2"],
            "venue_tactics_ab": promoted["venue_tactics_ab"]}
           if chosen_model in (VENUE_TACTICS_MODEL, POINT_FREE_MODEL) else {}),
        **({"postrace_conditional_v13": promoted["postrace_conditional_v13"],
            "postrace_conditional_control": promoted["postrace_conditional_control"]}
           if chosen_model in (POSTRACE_CONDITIONAL_MODEL, VENUE_TACTICS_MODEL, POINT_FREE_MODEL) else {}),
        **({"four_factor": promoted["four_factor"],
            "venue_surface_v1": promoted.get("venue_surface_v1"),
            "venue_surface_ab": promoted.get("venue_surface_ab")} if four_factor else {}),
        "model_role": "main",
        "legacy_control": legacy_control,
        "start_v07": promoted["start_v07"],
        **({"wake_v09": promoted["wake_v09"],
            "primary_promotion_date_jst": (FOUR_FACTOR_DATE if four_factor else WAKE_PROMOTION_DATE).isoformat(),
            "primary_model_ab": ("v1.7 corrected inside-survival scenario vs previous main, same pre-cutoff inputs, point count and 50000 yen" if interaction_active else "v1.5 point-free selection vs same-input previous primary; same 50000 budget" if point_free_active else "v1.4 venue-aware trial vs same-input v1.3 control and no-tactics ablation" if venue_active else
                                  "v1.3 forward trial vs v1.2 matched same-input control, with v0.9 legacy" if postrace_active else
                                 "four-factor primary vs same-time frozen v0.9 control") if four_factor else "v0.9 primary vs same-time frozen v0.7 control"}
           if new_primary else {}),
        "coupled_v06": promoted["coupled_v06"],
        "head_course_shares": shares,
        "role_coverage": promoted["role_coverage"],
        "role_changes": promoted["role_changes"],
        "relative_scores_uncalibrated": True,
        "exhibition_origin": race.get("_exhibition_origin") if phase == "exhibition" else None,
        "data_quality": {
            "average_start_timing_imputed_count": sum(
                bool(r.get("average_start_timing_imputed")) for r in racers
            ),
            "exhibition_f_count": sum(
                isinstance(r.get("exhibition_st"), (int, float)) and
                r["exhibition_st"] < 0 for r in racers
            ),
            "original_exhibition_metrics": list((race.get("_exhibition_original") or {}).keys())
                  if phase == "exhibition" else [],
            "motor_zero_percent_count": sum(
                r.get("motor_top_2_percent") == 0 for r in racers
            ),
            "notes": "平均STの0.00は中立補完、展示Fは速いSTとして加点しない",
        },
        "point_count": count,
        "point_reason": reason,
        "head_weight_concentration": round(concentration, 4),
        "head_weight_gap": round(gap, 4),
        "phase": phase,
        "venue": venue,
        "race": race_number,
        "cutoff_jst": cutoff.strftime("%H:%M"),
        "cutoff_iso_jst": cutoff.isoformat(),
        "frozen_at_utc": frozen_at,
        "source_url": source_url,
        "scenario": (("イン残存／イン着外の両分岐を評価：先頭候補"
                      + str(leader["lane"]) + "号艇、対抗" + str(follower["lane"]) + "号艇")
                     if interaction_active else
                     f"{leader['lane']}号艇{leader['name']}中心・"
                     f"{follower['lane']}号艇{follower['name']}の残存を検証"
                     + ("（展示数値を参照）" if phase == "exhibition" else "（展示前仮説）")),
        "bets": bets,
        "racers": racers,
        "weather_observed": weather,
        "venue_profile": profile,
        "venue_adjustment": venue_adjustment,
        "weather_used": selected_weather,
        "weather_adjustment": weather_adjustment,
        # Legacy weather A/B used the previous heuristic and cannot be
        # mistaken for a v0.7 weather ablation. Keep it INSIDE the old shadow.
        "weather_ab": None,
        "evidence": ("展示・場内気象あり" if weather and selected_weather and selected_weather.get("site_observed") else
                     "近隣予報（現地実測ではない）" if selected_weather else
                     "気象未取得") + ("・展示あり" if phase == "exhibition" else "・展示前"),
        "classification": "WATCH",  # No validated edge or live odds; never BUY automatically.
    }
    return {**body, "sha256": stable_hash(body)}


def context_quality(racers: list[dict]) -> int:
    fields = {"national_top3", "local_win", "local_top3", "motor_top3",
              "frame_win", "frame_st", "frame_start_order"}
    return sum(number(value) is not None for r in racers
               for key, value in (((r.get("racer_context") or {}).get("values") or {}).items())
               if key in fields)


def safe_to_append_pre_cutoff(snapshot: dict, cutoff: datetime, margin_seconds: int,
                              observed_now: datetime) -> bool:
    """Fail closed if a nationwide prediction finished after the safe cutoff.

    A job can start before cutoff and spend time inside the Node bridge. The
    initial per-race clock is not sufficient to authorize appending its result.
    The frozen timestamp AND the fresh completion clock must be safe.
    """
    try:
        frozen = datetime.fromisoformat(snapshot["frozen_at_utc"])
        if frozen.tzinfo is None or observed_now.tzinfo is None:
            return False
        limit = cutoff - timedelta(seconds=margin_seconds)
        return frozen < limit and observed_now < limit
    except (KeyError, ValueError, TypeError, AttributeError):
        return False


def build(existing: dict | None, payload: dict, now: datetime, source_url: str,
          weather_by_venue: dict | None = None, exhibition_rows: dict | None = None,
          enforce_wall_clock: bool = False, racer_context_rows: dict | None = None,
          tactics_rows: dict | None = None) -> tuple[dict, dict, dict]:
    if now.tzinfo is None:
        raise ValueError("Timezone-aware now is mandatory")
    local_day = now.astimezone(JST).date().isoformat()
    ledger = existing if isinstance(existing, dict) and existing.get("event_date") == local_day else {
        "event_date": local_day, "race_records": {},
        "created_at_utc": now.astimezone(UTC).isoformat()
    }
    records = ledger["race_records"]
    venues_seen = set()
    weather_by_venue = weather_by_venue or {}
    new_baseline, new_exhibition, revised_exhibition, changed_exhibition = 0, 0, 0, 0
    rejected_exhibition_input_mismatch = 0
    new_model_upgrades = 0
    exhibition_rows = exhibition_rows or {}
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
            nearby = weather_at(weather_by_venue.get(venue_code), cutoff)
            # Actual production per-race clock: a large nationwide Node batch
            # must NEVER treat the timestamp from initial collection as current.
            # Synthetic test fixtures explicitly leave this safeguard disabled.
            runtime_now = datetime.now(UTC) if enforce_wall_clock else now
            margin = max(SAFE_MARGIN_SECONDS, 180) if enforce_wall_clock else SAFE_MARGIN_SECONDS
            if cutoff.date() >= FOUR_FACTOR_DATE and valid_entrants(race):
                code = f"{local_day.replace('-', '')}{int(venue_code):02d}{n:02d}"
                context = (racer_context_rows or {}).get(code) or {}
                race = {**race, "_racer_context": {
                    str(i): validate_racer_context(context.get(i), race["racers"][str(i)], i,
                                                   runtime_now, cutoff.date()) for i in range(1, 7)
                }}
            postrace_active = cutoff.date() >= FOUR_FACTOR_DATE and runtime_now.astimezone(UTC) >= POSTRACE_ACTIVATION_UTC
            venue_active = postrace_active and VENUES[venue_code] != '江戸川' and runtime_now.astimezone(UTC) >= VENUE_TACTICS_ACTIVATION_UTC
            coverage_active = head_coverage_eligible(record, key, runtime_now, cutoff) and not postrace_active
            race = {**race, "_head_coverage_trial": coverage_active,
                    "_course_tactics": (tactics_rows or {}).get(f"{local_day.replace('-', '')}{int(venue_code):02d}{n:02d}")}
            point_free_active = cutoff.date() == POINT_FREE_DATE and runtime_now.astimezone(JST).date() == POINT_FREE_DATE
            interaction_active = (cutoff.date() >= FOUR_FACTOR_DATE and VENUES[venue_code] != "江戸川"
                                  and runtime_now.astimezone(UTC) >= INTERACTION_MAIN_ACTIVATION_UTC
                                  and cutoff.astimezone(UTC) > INTERACTION_MAIN_ACTIVATION_UTC)
            expected_main = (INTERACTION_MAIN_MODEL if interaction_active else
                             POINT_FREE_MODEL if point_free_active else VENUE_TACTICS_MODEL if venue_active else
                             POSTRACE_CONDITIONAL_MODEL if postrace_active else
                             HEAD_COVERAGE_MODEL if coverage_active else
                             FOUR_FACTOR_MODEL if cutoff.date() >= FOUR_FACTOR_DATE else MAIN_WAKE_MODEL)
            if runtime_now.astimezone(JST) < cutoff - timedelta(seconds=margin) and valid_entrants(race):
                if "baseline" not in phases:
                    baseline = prediction(race, VENUES[venue_code], n,
                                          "baseline", runtime_now, source_url, nearby)
                    completed_at = datetime.now(UTC) if enforce_wall_clock else now
                    if not safe_to_append_pre_cutoff(baseline, cutoff, margin, completed_at):
                        continue  # Historical baseline remains untouched; never backdate.
                    record["versions"].append(baseline)
                    new_baseline += 1
                code = f"{local_day.replace('-', '')}{int(venue_code):02d}{n:02d}"
                candidate, selected_csv_origin, selected_source = select_exhibition_source(
                    race, exhibition_rows.get(code), runtime_now, venue_code, n)
                candidate = {**candidate, "_head_coverage_trial": coverage_active}
                preview_ready = selected_source != "unavailable"
                existing_exhibition = [v for v in record["versions"] if v["phase"] == "exhibition"]
                previous_csv_time = (existing_exhibition[-1].get("exhibition_origin") or {}).get("observed_at_jst") if existing_exhibition else None
                previous_measurement = (existing_exhibition[-1].get("exhibition_origin") or {}).get("measurement_sha256") if existing_exhibition else None
                changed_measurement = bool(selected_csv_origin
                    and selected_csv_origin.get("measurement_sha256")
                    and selected_csv_origin["measurement_sha256"] != previous_measurement)
                # An OpenAPI preview may change after the first valid capture.
                # Compare the actual six-boat source input against the most
                # recently frozen version, not just a CSV timestamp.
                live_measurements_changed = bool(
                    selected_source == "openapi" and existing_exhibition
                    and not numeric_exhibition_matches_snapshot(candidate, existing_exhibition[-1]))
                revision = bool(
                    existing_exhibition and len(existing_exhibition) < 3
                    and ((selected_csv_origin
                          and (changed_measurement or not previous_csv_time
                               or previous_csv_time < selected_csv_origin["observed_at_jst"]))
                         or live_measurements_changed)
                )
                if preview_ready and ("exhibition" not in phases or revision):
                    origin_url = selected_csv_origin and "https://boatracecsv.github.io/docs/data/previews.html" or source_url
                    new = prediction(candidate, VENUES[venue_code], n,
                                     "exhibition", (datetime.now(UTC) if enforce_wall_clock else now), origin_url, nearby)
                    completed_at = datetime.now(UTC) if enforce_wall_clock else now
                    if not safe_to_append_pre_cutoff(new, cutoff, margin, completed_at):
                        continue  # Keep the prior pre-cutoff version; no late exhibition.
                    if not numeric_exhibition_matches_snapshot(candidate, new):
                        rejected_exhibition_input_mismatch += 1
                        continue  # Never save a falsely 'exhibition-reflected' forecast.
                    new["exhibition_input_check"] = {
                        "verified_before_freeze": True,
                        "six_boats_matched": 6,
                        "matched_fields": ["course", "exhibition_time", "exhibition_st"],
                        "original_metrics_matched": sorted(
                            (candidate.get("_exhibition_original") or {}).keys()),
                        "source": selected_source,
                        "no_result_or_payout_used": True,
                    }
                    new["sha256"] = stable_hash({k: v for k, v in new.items() if k != "sha256"})
                    before = record["versions"][-1] if record["versions"] else None
                    if before:
                        prev_bets = {b["combination"]: b["virtual_yen"] for b in before["bets"]}
                        curr_bets = {b["combination"]: b["virtual_yen"] for b in new["bets"]}
                        changed = prev_bets != curr_bets
                        new["exhibition_change"] = {
                            "comparison_phase": before["phase"],
                            "bets_changed": changed,
                            "added": sorted(set(curr_bets) - set(prev_bets)),
                            "removed": sorted(set(prev_bets) - set(curr_bets)),
                            "allocation_changed": any(prev_bets.get(k) != v for k,v in curr_bets.items()),
                            "head_changed": before["bets"][0]["combination"][0] != new["bets"][0]["combination"][0],
                            "previous_top": before["bets"][0]["combination"],
                            "new_top": new["bets"][0]["combination"],
                            "previous_point_count": len(before["bets"]),
                            "new_point_count": len(new["bets"]),
                        }
                        new["sha256"] = stable_hash({k:v for k,v in new.items() if k != "sha256"})
                        changed_exhibition += int(changed)
                    record["versions"].append(new)
                    new_exhibition += 1
                    revised_exhibition += int(revision)
            # 2026-10-25 onward, a race whose earlier v0.7 pre-cutoff
            # baseline was already fixed may receive ONE new v0.9 revision
            # BEFORE cutoff. NEVER replace the older version or backdate it.
            # If last snapshot was exhibition, only promote with complete
            # currently observed exhibition data; do not downgrade it.
            upgrade_now = datetime.now(UTC) if enforce_wall_clock else runtime_now
            previous_latest = record["versions"][-1] if record["versions"] else None
            current_context_quality = sum(
                number(value) is not None for row in (race.get("_racer_context") or {}).values()
                for value in ((row or {}).get("values") or {}).values())
            context_gain = bool(
                cutoff.date() >= FOUR_FACTOR_DATE and previous_latest
                and previous_latest.get("model_version") == expected_main
                and current_context_quality > context_quality(previous_latest.get("racers") or [])
                and sum(bool(v.get("racer_context_upgrade")) for v in record["versions"]) < 3)
            if (cutoff.date() >= WAKE_PROMOTION_DATE
                    and record["versions"]
                    and (record["versions"][-1].get("model_version") != expected_main or context_gain)
                    and upgrade_now.astimezone(JST) < cutoff - timedelta(seconds=margin)):
                latest_before = record["versions"][-1]
                phase_to_promote = latest_before["phase"]
                if phase_to_promote == "baseline" or preview_ready:
                    candidate_now = candidate if phase_to_promote == "exhibition" else race
                    latest_timestamp = datetime.now(UTC) if enforce_wall_clock else upgrade_now
                    upgrade = prediction(
                        candidate_now, VENUES[venue_code], n,
                        phase_to_promote, latest_timestamp, source_url, nearby
                    )
                    completed_at = datetime.now(UTC) if enforce_wall_clock else now
                    if not safe_to_append_pre_cutoff(upgrade, cutoff, margin, completed_at):
                        continue  # No delayed upgrade, regardless of the initial clock.
                    # Unique immutable record, not a rewrite of earlier SHA.
                    upgrade["model_upgrade"] = {
                        "previous_sha256": latest_before["sha256"],
                        "previous_model": latest_before["model_version"],
                        "revision_at_utc": latest_timestamp.isoformat(),
                        "new_model": expected_main,
                        "same_race_pre_cutoff_revision": True,
                    }
                    if context_gain:
                        upgrade["racer_context_upgrade"] = {
                            "previous_sha256": latest_before["sha256"],
                            "previous_quality": context_quality(latest_before.get("racers") or []),
                            "new_quality": current_context_quality,
                            "reason": "Newly captured player/frame fields before cutoff; old snapshot retained",
                        }
                    upgrade["sha256"] = stable_hash({
                        k: v for k, v in upgrade.items() if k != "sha256"
                    })
                    record["versions"].append(upgrade)
                    new_model_upgrades += 1
            # Results are NEVER taken from the unofficial preview API.
            # Official pay-page evidence is attached only after forecasts are generated.
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
        for extra in ("point_count", "point_reason", "head_weight_concentration", "head_weight_gap",
                      "weather_used", "weather_adjustment", "weather_ab", "data_quality",
                      "exhibition_origin", "exhibition_change",
                      "venue_profile", "venue_adjustment", "venue_surface_v1", "venue_surface_ab", "model_role", "legacy_control",
                      "start_v07", "coupled_v06", "wake_v09", "four_factor", "racer_context_upgrade", "model_upgrade", "primary_model_ab", "head_course_shares",
                      "role_coverage", "role_changes", "head_coverage_control", "postrace_conditional_v13",
                      "postrace_conditional_control", "venue_tactics_v2", "venue_tactics_ab", "point_free_control", "point_free_provenance",
                      "role_skill_shadow", "venue_motor_exhibition_shadow", "interaction_primary",
                      "exhibition_input_check", "relative_scores_uncalibrated"):
            if extra in current:
                r[extra] = current[extra]
        r["version_count"] = len(versions)
        # This is a derived, non-hashed display gate. Do not alter any frozen
        # baseline/exhibition snapshot or re-create SHA with post-race facts.
        r["entry_exhibition_gate"] = summarize_gate(current, local_day)
        r["ticket_status"] = "formal" if r["entry_exhibition_gate"]["final_eligible"] else "provisional"
        r["formal_snapshot_sha256"] = current["sha256"] if r["ticket_status"] == "formal" else None
        latest_races.append(r)
        p = record.get("official_pay")
        if p and p.get("verified") and not record.get("official_conflict") and not record.get("official_review"):
            official_results[f"{local_day}|{record['venue']}|{record['race']}"] = dict(p)
    latest_races.sort(key=lambda r: (r["cutoff_jst"], r["venue"], r["race"]))
    coverage = numeric_exhibition_coverage(records, local_day)
    out = {
        "event_date": local_day,
        "numeric_exhibition_coverage": coverage,
        "mode": "auto-live",
        "updated_at_utc": ledger["last_updated_at_utc"],
        "forecast_updated_at_utc": ledger["last_updated_at_utc"],
        "timezone": "Asia/Tokyo",
        "method": ("全国24場・新規予想はv0.7スタート差＋6艇着順連動がメイン"
                   "／旧モデル固定分は不変・同時点の旧方式を別枠検証"
                   "／保存モデル別の点数・仮想5万円（v1.5は点数枠なし）"
                   if any(x.get("model_role") == "main" for x in latest_races)
                   else "全国24場・既存の発走前固定予想（v0.7昇格前の旧モデル記録）"),
        "freeze_reference": "GitHub app/data/live/{date}.json のcommit履歴＋SHA256",
        "forecast_races": latest_races,
        "official_results": official_results,
        "unforecast_races": sorted(unavailable, key=lambda r: (r["cutoff_jst"], r["venue"])),
        "listed_races": sum(len(s.get("races", {})) for s in race_source.values()
                            if isinstance(s, dict)),
        "venues_with_races": len(venues_seen),
        "weather_venue_count": len(set(weather_by_venue)&venues_seen),
        "weather_fixed_race_count": sum(bool(r.get("weather_used")) for r in latest_races),
        "weather_adjusted_race_count": sum(bool((r.get("weather_adjustment") or {}).get("applied")) for r in latest_races),
        "exhibition_race_count": sum(r.get("phase")=="exhibition" for r in latest_races),
        "exhibition_changed_bet_count": sum(bool((r.get("exhibition_change") or {}).get("bets_changed")) for r in latest_races),
        "exhibition_input_mismatch_rejected_this_run": rejected_exhibition_input_mismatch,
        "exhibition_input_verified_race_count": sum(
            bool((r.get("exhibition_input_check") or {}).get("verified_before_freeze"))
            for r in latest_races),
        "final_exhibition_verified_races": sum(bool((r.get("entry_exhibition_gate") or {}).get("final_eligible")) for r in latest_races),
        "entry_watch_races": sum(bool((r.get("entry_exhibition_gate") or {}).get("entry_watch")) for r in latest_races),
        "entry_watch_held_races": sum(
            bool((r.get("entry_exhibition_gate") or {}).get("entry_watch"))
            and not (r.get("entry_exhibition_gate") or {}).get("final_eligible")
            for r in latest_races),
        "venue_weather": {
            VENUES[code]: weather_at(weather, now.astimezone(JST))
            for code, weather in weather_by_venue.items()
            if code in venues_seen and code in VENUES and weather_at(weather, now.astimezone(JST))
        },
        "weather_source_note": "場内実測は展示時だけ。周辺値はOpen-Meteo近隣気象予報で実測ではない。",
        "disclaimer": "非公式・数分遅延あり。展示動画と直前オッズは未対応。BUY判定は実施しません。仮想5万円は検証用で、実投票ではありません。",
    }
    status = {"event_date": local_day, "source": source_url,
              "listed_races": out["listed_races"], "venue_count": len(venues_seen),
              "forecast_races": len(latest_races),
              "missed_or_unavailable": len(unavailable),
              "new_baseline": new_baseline, "new_exhibition": new_exhibition,
              "new_model_upgrades": new_model_upgrades,
              "revised_exhibition": revised_exhibition,
              "changed_exhibition": changed_exhibition,
              "entry_watch_races": out["entry_watch_races"],
              "entry_watch_held_races": out["entry_watch_held_races"],
              "final_exhibition_verified_races": out["final_exhibition_verified_races"],
              "exhibition_input_mismatch_rejected_this_run": rejected_exhibition_input_mismatch,
              "numeric_exhibition_coverage": coverage["total"],
              "official_results": len(official_results),
              "weather_venues": len(set(weather_by_venue)&venues_seen),
              "weather_coverage": f"{len(set(weather_by_venue)&venues_seen)}/{len(venues_seen)}"}
    return ledger, out, status



def integrate_official(ledger: dict, view: dict, pay: dict,
                       now: datetime) -> dict:
    """Attach verified official results ONLY to previously frozen forecasts.

    Validation occurs independently after predictions have been generated; the
    official page is not a feature source. A correction/conflict requires manual
    review instead of silently changing completed simulated results.
    """
    if pay.get("date") != ledger.get("event_date"):
        raise ValueError("Official payoff date does not match prediction date")
    records = ledger["race_records"]
    processed = 0
    alerts = {}
    for key, issue in pay.get("reviews", {}).items():
        rec = records.get(key)
        if rec and rec.get("versions"):
            rec["official_review"] = issue.get("reason", "review")
            alerts[f"{ledger['event_date']}|{rec['venue']}|{rec['race']}"] = {
                "status": "review", "reason": "返還・異常払戻の確認が必要",
                "source_url": pay["source_url"],
            }
    for key, issue in pay.get("cancellations", {}).items():
        rec = records.get(key)
        if rec and rec.get("versions"):
            rec["official_review"] = "cancelled"
            alerts[f"{ledger['event_date']}|{rec['venue']}|{rec['race']}"] = {
                "status": "cancelled", "reason": "レース中止",
                "source_url": pay["source_url"],
            }
    for key, payout in pay.get("results", {}).items():
        rec = records.get(key)
        if not rec or not rec.get("versions") or rec.get("official_review"):
            continue
        cutoff = datetime.fromisoformat(rec["versions"][-1]["cutoff_iso_jst"])
        if now.astimezone(JST) < cutoff:
            continue
        combo = payout["finish"]
        amount = payout["payout_per_100"]
        if not isinstance(amount, int) or amount < 100 or amount % 10 != 0:
            continue
        if not isinstance(combo, str) or len(combo.split("-")) != 3:
            continue
        previous = rec.get("official_pay")
        if previous and (previous["finish"], previous["payout_per_100"]) != (combo, amount):
            rec["official_conflict"] = {
                "previous": [previous["finish"], previous["payout_per_100"]],
                "current": [combo, amount],
                "detected_at_utc": now.astimezone(UTC).isoformat(),
            }
            alerts[f"{ledger['event_date']}|{rec['venue']}|{rec['race']}"] = {
                "status": "conflict", "reason": "公式結果の値が以前の取得値と不一致",
                "source_url": pay["source_url"],
            }
            continue
        if not previous:
            rec["official_pay"] = {
                "finish": combo, "payout_per_100": amount, "verified": True,
                "source": "boatrace_official_pay", "source_url": pay["source_url"],
                "recorded_at": pay["retrieved_at_utc"],
            }
            processed += 1

    # Current official evidence only. A stale unofficial datum is NEVER used.
    results = {}
    base = ledger["event_date"]
    for rec in records.values():
        if not rec.get("versions"):
            continue
        key = f"{base}|{rec['venue']}|{rec['race']}"
        if rec.get("official_conflict"):
            alerts[key] = {
                "status": "conflict", "reason": "公式払戻に差異あり",
                "source_url": pay["source_url"],
            }
            continue
        if rec.get("official_review"):
            if key not in alerts:
                alerts[key] = {
                    "status": "review", "reason": "返還・中止・払戻の確認待ち",
                    "source_url": pay["source_url"],
                }
            continue
        p = rec.get("official_pay")
        if not p or not p.get("verified"):
            continue
        snap = rec["versions"][-1]
        stake = sum(b["virtual_yen"] for b in snap["bets"])
        winning_bet = next((b for b in snap["bets"] if b["combination"] == p["finish"]), None)
        paid = winning_bet["virtual_yen"] * p["payout_per_100"] // 100 if winning_bet else 0
        first_second = any(b["combination"][:3] == p["finish"][:3] for b in snap["bets"])
        head = any(b["combination"][0] == p["finish"][0] for b in snap["bets"])
        baseline_control = snap.get("weather_ab")
        weather_comparison = None
        if baseline_control and baseline_control.get("generated_pre_cutoff"):
            alternative = baseline_control.get("control_bets") or []
            if alternative and all(
                isinstance(b.get("virtual_yen"), int) and b.get("combination")
                for b in alternative
            ) and sum(b["virtual_yen"] for b in alternative) == 50000:
                control_hit = next((b for b in alternative if b["combination"] == p["finish"]), None)
                control_paid = (
                    control_hit["virtual_yen"] * p["payout_per_100"] // 100
                    if control_hit else 0
                )
                weather_comparison = {
                    "control_hit": bool(control_hit),
                    "control_payout": control_paid,
                    "control_profit": control_paid - 50000,
                    "weather_hit": bool(winning_bet),
                    "weather_payout": paid,
                    "weather_profit": paid - stake,
                    "weather_minus_control_yen": paid - control_paid,
                    "control_point_count": len(alternative),
                    "weather_point_count": len(snap["bets"]),
                    "source": "pre_cutoff_shadow_frozen",
                }
        old_control = snap.get("legacy_control")
        old_comparison = None
        if (isinstance(old_control, dict)
                and old_control.get("model_role") == "shadow_validation"):
            alternative = old_control.get("bets") or []
            if (4 <= len(alternative) <= 12
                    and all(isinstance(b.get("virtual_yen"), int)
                            and isinstance(b.get("combination"), str) for b in alternative)
                    and sum(b["virtual_yen"] for b in alternative) == VIRTUAL_BUDGET_YEN):
                old_bet = next((b for b in alternative if b["combination"] == p["finish"]), None)
                old_paid = old_bet["virtual_yen"] * p["payout_per_100"] // 100 if old_bet else 0
                old_comparison = {
                    "model_version": old_control["model_version"],
                    "hit": bool(old_bet), "virtual_payout": old_paid,
                    "virtual_stake": VIRTUAL_BUDGET_YEN,
                    "virtual_profit": old_paid - VIRTUAL_BUDGET_YEN,
                    "main_minus_legacy_yen": paid - old_paid,
                    "source": "same_pre_cutoff_shadow_only",
                    "legacy_sha256": old_control.get("sha256"),
                }
        role_comparison = None
        shadow = snap.get("role_skill_shadow")
        if (isinstance(shadow, dict)
                and shadow.get("status") == "ready"
                and shadow.get("model_role") == "shadow_validation"
                and shadow.get("generated_pre_cutoff") is True
                and shadow.get("result_data_used") is False
                and shadow.get("frozen_at_utc") == snap.get("frozen_at_utc")):
            alternative = shadow.get("bets")
            if (isinstance(alternative, list)
                    and len(alternative) == len(snap["bets"])
                    and len({b.get("combination") for b in alternative
                             if isinstance(b, dict)}) == len(alternative)
                    and all(isinstance(b, dict)
                            and isinstance(b.get("combination"), str)
                            and len(b["combination"].split("-")) == 3
                            and len(set(b["combination"].split("-"))) == 3
                            and all(i in "123456" for i in b["combination"].split("-"))
                            and isinstance(b.get("virtual_yen"), int)
                            and b["virtual_yen"] > 0 for b in alternative)
                    and sorted(b["virtual_yen"] for b in alternative)
                        == sorted(b["virtual_yen"] for b in snap["bets"])
                    and sum(b["virtual_yen"] for b in alternative) == VIRTUAL_BUDGET_YEN):
                test_bet = next((b for b in alternative if b["combination"] == p["finish"]), None)
                test_paid = (test_bet["virtual_yen"] * p["payout_per_100"] // 100
                             if test_bet else 0)
                role_comparison = {
                    "main_hit": bool(winning_bet), "shadow_hit": bool(test_bet),
                    "main_payout": paid, "shadow_payout": test_paid,
                    "shadow_minus_main_yen": test_paid - paid,
                    "same_frozen_input": True, "same_point_count": True,
                    "same_stake_distribution": True, "no_extra_formal_stake": True,
                    "main_head_captured": head,
                    "shadow_head_captured": any(
                        b["combination"].split("-")[0] == p["finish"].split("-")[0]
                        for b in alternative),
                    "main_first_second": first_second,
                    "shadow_first_second": any(
                        b["combination"].split("-")[:2] == p["finish"].split("-")[:2]
                        for b in alternative),
                    "model_version": shadow.get("version") or "unknown",
                    "source": "same_pre_cutoff_role_skill_shadow_only",
                }
        results[key] = {
            **p, "hit": bool(winning_bet), "virtual_stake": stake,
            "virtual_payout": paid, "virtual_profit": paid - stake,
            "head_captured": head, "first_second": first_second,
            "third_miss": bool(first_second and not winning_bet),
            "snapshot_phase": snap["phase"], "snapshot_sha256": snap["sha256"],
            "weather_comparison": weather_comparison,
            "legacy_comparison": old_comparison,
            **({"role_skill_comparison": role_comparison} if role_comparison else {}),
        }

    role_trials = [r["role_skill_comparison"] for r in results.values()
                   if r.get("role_skill_comparison")]
    if role_trials:
        def role_summary(rows):
            return {
                "races": len(rows),
                "main_hits": sum(r["main_hit"] for r in rows),
                "shadow_hits": sum(r["shadow_hit"] for r in rows),
                "main_payout": sum(r["main_payout"] for r in rows),
                "shadow_payout": sum(r["shadow_payout"] for r in rows),
                "shadow_minus_main_yen": sum(r["shadow_minus_main_yen"] for r in rows),
                "virtual_stake_per_model": len(rows) * VIRTUAL_BUDGET_YEN,
                "main_head_misses": sum(not r["main_head_captured"] for r in rows),
                "shadow_head_misses": sum(not r["shadow_head_captured"] for r in rows),
                "main_third_misses": sum(r["main_first_second"] and not r["main_hit"] for r in rows),
                "shadow_third_misses": sum(r["shadow_first_second"] and not r["shadow_hit"] for r in rows),
            }
        versions = sorted({r["model_version"] for r in role_trials})
        view["role_skill_backtest"] = {
            **role_summary(role_trials),
            "mixed_versions": len(versions) > 1,
            "by_model_version": {version: role_summary([
                r for r in role_trials if r["model_version"] == version
            ]) for version in versions},
            "scope": "発走前同一入力の試験比較。正式予想・収支に試験買い目を合算しない",
        }

    comparable = [
        r["weather_comparison"] for r in results.values()
        if r.get("weather_comparison") is not None
    ]
    view["weather_backtest"] = {
        "races": len(comparable),
        "weather_hits": sum(bool(r["weather_hit"]) for r in comparable),
        "control_hits": sum(bool(r["control_hit"]) for r in comparable),
        "weather_payout": sum(r["weather_payout"] for r in comparable),
        "control_payout": sum(r["control_payout"] for r in comparable),
        "virtual_stake_per_model": len(comparable) * 50_000,
        "weather_minus_control_yen": sum(r["weather_minus_control_yen"] for r in comparable),
        "model_note": "発走前固定の気象補正あり・なしの試験比較。配当・結果はBOATRACE公式確定後に照合",
    }
    historical = [r["legacy_comparison"] for r in results.values()
                  if r.get("legacy_comparison") is not None]
    view["main_vs_legacy"] = {
        "model": (FOUR_FACTOR_MODEL if view.get("event_date", "") >= FOUR_FACTOR_DATE.isoformat() else MAIN_WAKE_MODEL if view.get("event_date", "") >= WAKE_PROMOTION_DATE.isoformat() else MAIN_MODEL), "verified_comparisons": len(historical),
        "legacy_model_label": "Previous main, same pre-cutoff inputs",
        "main_hits": sum(bool(results[key]["hit"]) for key in results if results[key].get("legacy_comparison")),
        "legacy_hits": sum(bool(r["hit"]) for r in historical),
        "main_virtual_payout": sum(results[key]["virtual_payout"] for key in results if results[key].get("legacy_comparison")),
        "legacy_virtual_payout": sum(r["virtual_payout"] for r in historical),
        "virtual_stake_per_model": len(historical)*VIRTUAL_BUDGET_YEN,
        "note": "Both models are independent pre-cutoff frozen comparisons. Only main tickets count in official primary performance."
    }
    view["official_results"] = results
    view["settlement_alerts"] = alerts
    view["official_pay_info"] = {
        "source_url": pay["source_url"],
        "retrieved_at_utc": pay["retrieved_at_utc"],
        "verified_on_page": len(pay["results"]),
        "confirmed_forecast_results": len(results),
        "needs_review": len(alerts),
        "pending_on_page": pay.get("pending_count", 0),
        "newly_confirmed": processed,
    }
    return view


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
    parser.add_argument("--tactics-json", type=Path, help="Licensed past-only course/technique profiles, keyed by race code")
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
    # Forecast weather is fetched only for venues actually hosting races today.
    # A failed provider request is reported; never synthesize wind readings.
    active = [
        code for code, stadium in ((source.get("programs") or {}).get("stadiums") or {}).items()
        if code in VENUES and isinstance(stadium, dict) and stadium.get("races")
    ]
    nearby_forecasts = {}
    weather_error = None
    if not args.input_json:
        try:
            nearby_forecasts = fetch_weather(active, now)
        except Exception as exc:
            weather_error = str(exc)
    # BoatraceCSV data must have been downloaded by this run BEFORE forecasting.
    # Tests with --input-json receive no historical research file by default.
    research = (available_rows(Path("app/data/exhibition") / f"{day}.json", day)
                if not args.input_json else {})
    contexts = {}
    if not args.input_json and now.astimezone(JST).date() >= FOUR_FACTOR_DATE:
        try:
            contexts = collect_racer_context(now.astimezone(JST).date())
        except Exception:
            contexts = {}  # Missing sources stay neutral, never fabricate player history.
    # Explicit opt-in source; never automatically scrape a restricted site.
    # Each racer row is individually checked against its future cutoff.
    tactics_rows = {}
    if args.tactics_json:
        raw_tactics = json.loads(args.tactics_json.read_text(encoding='utf-8'))
        if raw_tactics.get('event_date') != day or not isinstance(raw_tactics.get('races'), dict):
            raise ValueError('Tactics file date or race map mismatch')
        tactics_rows = raw_tactics['races']
    ledger, webapp, summary = build(previous, source, now, source_url, nearby_forecasts,
                                     exhibition_rows=research, enforce_wall_clock=not bool(args.input_json),
                                     racer_context_rows=contexts, tactics_rows=tactics_rows)
    if weather_error:
        summary["weather_error"] = weather_error
        webapp["weather_fetch_status"] = "UNAVAILABLE"
    else:
        webapp["weather_fetch_status"] = "OK" if nearby_forecasts else "NO_DATA"
    # Read official payouts only AFTER the pre-cutoff forecast has been frozen.
    # Failure of the official website must not make up results or erase forecasts.
    try:
        pay = fetch_official_pay(compact)
        # Publish an independently verified, date-scoped FULL official payoff
        # table for batch reconciliation of multiple venues/races. This is
        # official evidence only; no prediction data and no raw HTML.
        pay_path = args.out_dir / "official-pay" / f"{day}.json"
        old_pay = json.loads(pay_path.read_text(encoding="utf-8")) if pay_path.exists() else {}
        if old_pay.get("date") == day:
            # Do not lose previously verified races when an official response is
            # temporarily sparse. Conflicting published values are quarantined.
            conflict = dict(old_pay.get("conflicts") or {})
            old_results = old_pay.get("results") or {}
            for key, v in old_results.items():
                new_value = pay["results"].get(key)
                if new_value and new_value != v:
                    conflict[key] = {"previous": v, "incoming": new_value}
                    pay["results"].pop(key, None)
                    pay.setdefault("reviews", {})[key] = {"reason": "official_correction_conflict"}
                elif not new_value and key not in pay.get("reviews", {}) and key not in pay.get("cancellations", {}) and key not in conflict:
                    pay["results"][key] = v
            pay["conflicts"] = conflict
            for key in conflict:
                pay["results"].pop(key, None)
        pay["evidence_type"] = "official_boatrace_pay_snapshot"
        pay["status"] = "verified_by_server_fetch"
        write_json(pay_path, pay)
        webapp = integrate_official(ledger, webapp, pay, now)
        summary["official_pay"] = webapp["official_pay_info"]
    except Exception as exc:
        summary["official_pay_error"] = str(exc)
        # A fetch failure does not invalidate previously verified official results.
        preserved = {
            "date": day, "results": {}, "reviews": {}, "cancellations": {},
            "source_url": f"https://www.boatrace.jp/owpc/pc/race/pay?hd={compact}",
            "retrieved_at_utc": now.astimezone(UTC).isoformat(),
        }
        integrate_official(ledger, webapp, preserved, now)
        webapp["official_pay_info"]["source_status"] = "FETCH_FAILED"
        webapp["official_pay_info"]["error"] = str(exc)
    # A successful GET with no scheduled races still writes a factual empty dashboard.
    write_json(path, ledger)
    write_json(args.out_dir / "latest.json", webapp)
    # This record is written only by the forecast collector. Result updates
    # cannot make an old exhibition capture look fresh to its watchdog.
    write_json(args.out_dir / "forecast-sync-latest.json", {
        "schema": "boatlabs.forecast_capture.v1", "event_date": day,
        "status": "completed", "captured_at_utc": webapp["forecast_updated_at_utc"],
        "completed_at_utc": (now if args.input_json else datetime.now(UTC)).astimezone(UTC).isoformat(),
        "listed_races": summary["listed_races"], "forecast_races": summary["forecast_races"],
        "final_exhibition_verified_races": webapp["final_exhibition_verified_races"],
    })
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
