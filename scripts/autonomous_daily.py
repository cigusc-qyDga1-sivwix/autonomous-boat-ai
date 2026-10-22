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
from datetime import date, datetime, timedelta, timezone
from itertools import permutations
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

if __package__:
    from .official_pay import fetch_official_pay
    from .venue_weather import fetch_weather, weather_at, VENUE_POINTS
else:
    from official_pay import fetch_official_pay
    from venue_weather import fetch_weather, weather_at, VENUE_POINTS

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
    preview = race.get("preview")
    if not isinstance(preview, dict):
        return False
    racers = preview.get("racers") or {}
    # Complete racer exhibition and venue weather arrive independently.
    # Lack of on-water observation must not hide otherwise complete exhibition.
    return all(
        isinstance(racers.get(str(i)), dict) and all(
            number(racers[str(i)].get(field)) is not None
            for field in ("course_number", "start_timing", "exhibition_time")
        ) for i in range(1, 7)
    )


def features(race: dict, phase: str) -> tuple[list[float], list[dict]]:
    runners = race["racers"]
    preview = race.get("preview") or {}
    prev_racers = preview.get("racers") or {}
    expo_times = [number((prev_racers.get(str(i)) or {}).get("exhibition_time"))
                  for i in range(1, 7)]
    reference = min(t for t in expo_times if t is not None) if all(
        t is not None for t in expo_times) else None
    weights, detail = [], []
    for i in range(1, 7):
        racer = runners[str(i)]
        pr = prev_racers.get(str(i)) or {}
        course = int(number(pr.get("course_number"), i)) if phase == "exhibition" else i
        course = max(1, min(6, course))
        win = number(racer.get("national_win_rate"), 4.5)
        motor = number(racer.get("motor_top_2_percent"), 30.0)
        avg_st = number(racer.get("average_start_timing"), .17)
        f_count = number(racer.get("flying_count"), 0)
        score = COURSE[course - 1] * (1 + .11 * (win - 4.5)
                                     + .004 * (motor - 30)
                                     - .60 * (avg_st - .17))
        score *= 0.96 ** min(3, max(0, f_count))
        if phase == "exhibition" and reference is not None:
            expo = number(pr.get("exhibition_time"))
            est = number(pr.get("start_timing"))
            # Mild, capped adjustments: exhibition ST is not a race-day guarantee.
            score *= max(.75, min(1.23, 1 + .7 * (reference - expo)))
            score *= max(.90, min(1.10, 1 + .18 * (.16 - est)))
        weights.append(max(.12, score))
        detail.append({
            "lane": i,
            "name": str(racer.get("name", "")).strip(),
            "course": course,
            "national_win_rate": number(racer.get("national_win_rate")),
            "average_start_timing": number(racer.get("average_start_timing")),
            "motor_top_2_percent": number(racer.get("motor_top_2_percent")),
            "exhibition_st": number(pr.get("start_timing")) if phase == "exhibition" else None,
            "exhibition_time": number(pr.get("exhibition_time")) if phase == "exhibition" else None,
            "tilt": number(pr.get("tilt_adjustment")) if phase == "exhibition" else None,
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
    # Freeze a fair-weather control *before* seeing the official result.
    control_bets = allocate_stakes(combinations(weights))
    observed, selected_weather = weather_for_prediction(race, nearby_weather)
    weathered, weather_adjustment = condition_weights(weights, selected_weather)
    ranked = combinations(weathered)
    bets = allocate_stakes(ranked)
    count, reason, concentration, gap = point_count(weathered)
    if weather_adjustment['applied']:
        reason += ' ／ 気象補正試験：' + weather_adjustment['why']
    leader = racers[int(ranked[0][0][0]) - 1]
    follower = racers[int(ranked[0][0][2]) - 1]
    weather = observed
    body = {
        "model_version": "heuristic-0.4-weather-uncertainty-test-untrained",
        "point_count": count,
        "point_reason": reason,
        "head_weight_concentration": round(concentration, 4),
        "head_weight_gap": round(gap, 4),
        "phase": phase,
        "venue": venue,
        "race": race_number,
        "cutoff_jst": cutoff.strftime("%H:%M"),
        "cutoff_iso_jst": cutoff.isoformat(),
        "frozen_at_utc": now.astimezone(UTC).isoformat(),
        "source_url": source_url,
        "scenario": f"{leader['lane']}号艇{leader['name']}中心・"
                    f"{follower['lane']}号艇{follower['name']}の残存を検証"
                    + ("（展示数値を参照）" if phase == "exhibition" else "（展示前仮説）"),
        "bets": bets,
        "racers": racers,
        "weather_observed": weather,
        "weather_used": selected_weather,
        "weather_adjustment": weather_adjustment,
        "weather_ab": ({
            "control_model": "same_features_without_weather",
            "control_bets": control_bets,
            "control_point_count": len(control_bets),
            "weather_point_count": len(bets),
            "different_combinations": len({b["combination"] for b in control_bets}
                                         ^ {b["combination"] for b in bets}),
            "generated_pre_cutoff": True,
        } if selected_weather else None),
        "evidence": ("展示・場内気象あり" if weather and selected_weather and selected_weather.get("site_observed") else
                     "近隣予報（現地実測ではない）" if selected_weather else
                     "気象未取得") + ("・展示あり" if phase == "exhibition" else "・展示前"),
        "classification": "WATCH",  # No validated edge or live odds; never BUY automatically.
    }
    return {**body, "sha256": stable_hash(body)}


def build(existing: dict | None, payload: dict, now: datetime, source_url: str,
          weather_by_venue: dict | None = None) -> tuple[dict, dict, dict]:
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
    new_baseline, new_exhibition = 0, 0
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
            if now.astimezone(JST) < cutoff - timedelta(seconds=SAFE_MARGIN_SECONDS) and valid_entrants(race):
                if "baseline" not in phases:
                    record["versions"].append(prediction(race, VENUES[venue_code], n,
                                                         "baseline", now, source_url, nearby))
                    new_baseline += 1
                if "exhibition" not in phases and preview_complete(race):
                    record["versions"].append(prediction(race, VENUES[venue_code], n,
                                                         "exhibition", now, source_url, nearby))
                    new_exhibition += 1
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
                      "weather_used", "weather_adjustment", "weather_ab"):
            if extra in current:
                r[extra] = current[extra]
        r["version_count"] = len(versions)
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
        "method": "全国24場対応・未訓練Plackett–Luceヒューリスティック／4〜12点・展示前後の発走前固定",
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
        results[key] = {
            **p, "hit": bool(winning_bet), "virtual_stake": stake,
            "virtual_payout": paid, "virtual_profit": paid - stake,
            "head_captured": head, "first_second": first_second,
            "third_miss": bool(first_second and not winning_bet),
            "snapshot_phase": snap["phase"], "snapshot_sha256": snap["sha256"],
            "weather_comparison": weather_comparison,
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
    ledger, webapp, summary = build(previous, source, now, source_url, nearby_forecasts)
    if weather_error:
        summary["weather_error"] = weather_error
        webapp["weather_fetch_status"] = "UNAVAILABLE"
    else:
        webapp["weather_fetch_status"] = "OK" if nearby_forecasts else "NO_DATA"
    # Read official payouts only AFTER the pre-cutoff forecast has been frozen.
    # Failure of the official website must not make up results or erase forecasts.
    try:
        pay = fetch_official_pay(compact)
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
