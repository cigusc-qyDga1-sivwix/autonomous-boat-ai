"""Pre-cutoff, course-conditioned tactics evidence for BOAT LAB.

No web scraping or guessed athlete styles. Input counts must derive from
permitted, time-stamped past race records. Never use today's target result.
Not connected to the formal forecast until source provenance is verified.
"""
from __future__ import annotations
from datetime import datetime
from math import isfinite

VERSION = "course-tactics-evidence-v0.1"
TECHNIQUES = ("escape", "sashi", "makuri", "makurizashi", "nuki", "megumare")
DEFENSE = ("makurare", "sasare", "nigasashi")
# A symmetric prior for success per start, not a learned empirical prevalence.
PRIOR_STRENGTH = 30.0
MIN_EFFECTIVE_STARTS = 20
MAX_ABS_ADJUSTMENT = 0.12


def _integer(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name}: nonnegative integer required")
    return value


def _time(text):
    if not isinstance(text, str):
        raise ValueError("ISO date-time required")
    stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Timezone required")
    return stamp


def rate(count, denominator, *, prior_rate, prior_strength=PRIOR_STRENGTH):
    """Beta-binomial shrinkage of successes per eligible start."""
    count = _integer(count, "successes")
    denominator = _integer(denominator, "starts")
    if count > denominator:
        raise ValueError("successes exceed eligible starts")
    if not (isinstance(prior_rate, (int, float))
            and isfinite(prior_rate) and 0 <= prior_rate <= 1):
        raise ValueError("invalid reference rate")
    if not (isinstance(prior_strength, (int, float))
            and isfinite(prior_strength) and prior_strength > 0):
        raise ValueError("invalid prior strength")
    return (count + prior_rate * prior_strength) / (denominator + prior_strength)


def profile(row, reference, *, target_racer_id, course, cutoff_at_utc):
    """Validate strictly past-only evidence; return provenance and smoothed rates.

    Rows: racer_id, course, starts, wins_by_technique {technique: count},
    defended {event: {opportunities, occurrences}}, observed_until_utc,
    source_sha256. Reference rates: technique and defense dictionaries keyed
    by event, each pre-estimated from OTHER historical training rows.
    """
    if not isinstance(row, dict) or not isinstance(reference, dict):
        raise ValueError("Missing inputs")
    if type(target_racer_id) is not int or type(course) is not int or course not in range(1, 7):
        raise ValueError("Invalid identity/course")
    if row.get("racer_id") != target_racer_id or row.get("course") != course:
        raise ValueError("Racer/course mismatch")
    cutoff = _time(cutoff_at_utc)
    observed = _time(row.get("observed_until_utc"))
    if observed >= cutoff:
        raise ValueError("Future/current race evidence forbidden")
    sha = row.get("source_sha256")
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("Missing SHA-256 provenance")
    starts = _integer(row.get("starts"), "starts")
    wins = row.get("wins_by_technique")
    if not isinstance(wins, dict) or set(wins) - set(TECHNIQUES):
        raise ValueError("Unexpected technique field")
    counts = {key: _integer(wins.get(key, 0), key) for key in TECHNIQUES}
    if sum(counts.values()) > starts:
        raise ValueError("Technique wins exceed starts")
    defenses = row.get("defended")
    if not isinstance(defenses, dict) or set(defenses) - set(DEFENSE):
        raise ValueError("Unexpected defensive field")
    tech_ref, defense_ref = reference.get("technique"), reference.get("defense")
    if not isinstance(tech_ref, dict) or not isinstance(defense_ref, dict):
        raise ValueError("Missing reference rates")
    tech = {key: rate(counts[key], starts, prior_rate=tech_ref[key]) for key in TECHNIQUES}
    defense = {}
    opportunity_counts = {}
    for key in DEFENSE:
        event = defenses.get(key, {})
        if not isinstance(event, dict):
            raise ValueError("Invalid defense denominator")
        occurrences = _integer(event.get("occurrences", 0), key + ".occurrences")
        opportunities = _integer(event.get("opportunities", 0), key + ".opportunities")
        defense[key] = rate(occurrences, opportunities, prior_rate=defense_ref[key])
        opportunity_counts[key] = opportunities
    return {
        "version": VERSION,
        "racer_id": target_racer_id, "course": course, "starts": starts,
        "observed_until_utc": observed.isoformat(), "source_sha256": sha,
        "technique_per_start": tech,
        "defense_per_opportunity": defense,
        "defense_opportunities": opportunity_counts,
        "effective_starts": starts,
        "status": "INSUFFICIENT" if starts < MIN_EFFECTIVE_STARTS else "RESEARCH_READY",
        "formal_forecast_eligible": False,
    }


def pairwise_note(attacker, defender, *, attack):
    """Descriptive contested-attack signal, not a probability or bet.

    The defense denominator must describe actual opportunities, not starts.
    No adjustment without matched, researched, independently observed data.
    """
    if attack not in ("makuri", "makurizashi", "sashi"):
        raise ValueError("Unrecognized attack")
    defense_key = "makurare" if attack == "makuri" else "sasare"
    if (attacker.get("status") != "RESEARCH_READY"
            or defender.get("status") != "RESEARCH_READY"
            or defender["defense_opportunities"].get(defense_key, 0) < MIN_EFFECTIVE_STARTS):
        return {"status": "NO_ADJUSTMENT", "attack": attack, "reason": "insufficient samples"}
    a = attacker["technique_per_start"][attack]
    vulnerability = defender["defense_per_opportunity"][defense_key]
    # Relative research indicator only: explicitly not a calibrated score.
    return {"status": "RESEARCH_SIGNAL", "attack": attack,
            "attacker_smoothed_frequency": round(a, 6),
            "defender_smoothed_vulnerability": round(vulnerability, 6),
            "note": "Evaluate against matched historical controls; do not auto-promote"}
