"""Bounded venue-specific weather correction for a *forward shadow* forecast.

This module DOES NOT change the main BOAT LAB model, fixed tickets or results.
Only verified on-site data captured before a race is eligible. Generic 24-site
wind alerts are not automatic betting signals. The same canonical 120 triples
are rescored separately and compared at the same pre-cutoff timestamp.
"""
from __future__ import annotations
import math
from itertools import permutations

VERSION = "venue-weather-condition-shadow-v0.1-untrained"
OFFICIAL_CONTEXT = {
    "津": "https://www.boatrace-tsu.com/modules/datafile/?page=index_suimen",
    "尼崎": "https://boatrace-amagasaki.jp/modules/datafile/?page=index_suimen",
    "三国": "https://www.boatrace-mikuni.jp/modules/datafile/?page=index_suimen",
    "宮島": "https://www.boatrace-miyajima.com/surface.html",
    "児島": "https://www1.kojimaboat.jp/01suimen/01suimen.htm",
    "鳴門": "https://www.boatrace.jp/owpc/pc/site/place/stadium/br14/index.html",
}


def _numeric(x):
    return float(x) if type(x) in (int, float) and math.isfinite(x) else None


def site_condition(venue: str, weather: dict | None) -> dict | None:
    """Conservatively recognize ONLY evidenced local conditions.

    Site wind is available today; verified relative wind and local tide are
    future-only until their validation pipelines are implemented.
    """
    if not isinstance(weather, dict) or weather.get("site_observed") is not True:
        return None
    speed = _numeric(weather.get("wind_speed"))
    wave = _numeric(weather.get("wave_height"))
    if speed is None or not 0 <= speed <= 65:
        return None
    has_rel = weather.get("relative_wind_verified") is True
    rel = weather.get("relative_wind") if has_rel else None
    has_tide = weather.get("local_tide_verified") is True
    tide = weather.get("local_tide_stage") if has_tide else None
    condition = None
    if venue == "津" and speed >= 5:
        condition = "tsu_wind_5m"
    elif venue == "尼崎" and speed >= 6:
        condition = "amagasaki_wind_6m"
    elif venue == "三国" and speed >= 5 and rel == "tailwind":
        condition = "mikuni_verified_tailwind"
    elif venue == "鳴門" and speed >= 6 and rel == "tailwind":
        condition = "naruto_verified_tailwind"
    elif venue == "宮島" and tide == "high":
        condition = "miyajima_verified_high_tide"
    elif venue == "児島" and tide == "high" and rel == "tailwind" and speed >= 4:
        condition = "kojima_verified_tide_and_tailwind"
    if condition is None:
        return None
    combined = wave is not None and wave >= 5 and speed >= 8
    return {
        "condition": condition,
        "venue": venue,
        "context_source": OFFICIAL_CONTEXT[venue],
        "source": weather.get("source"),
        "site_observed": True,
        "wind_speed": speed,
        "wave_cm": wave,
        "combined_rough_water": combined,
        "relative_wind_verified": has_rel,
        "local_tide_verified": has_tide,
        "thresholds_calibrated": False,
        "effect": "uncertainty_flattening_only_not_course_bias",
    }


def rescore(outcomes: list[dict], venue: str, weather: dict | None) -> dict | None:
    """Create conditional-shadow 120 scores, without using results/odds.

    4% relative correction limit in qualifying site conditions; 8% only if
    verified stronger wind plus observed waves. This is an A/B trial,
    NOT a calibrated weather prediction or permission to modify main tickets.
    """
    event = site_condition(venue, weather)
    if event is None:
        return None
    valid = {"-".join(map(str, p)) for p in permutations(range(1, 7), 3)}
    if (not isinstance(outcomes, list) or len(outcomes) != 120
            or {r.get("combination") for r in outcomes} != valid
            or any(type(r.get("relative_score")) not in (int, float)
                   or not math.isfinite(r["relative_score"]) or r["relative_score"] <= 0
                   for r in outcomes)):
        raise ValueError("Missing unmodified canonical 120 triplets")
    original = [float(r["relative_score"]) for r in outcomes]
    total = sum(original)
    if not math.isclose(total, 1., rel_tol=1e-6, abs_tol=1e-6):
        raise ValueError("Canonical scores not normalized")
    severe = event["combined_rough_water"]
    alpha = .965 if severe else .985
    cap = .08 if severe else .04
    powered = [v ** alpha for v in original]
    denom = sum(powered)
    raw = [v / denom for v in powered]
    clipped = [v * max(1-cap, min(1+cap, raw_i/v)) for v, raw_i in zip(original, raw)]
    final_sum = sum(clipped)
    corrected = [{**row, "relative_score": value / final_sum}
                 for row, value in zip(outcomes, clipped)]
    return {
        "version": VERSION,
        "condition": event,
        "outcomes": corrected,
        "alpha": alpha,
        "max_pre_normalization_relative_change": cap,
        "same_input_baseline_unchanged": True,
        "primary_bets_changed": False,
        "calibrated": False,
    }
