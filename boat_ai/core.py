from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from itertools import permutations
import json
import math


@dataclass(frozen=True)
class RaceInput:
    race_id: str
    cutoff_iso: str
    strengths: tuple[float, ...]


def predict(race: RaceInput) -> dict[str, float]:
    """Untrained Plackett-Luce baseline; NOT calibrated probabilities."""
    if len(race.strengths) != 6 or any(not math.isfinite(x) or x <= 0 for x in race.strengths):
        raise ValueError("Exactly six positive finite strengths are required")
    weights = race.strengths
    result = {}
    for a, b, c in permutations(range(6), 3):
        p = (weights[a] / sum(weights)) * (weights[b] / (sum(weights) - weights[a])) * (weights[c] / (sum(weights) - weights[a] - weights[b]))
        result[f"{a+1}-{b+1}-{c+1}"] = p
    return result


def freeze_prediction(race: RaceInput, probabilities: dict[str, float], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cutoff = datetime.fromisoformat(race.cutoff_iso)
    if cutoff.tzinfo is None or now.tzinfo is None:
        raise ValueError("Timezone-aware cutoff and timestamp required")
    if now >= cutoff:
        raise ValueError("Cannot freeze after cutoff")
    if len(probabilities) != 120 or abs(sum(probabilities.values()) - 1) > 1e-8:
        raise ValueError("Invalid prediction distribution")
    record = {"race_id": race.race_id, "cutoff_iso": race.cutoff_iso, "frozen_at": now.isoformat(), "probabilities": probabilities, "model_version": "baseline-0.1"}
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
    return {**record, "sha256": sha256(canonical.encode()).hexdigest()}


def settle_prediction(frozen: dict, result: str) -> dict:
    if result not in frozen["probabilities"]:
        raise ValueError("Invalid finish order")
    ranked = sorted(frozen["probabilities"], key=frozen["probabilities"].get, reverse=True)
    return {"race_id": frozen["race_id"], "result": result, "top_prediction": ranked[0], "top_hit": ranked[0] == result, "result_probability": frozen["probabilities"][result], "prediction_sha256": frozen["sha256"]}
