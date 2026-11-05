"""Strict venue-specific weather-condition detectors for supplemental trials.

Never infer tide height or relative wind bearing from raw source wind code.
Never change predictions or payouts. The result is a verified, pre-cutoff
conditional signal for a separately compared weather correction.
"""
from __future__ import annotations
from math import isfinite

# Only primary-source supported site-specific rules; wind thresholds for
# 三国/鳴門 are research hypotheses, not official numerical thresholds.
SOURCES = {
    "09": "https://www.boatrace-tsu.com/modules/datafile/?page=index_suimen",
    "13": "https://boatrace-amagasaki.jp/modules/datafile/?page=index_suimen",
    "10": "https://www.boatrace-mikuni.jp/modules/datafile/?page=index_suimen",
    "14": "https://www.boatrace.jp/owpc/pc/site/place/stadium/br14/index.html",
    "17": "https://www.boatrace-miyajima.com/surface.html",
    "16": "https://www1.kojimaboat.jp/01suimen/01suimen.htm",
    "08": "https://www.boatrace-tokoname.jp/modules/datafile/?page=index_suimen",
}


def num(value):
    return float(value) if isinstance(value, (float, int)) and not isinstance(value, bool) and isfinite(value) else None


def evaluate(code: str, wind, wave, freshness: str, *,
             relative_wind=None, relative_wind_verified=False,
             tide_stage=None, tide_verified=False) -> dict:
    """Only trustworthy conditions become active site-specific signals."""
    c = str(code).zfill(2)
    valid = freshness == "fresh_snapshot"
    w, h = num(wind), num(wave)
    # Never let a string passed by an unverified provider count as a direction.
    direction = relative_wind if relative_wind_verified and relative_wind in ("tailwind", "headwind", "crosswind") else None
    tide = tide_stage if tide_verified and tide_stage in ("high", "low") else None
    active = []
    pending = []
    if not valid:
        return {"status": "unavailable", "conditions": [], "pending": [],
                "supplementary_only": True, "formal_ticket_modified": False}
    if c == "09" and w is not None and w >= 5:
        active.append({"id": "tsu_wind_5m", "effect_to_check": "rough_water_start_and_turn",
                       "threshold_type": "official_descriptive", "source": SOURCES[c]})
    if c == "13" and w is not None and w >= 6:
        active.append({"id": "amagasaki_wind_6m", "effect_to_check": "slow_acceleration_or_turn_drift",
                       "threshold_type": "official_descriptive", "source": SOURCES[c]})
        if direction is None:
            pending.append("relative_wind_unverified: cannot decide makuri vs sashi")
        else:
            active.append({"id": "amagasaki_" + direction,
                           "effect_to_check": "headwind_makuri" if direction == "headwind" else "tailwind_sashi" if direction == "tailwind" else "crosswind_no_directional_bias",
                           "threshold_type": "official_descriptive", "source": SOURCES[c]})
    if c == "10":
        if w is not None and w >= 5:
            if direction == "tailwind":
                active.append({"id": "mikuni_strong_tailwind", "effect_to_check": "inside_drift_and_2_3_course_sashi",
                               "threshold_type": "research_5m_cutoff_official_directional_mechanism", "source": SOURCES[c]})
            else:
                pending.append("strong_tailwind_requires_verified_course_relative_wind")
    if c == "14" and w is not None and w >= 6:
        if direction == "tailwind":
            active.append({"id": "naruto_strong_tailwind", "effect_to_check": "turn_and_makuri",
                           "threshold_type": "research_6m_cutoff", "source": SOURCES[c]})
        else:
            pending.append("strong_tailwind_requires_verified_course_relative_wind")
    if c == "17":
        if tide == "high":
            active.append({"id": "miyajima_high_tide", "effect_to_check": "surface_swell_and_inside_survival",
                           "threshold_type": "official_descriptive_verified_local_tide_required", "source": SOURCES[c]})
        elif tide is None:
            pending.append("verified_local_tide_stage_unavailable")
    if c == "16":
        if tide == "high" and w is not None and w >= 4 and direction == "tailwind":
            active.append({"id": "kojima_high_tide_tailwind", "effect_to_check": "inside_drift_and_sashi",
                           "threshold_type": "research_4m_cutoff_official_combined_mechanism", "source": SOURCES[c]})
        elif tide is None or direction is None:
            pending.append("verified_high_tide_and_course_relative_tailwind_required")
    if c == "08" and tide is not None:
        pending.append("tokoname_regulated_pool: external_tide_cannot_be_used")
    # This is a research *trial* indicator, not a calibrated probability.
    # Only venue-specific official contextual mechanisms are expressed.
    return {"status": "active" if active else "pending" if pending else "no_site_special",
            "conditions": active, "pending": pending,
            "supplementary_only": True, "formal_ticket_modified": False,
            "direction_used": direction,
            "verified_local_tide_used": tide,
            "study_tier": "special_weather_context" if active else "base_model"}
