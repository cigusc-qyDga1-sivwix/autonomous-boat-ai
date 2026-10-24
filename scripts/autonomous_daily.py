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
    from .official_pay import fetch_official_pay
    from .venue_weather import fetch_weather, weather_at, VENUE_POINTS
    from .exhibition_bridge import available_rows, inject
    from .entry_exhibition_gate import validated_preview, summarize_gate
    from .venue_profiles import get_profile, adjust_weights as adjust_venue_weights
else:
    from official_pay import fetch_official_pay
    from venue_weather import fetch_weather, weather_at, VENUE_POINTS
    from exhibition_bridge import available_rows, inject
    from entry_exhibition_gate import validated_preview, summarize_gate
    from venue_profiles import get_profile, adjust_weights as adjust_venue_weights

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
        detail.append({
            "lane": i,
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
                 frozen_at_utc: str) -> dict:
    """New main (only for Oct 25+). Fail closed, same pre-cutoff data."""
    inputs = {
        "venue": venue, "phase": phase,
        "racers": [{key: r.get(key) for key in (
            "lane", "course", "national_win_rate", "motor_top_2_percent",
            "average_start_timing", "exhibition_st", "exhibition_time",
            "original_exhibition"
        )} for r in racers],
        "venue_profile": profile, "weather_used": weather,
        "frozen_at_utc": frozen_at_utc,
    }
    try:
        job = subprocess.run(
            ["node", str(WAKE_BRIDGE)], input=json.dumps(inputs, ensure_ascii=False),
            text=True, capture_output=True, timeout=12, check=True
        )
        answer = json.loads(job.stdout)
    except (OSError, ValueError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        raise RuntimeError("v0.9 bridge unavailable: fail closed, no fallback freeze") from exc
    bets = answer.get("bets")
    if answer.get("model_version") != MAIN_WAKE_MODEL or not isinstance(bets, list):
        raise ValueError("Wrong new main bridge model identity")
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
        raise ValueError("Invalid v0.9 ticket allocation")
    if not answer.get("wake_v09", {}).get("pre_cutoff_only"):
        raise ValueError("Wake provenance missing")
    return answer


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
    new_primary = cutoff.date() >= WAKE_PROMOTION_DATE
    if new_primary:
        same_time_old = promoted_v07(venue, phase, racers, profile, selected_weather, frozen_at)
        legacy_control = {
            "model_version": same_time_old["model_version"],
            "bets": same_time_old["bets"],
            "point_count": len(same_time_old["bets"]),
            "frozen_at_utc": frozen_at,
            "model_role": "shadow_validation",
            "source_note": "v0.7 old main frozen at same pre-cutoff instant; no result",
        }
        legacy_control["sha256"] = stable_hash(legacy_control)
        promoted = promoted_v09(venue, phase, racers, profile, selected_weather, frozen_at)
        chosen_model = MAIN_WAKE_MODEL
    else:
        promoted = promoted_v07(venue, phase, racers, profile, selected_weather, frozen_at)
        chosen_model = MAIN_MODEL
    bets = promoted["bets"]
    count = len(bets)
    shares = promoted["head_course_shares"]
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
    body = {
        "model_version": chosen_model,
        "model_role": "main",
        "legacy_control": legacy_control,
        "start_v07": promoted["start_v07"],
        **({"wake_v09": promoted["wake_v09"],
            "primary_promotion_date_jst": WAKE_PROMOTION_DATE.isoformat(),
            "primary_model_ab": "v0.9 primary vs same-time frozen v0.7 control"}
           if new_primary else {}),
        "coupled_v06": promoted["coupled_v06"],
        "head_course_shares": promoted["head_course_shares"],
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
        "scenario": f"{leader['lane']}号艇{leader['name']}中心・"
                    f"{follower['lane']}号艇{follower['name']}の残存を検証"
                    + ("（展示数値を参照）" if phase == "exhibition" else "（展示前仮説）"),
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


def build(existing: dict | None, payload: dict, now: datetime, source_url: str,
          weather_by_venue: dict | None = None, exhibition_rows: dict | None = None,
          enforce_wall_clock: bool = False) -> tuple[dict, dict, dict]:
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
            if runtime_now.astimezone(JST) < cutoff - timedelta(seconds=margin) and valid_entrants(race):
                if "baseline" not in phases:
                    record["versions"].append(prediction(race, VENUES[venue_code], n,
                                                         "baseline", runtime_now, source_url, nearby))
                    new_baseline += 1
                code = f"{local_day.replace('-', '')}{int(venue_code):02d}{n:02d}"
                csv_race, csv_origin = inject(race, exhibition_rows.get(code), runtime_now, venue_code, n)
                candidate = csv_race if csv_origin else race
                preview_ready = preview_complete(candidate)
                existing_exhibition = [v for v in record["versions"] if v["phase"] == "exhibition"]
                previous_csv_time = (existing_exhibition[-1].get("exhibition_origin") or {}).get("observed_at_jst") if existing_exhibition else None
                revision = bool(
                    csv_origin and existing_exhibition
                    and len(existing_exhibition) < 3
                    and (not previous_csv_time or previous_csv_time < csv_origin["observed_at_jst"])
                )
                if preview_ready and ("exhibition" not in phases or revision):
                    origin_url = csv_origin and "https://boatracecsv.github.io/docs/data/previews.html" or source_url
                    new = prediction(candidate, VENUES[venue_code], n,
                                     "exhibition", (datetime.now(UTC) if enforce_wall_clock else now), origin_url, nearby)
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
            if (cutoff.date() >= WAKE_PROMOTION_DATE
                    and record["versions"]
                    and record["versions"][-1].get("model_version") != MAIN_WAKE_MODEL
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
                    # Unique immutable record, not a rewrite of earlier SHA.
                    upgrade["model_upgrade"] = {
                        "previous_sha256": latest_before["sha256"],
                        "previous_model": latest_before["model_version"],
                        "revision_at_utc": latest_timestamp.isoformat(),
                        "new_model": MAIN_WAKE_MODEL,
                        "same_race_pre_cutoff_revision": True,
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
                      "venue_profile", "venue_adjustment", "model_role", "legacy_control",
                      "start_v07", "coupled_v06", "wake_v09", "model_upgrade", "primary_model_ab", "head_course_shares",
                      "role_coverage", "role_changes", "relative_scores_uncalibrated"):
            if extra in current:
                r[extra] = current[extra]
        r["version_count"] = len(versions)
        # This is a derived, non-hashed display gate. Do not alter any frozen
        # baseline/exhibition snapshot or re-create SHA with post-race facts.
        r["entry_exhibition_gate"] = summarize_gate(current, local_day)
        latest_races.append(r)
        p = record.get("official_pay")
        if p and p.get("verified") and not record.get("official_conflict") and not record.get("official_review"):
            official_results[f"{local_day}|{record['venue']}|{record['race']}"] = dict(p)
    latest_races.sort(key=lambda r: (r["cutoff_jst"], r["venue"], r["race"]))
    out = {
        "event_date": local_day,
        "mode": "auto-live",
        "updated_at_utc": ledger["last_updated_at_utc"],
        "timezone": "Asia/Tokyo",
        "method": ("全国24場・新規予想はv0.7スタート差＋6艇着順連動がメイン"
                   "／旧モデル固定分は不変・同時点の旧方式を別枠検証"
                   "／4〜12点・仮想5万円"
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
        results[key] = {
            **p, "hit": bool(winning_bet), "virtual_stake": stake,
            "virtual_payout": paid, "virtual_profit": paid - stake,
            "head_captured": head, "first_second": first_second,
            "third_miss": bool(first_second and not winning_bet),
            "snapshot_phase": snap["phase"], "snapshot_sha256": snap["sha256"],
            "weather_comparison": weather_comparison,
            "legacy_comparison": old_comparison,
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
        "model": MAIN_MODEL, "verified_comparisons": len(historical),
        "legacy_model_label": "old Python heuristic, same pre-cutoff inputs",
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
    ledger, webapp, summary = build(previous, source, now, source_url, nearby_forecasts,
                                     exhibition_rows=research, enforce_wall_clock=not bool(args.input_json))
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
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
