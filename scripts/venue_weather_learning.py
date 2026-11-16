"""Venue-specific WEATHER LAB outcome research with source/provenance separation.

An observational, post-result report only. Uses values saved on immutable
pre-cutoff forecasts as exposures and SHA-verified official outcomes as labels.
Never reads future forecasts, changes tickets, or promotes a weather correction.
Nearby grid forecasts are NOT racetrack observations; unverified wind bearings
are NOT classified as headwinds or tailwinds.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import math

SCHEMA = "boatlabs.venue-weather-observational.v1"
VENUES = (
    "桐生", "戸田", "平和島", "多摩川", "浜名湖", "蒲郡", "常滑", "津",
    "三国", "びわこ", "住之江", "尼崎", "鳴門", "丸亀", "児島",
    "宮島", "徳山", "下関", "若松", "芦屋", "福岡", "唐津", "大村",
)
WAVE_EVIDENCE = {
    "fresh_pre_cutoff_onsite_snapshot",
    "official_pre_cutoff_wave_with_observation_label",
}
WIND_BANDS = ("under_4", "4_to_under_6", "6_to_under_8", "8_plus")
WAVE_BANDS = ("under_4", "4_to_under_8", "8_plus")


def _number(value, lo, hi):
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    value = float(value)
    return value if lo <= value <= hi else None


def _not_late(timestamp, frozen):
    """A known source timestamp may not be later than the frozen record."""
    if timestamp is None:
        return True
    try:
        captured = datetime.fromisoformat(timestamp)
        cutoff = datetime.fromisoformat(frozen)
        return (captured.tzinfo is not None and cutoff.tzinfo is not None
                and captured <= cutoff)
    except (TypeError, ValueError):
        return False


def _metrics(items):
    n = len(items)
    hits = sum(x["stage"] == "hit" for x in items)
    payout = sum(x["virtual_payout_yen"] for x in items)
    stake = sum(x["virtual_stake_yen"] for x in items)
    return {
        "n": n,
        "hits": hits,
        "hit_rate": round(hits / n, 5) if n else None,
        "lane1_wins": sum(x["actual_head"] == "1" for x in items),
        "outside_wins": sum(x["actual_head"] != "1" for x in items),
        "outside_lane1_second": sum(
            x["actual_head"] != "1" and x["actual_finish"].split("-")[1] == "1"
            for x in items
        ),
        "head_miss": sum(x["stage"] == "head_miss" for x in items),
        "second_miss": sum(x["stage"] == "second_miss" for x in items),
        "third_miss": sum(x["stage"] == "third_miss" for x in items),
        "stake_yen": stake,
        "payout_yen": payout,
        "return_rate": round(payout / stake, 5) if stake else None,
    }


def _band(value, kind):
    if kind == "wind":
        return "under_4" if value < 4 else "4_to_under_6" if value < 6 else "6_to_under_8" if value < 8 else "8_plus"
    return "under_4" if value < 4 else "4_to_under_8" if value < 8 else "8_plus"


def _weather(r):
    """Field-level evidence: one valid field never blesses another field."""
    w = r.get("weather_used")
    w = w if isinstance(w, dict) else {}
    freeze = r.get("frozen_at_utc")
    wind = _number(w.get("wind_speed"), 0, 65)
    wind_source = w.get("wind_source") or w.get("source")
    if w.get("site_observed") is True and wind_source == "boatrace_preview":
        wind_kind = "site_preview_unverified_timestamp"
    elif wind_source in ("open-meteo", "open-meteo-jma"):
        wind_kind = "nearby_grid_forecast"
    else:
        wind_kind = "source_unverified" if wind is not None else "missing"
    if wind is not None and not _not_late(w.get("issued_at_utc"), freeze):
        wind = None
        wind_kind = "source_timestamp_late"
    if wind is None and wind_kind not in ("source_timestamp_late",):
        wind_kind = "missing"

    wave = _number(w.get("wave_height"), 0, 150)
    if wave is None:
        wave_kind = "missing"
    elif (w.get("site_wave_observed") is True
          and w.get("wave_evidence_quality") in WAVE_EVIDENCE):
        wave_kind = "site_wave_time_verified"
    elif w.get("site_observed") is True or w.get("wave_source") == "boatrace_preview_timestamp_unverified":
        wave_kind = "preview_wave_timestamp_unverified"
    else:
        wave_kind = "source_unverified"
    if wave is not None and not all(
        _not_late(w.get(field), freeze)
        for field in ("wave_collected_at_utc", "wave_source_captured_at_jst", "wave_observed_at_jst")
    ):
        wave = None
        wave_kind = "source_timestamp_late"

    rel = w.get("relative_wind") if w.get("relative_wind_verified") is True else None
    rel = rel if rel in ("headwind", "tailwind", "crosswind") else None
    tide = w.get("local_tide_stage") if w.get("local_tide_verified") is True else None
    tide = tide if tide in ("low", "mid", "high") else None
    return {
        "wind_mps": wind, "wind_source": wind_kind,
        "wind_band": _band(wind, "wind") if wind is not None else None,
        "wave_cm": wave, "wave_source": wave_kind,
        "wave_band": _band(wave, "wave") if wave is not None else None,
        "relative_wind": rel, "local_tide": tide,
    }


def _by(items, name):
    groups = defaultdict(list)
    for item in items:
        groups[item["weather"][name]].append(item["row"])
    return {str(k): _metrics(rows) for k, rows in sorted(groups.items())}


def _venue(items, all_frozen_count):
    rows = [x["row"] for x in items]
    valid_wind = [x for x in items if x["weather"]["wind_mps"] is not None]
    valid_wave = [x for x in items if x["weather"]["wave_cm"] is not None]
    return {
        "frozen_forecasts": all_frozen_count,
        "official_verified_formal": _metrics(rows),
        "coverage": {
            "wind_known": len(valid_wind),
            "wind_site_preview": sum(x["weather"]["wind_source"] == "site_preview_unverified_timestamp" for x in items),
            "wind_grid_forecast": sum(x["weather"]["wind_source"] == "nearby_grid_forecast" for x in items),
            "wave_known": len(valid_wave),
            "wave_site_time_verified": sum(x["weather"]["wave_source"] == "site_wave_time_verified" for x in items),
            "relative_wind_verified": sum(x["weather"]["relative_wind"] is not None for x in items),
            "tide_verified": sum(x["weather"]["local_tide"] is not None for x in items),
        },
        "wind_by_source": _by(items, "wind_source"),
        "wind_by_band": {
            source: {band: _metrics([x["row"] for x in valid_wind
                                    if x["weather"]["wind_source"] == source and x["weather"]["wind_band"] == band])
                     for band in WIND_BANDS}
            for source in ("site_preview_unverified_timestamp", "nearby_grid_forecast", "source_unverified")
        },
        "wave_by_source": _by(items, "wave_source"),
        "wave_by_band": {
            source: {band: _metrics([x["row"] for x in valid_wave
                                    if x["weather"]["wave_source"] == source and x["weather"]["wave_band"] == band])
                     for band in WAVE_BANDS}
            for source in ("site_wave_time_verified", "preview_wave_timestamp_unverified", "source_unverified")
        },
        "verified_relative_wind": _by([x for x in items if x["weather"]["relative_wind"] is not None], "relative_wind"),
        "verified_local_tide": _by([x for x in items if x["weather"]["local_tide"] is not None], "local_tide"),
        "sample_status": ("no_official_verified_formal" if not rows else
                          "too_small_for_venue_effect" if len(rows) < 100 else
                          "descriptive_only_not_causal"),
    }


def inspect(forecasts, verified):
    frozen = Counter(r.get("venue") for r in forecasts if isinstance(r, dict)
                     and r.get("venue") in VENUES and r.get("ticket_status") == "formal")
    lookup = {(r.get("venue"), r.get("race"), r.get("sha256")): r
              for r in forecasts if isinstance(r, dict) and r.get("venue") in VENUES}
    by_venue = defaultdict(list)
    for row in verified:
        if row.get("ticket_status") != "formal":
            continue
        venue = row.get("venue")
        if venue not in VENUES:
            continue
        snapshot = lookup.get((venue, row.get("race"), row.get("snapshot_sha256")))
        if not snapshot or snapshot.get("ticket_status") != "formal" or snapshot.get("phase") != "exhibition":
            continue
        # The caller has already enforced official verified + snapshot SHA +
        # freeze-before-cutoff, payout validity, and settlement exclusions.
        by_venue[venue].append({"row": row, "weather": _weather(snapshot)})
    report = {name: _venue(by_venue[name], frozen[name]) for name in VENUES}
    return {
        "schema": SCHEMA, "venue_count": len(VENUES), "excluded_venue": "江戸川",
        "official_verified_formal": _metrics(
            [x["row"] for name in VENUES for x in by_venue[name]]),
        "by_venue": report,
        "wind_bands_mps": {"under_4": [0, 4], "4_to_under_6": [4, 6],
                            "6_to_under_8": [6, 8], "8_plus": [8, None]},
        "wave_bands_cm": {"under_4": [0, 4], "4_to_under_8": [4, 8],
                           "8_plus": [8, None]},
        "research_only": True, "formal_forecasts_modified": False,
        "observational_not_causal": True,
        "rules": [
            "Wind site preview and nearby grid forecasts are separate, never pooled for a causal claim.",
            "Wind-direction code is unverified: headwind/tailwind requires explicit relative_wind_verified.",
            "Tide requires actual pre-cutoff local_tide_verified; never infer from venue name or time.",
            "Source observation time later than freeze is excluded, not backfilled.",
            "Only official confirmed formal exhibition forecasts are labeled; pending/refunded races are excluded.",
            "Venue-wise effects require repeated prospective seasons and matched controls, not a one-day split.",
        ],
    }
