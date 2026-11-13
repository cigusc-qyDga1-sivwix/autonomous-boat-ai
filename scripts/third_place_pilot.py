"""Forward-only, conditional third-place RESEARCH pilot for BOAT LAB.

Only pre-race frozen features feed inference; official results are used solely
to fit tomorrow's coefficients. Never replaces formal tickets or past SHA.
The geometric signals are proxies, NOT observed 1M maneuvers.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from boat_ai.statistical import (
    SCHEMA, FEATURES, digest, dataset, prepare, features, distributions,
    softmax, allocate,
)

PILOT_SCHEMA = "conditional-third-course-context-v0.1"
PILOT_VERSION = "third-place-context-v0.1-research-only"
JST = ZoneInfo("Asia/Tokyo")
MODEL_FILE = Path("app/data/statistical/third-place-pilot-latest.json")
PILOT_L2 = 0.08
EXTRA_FEATURES = [
    "third_between_head_second", "third_inside_both", "third_outside_both",
    "third_adjacent_to_head", "third_adjacent_to_second",
    "third_skill_minus_head", "third_motor_minus_head", "third_st_minus_head",
    "third_exhibition_minus_head", "third_skill_minus_second",
    "third_motor_minus_second", "third_st_minus_second",
    "third_exhibition_minus_second", "third_inside_head_x_wave",
    "third_outside_second_x_wind",
]
THIRD_FEATURES = FEATURES + EXTRA_FEATURES


def third_features(p: dict, third: int, head: int, second: int) -> list[float]:
    if len({third, head, second}) != 3:
        raise ValueError("Third must differ from first and second")
    courses = p["courses"]
    t, h, s = (courses[index] for index in (third, head, second))
    tv, hv, sv = (p["values"][index] for index in (third, head, second))
    inside_head = float(t < h)
    outside_second = float(t > s)
    extra = [
        float(min(h, s) < t < max(h, s)),
        float(t < min(h, s)),
        float(t > max(h, s)),
        float(abs(t-h) == 1),
        float(abs(t-s) == 1),
        tv[0]-hv[0], tv[1]-hv[1], tv[2]-hv[2], tv[3]-hv[3],
        tv[0]-sv[0], tv[1]-sv[1], tv[2]-sv[2], tv[3]-sv[3],
        inside_head*p["wave"], outside_second*p["wind"],
    ]
    return features(p, third, head, second)+extra


def fit_third(rows: list[dict]) -> dict:
    """Stage-3 conditional choice learned on historical official labels only."""
    import numpy as np
    from scipy.optimize import minimize
    from scripts.train_statistical import objective
    if len(rows) < 100:
        raise ValueError("At least 100 safely frozen past races required")
    xs, ys = [], []
    for row in rows:
        p = prepare(row["snapshot"])
        h, s, third = row["label"]
        ids = [c for c in range(6) if c not in (h, s)]
        xs.append([third_features(p, c, h, s) for c in ids])
        ys.append(ids.index(third))
    x, y = np.asarray(xs, dtype=float), np.asarray(ys, dtype=int)
    out = minimize(
        objective, np.zeros(len(THIRD_FEATURES)), args=(x, y, PILOT_L2),
        jac=True, method="L-BFGS-B",
        options={"maxiter": 250, "gtol": 1e-7, "ftol": 1e-11},
    )
    if not out.success:
        raise RuntimeError("Third-place pilot optimizer failed: " + str(out.message))
    return {
        "weights": out.x.tolist(),
        "l2": PILOT_L2,
        "optimization": {
            "success": True, "iterations": int(out.nit),
            "penalized_loss": float(out.fun),
        },
    }


def verify_pilot(pilot: dict, primary: dict, frozen: datetime) -> bool:
    try:
        if frozen.tzinfo is None or not isinstance(pilot, dict):
            return False
        if (pilot.get("schema") != PILOT_SCHEMA
                or pilot.get("version") != PILOT_VERSION
                or pilot.get("features") != THIRD_FEATURES
                or pilot.get("role") != "research_shadow"
                or pilot.get("not_formal") is not True
                or pilot.get("calibrated") is not False
                or pilot.get("parent_model_sha256") != primary.get("model_sha256")
                or pilot.get("parent_schema") != SCHEMA):
            return False
        if pilot.get("model_sha256") != digest({
                k: v for k, v in pilot.items() if k != "model_sha256"}):
            return False
        trained = date.fromisoformat(pilot["trained_through"])
        today = frozen.astimezone(JST).date()
        created = datetime.fromisoformat(pilot["created_at_utc"])
        if (created.tzinfo is None or created > frozen
                or trained >= today or trained < today - timedelta(days=2)
                or trained != date.fromisoformat(primary["trained_through"])
                or type(pilot.get("training_n")) is not int
                or pilot["training_n"] < 100):
            return False
        weights = pilot.get("weights")
        return bool(isinstance(weights, list)
                    and len(weights) == len(THIRD_FEATURES)
                    and all(type(x) in (int, float) and math.isfinite(x)
                            for x in weights))
    except (KeyError, ValueError, TypeError, OverflowError):
        return False


def load_pilot(primary: dict, frozen: datetime,
               path: Path = MODEL_FILE) -> dict | None:
    try:
        pilot = json.loads(path.read_text(encoding="utf-8"))
        return pilot if verify_pilot(pilot, primary, frozen) else None
    except (OSError, TypeError, ValueError):
        return None


def conditional_ranked(snapshot: dict, primary: dict,
                       pilot: dict) -> list[dict]:
    """Keep the v1 head/second pair mass; change *only* the third choice."""
    p = prepare(snapshot)
    v1 = distributions(snapshot, primary)
    pairs = {}
    for item in v1:
        h, s, _ = (int(x)-1 for x in item["combination"].split("-"))
        pairs[(h, s)] = pairs.get((h, s), 0.0) + item["score"]
    result = []
    for (h, s), mass in sorted(pairs.items()):
        ids = [c for c in range(6) if c not in (h, s)]
        z = [sum(a*b for a, b in zip(third_features(p, c, h, s),
                                   pilot["weights"])) for c in ids]
        probabilities = softmax(z)
        for third, prob in zip(ids, probabilities):
            result.append({
                "combination": f"{h+1}-{s+1}-{third+1}",
                "score": mass*prob,
            })
    if len(result) != 120 or abs(sum(r["score"] for r in result) - 1) > 1e-8:
        raise ValueError("Invalid conditional third distribution")
    return sorted(result, key=lambda x: (-x["score"], x["combination"]))


def frozen_shadow(snapshot: dict, primary: dict,
                  pilot: dict) -> dict:
    """Pre-cutoff ticket counterfactual, with no main ticket modification."""
    frozen = datetime.fromisoformat(snapshot["frozen_at_utc"])
    if not verify_pilot(pilot, primary, frozen):
        raise ValueError("Missing verified, same-parent, pre-cutoff third model")
    safe_input = {
        "phase": snapshot["phase"],
        "racers": [{k: r.get(k) for k in (
            "lane", "course", "national_win_rate", "motor_top_2_percent",
            "average_start_timing", "average_start_timing_imputed",
            "exhibition_time", "exhibition_st")} for r in snapshot["racers"]],
        "weather_used": {k: (snapshot.get("weather_used") or {}).get(k)
                         for k in ("wind_speed", "wave_height")},
    }
    ranked = conditional_ranked(safe_input, primary, pilot)
    count = len(snapshot["bets"])
    if not 4 <= count <= 20:
        raise ValueError("Pilot cannot change formal point policy")
    bets = allocate(ranked, count, max_points=20)
    if len(bets) != count or sum(x["virtual_yen"] for x in bets) != 50000:
        raise ValueError("Pilot violated same-budget constraint")
    return {
        "version": PILOT_VERSION,
        "model_role": "research_shadow",
        "not_formal": True,
        "no_additional_stake": True,
        "parent_model_sha256": primary["model_sha256"],
        "pilot_model_sha256": pilot["model_sha256"],
        "trained_through": pilot["trained_through"],
        "training_n": pilot["training_n"],
        "frozen_at_utc": snapshot["frozen_at_utc"],
        "source_main_bets_sha256": digest({"bets": snapshot["bets"]}),
        "source_input_sha256": digest(safe_input),
        "same_race_same_time": True,
        "same_point_count": True,
        "virtual_budget_per_model_yen": 50000,
        "formal_bets_unchanged": True,
        "bets": bets,
        "actual_1m_maneuver_observed": False,
        "result_data_used": False,
        "odds_used": False,
        "calibrated": False,
    }


def train(data_dir: Path, out_dir: Path, now: datetime,
          primary_path: Path) -> dict:
    primary = json.loads(primary_path.read_text(encoding="utf-8"))
    from scripts.learned_formal import verify_model
    if not verify_model(primary, now):
        raise ValueError("Fresh verified parent learned model required")
    day = now.astimezone(JST).date().isoformat()
    rows, audit = dataset(sorted(data_dir.glob("????-??-??.json")), day)
    if len(rows) < 100:
        raise ValueError("No sufficient confirmed historical training data")
    if max(r["day"] for r in rows) != primary["trained_through"]:
        raise ValueError("Pilot and main must have same training cutoff")
    manifest = [{
        "day": r["day"], "race_key": r["race_key"],
        "source_sha256": r["snapshot"]["sha256"],
        "official_label_sha256": digest(r["official"]),
    } for r in rows]
    source_sha = digest(manifest)
    code_sha = digest([Path(__file__).read_text(), Path("boat_ai/statistical.py").read_text()])
    path = out_dir/"third-place-pilot-latest.json"
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        if (old.get("dataset_sha256") == source_sha
                and old.get("training_code_sha256") == code_sha
                and old.get("parent_model_sha256") == primary["model_sha256"]
                and verify_pilot(old, primary, now)):
            return old
    trained = fit_third(rows)
    result = {
        **trained,
        "schema": PILOT_SCHEMA,
        "version": PILOT_VERSION,
        "features": THIRD_FEATURES,
        "created_at_utc": now.astimezone(timezone.utc).isoformat(),
        "trained_through": primary["trained_through"],
        "training_n": len(rows),
        "training_days": sorted({r["day"] for r in rows}),
        "dataset_sha256": source_sha,
        "training_code_sha256": code_sha,
        "parent_schema": SCHEMA,
        "parent_model_sha256": primary["model_sha256"],
        "role": "research_shadow",
        "not_formal": True,
        "calibrated": False,
        "input_audit": audit,
        "training_scope": "pre-cutoff snapshots and official results from earlier days only",
    }
    result["model_sha256"] = digest(result)
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                               indent=2, allow_nan=False)+"\n", encoding="utf-8")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", type=Path, default=Path("app/data/live"))
    p.add_argument("--out-dir", type=Path, default=Path("app/data/statistical"))
    p.add_argument("--main-model", type=Path,
                   default=Path("app/data/statistical/latest-model.json"))
    a = p.parse_args()
    m = train(a.data_dir, a.out_dir, datetime.now(timezone.utc), a.main_model)
    print(json.dumps({
        "pilot_model_sha256": m["model_sha256"],
        "parent_model_sha256": m["parent_model_sha256"],
        "trained_through": m["trained_through"],
        "training_n": m["training_n"],
        "role": m["role"],
    }))


if __name__ == "__main__":
    main()
