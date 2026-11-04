"""Conservative, explicitly attributable primary ticket selection for v2.0.

The 120 six-boat ordered outcomes remain ANALYSIS ONLY. They are not permission
to purchase 120 trifectas. Past results are never used for same-race selection.
Without independent pre-cutoff evidence, ambiguity does not authorize expansion.

All numerical thresholds are RISK-CONTROL HEURISTICS, NOT validated win
probabilities or profitable-bet thresholds. No automatic BUY classification.
"""
from __future__ import annotations

from math import isfinite
from typing import Sequence

try:
    from .adaptive_main_points import VALID, stake_dynamic
except ImportError:
    from adaptive_main_points import VALID, stake_dynamic

VERSION = "justified-main-points-v2.0-conservative-untrained"
SAFETY_MAX_POINTS = 24
MIN_POINTS = 4


def justified_selection(ranked: Sequence[dict], scenarios: Sequence[dict], *,
                        exhibition_verified: bool,
                        independent_sources: Sequence[str] = ()):
    """Apply evidence gates before selecting any extra ticket.

    The number 24 is a provisional harm-limiting ceiling, NOT a desired count.
    Study all 120 permutations, but issue only a small supported subset.
    Even the first four remain uncalibrated model candidates, not BUY advice.
    """
    if not isinstance(ranked, (list, tuple)) or len(ranked) != 120:
        raise ValueError("Need all 120 pre-race outcomes for analysis")
    ordered, seen = [], set()
    for row in ranked:
        if not isinstance(row, dict):
            raise ValueError("Invalid ranked score")
        name, score = row.get("combination"), row.get("relative_score")
        if name not in VALID or name in seen or isinstance(score, bool) or not isinstance(score, (float,int)) or not isfinite(score) or score < 0:
            raise ValueError("Invalid/duplicate ranked outcome")
        ordered.append((name, float(score)))
        seen.add(name)
    ordered.sort(key=lambda x: (-x[1], x[0]))
    if ordered[0][1] <= 0 or sum(v > 0 for _, v in ordered) < MIN_POINTS:
        raise ValueError("Not enough positive scenario support")
    if not isinstance(scenarios, (list, tuple)) or len(scenarios) != 5:
        raise ValueError("Expected five distinct pre-race paths")
    pair_support = {}
    heads = set()
    distinct_paths = set()
    for path in scenarios:
        if not isinstance(path, dict) or not isinstance(path.get("scenario"), str):
            raise ValueError("Invalid pre-race path")
        label=path["scenario"]
        if label in distinct_paths:
            raise ValueError("Duplicated pre-race path")
        distinct_paths.add(label)
        top=path.get("top_3")
        if not isinstance(top,(list,tuple)) or len(top)!=3:
            raise ValueError("Incomplete hypothetical path")
        for entry in top:
            if not isinstance(entry, (list,tuple)) or len(entry)!=2 or entry[0] not in VALID:
                raise ValueError("Invalid hypothetical path ticket")
            a,b,_=entry[0].split("-")
            heads.add(a)
            pair_support.setdefault(f"{a}-{b}",set()).add(label)
    allowed_sources=frozenset({"past_racer_course_tactics","site_observed_weather"})
    if isinstance(exhibition_verified,bool) is False or not isinstance(independent_sources,(tuple,list)):
        raise ValueError("Evidence flags must be explicit")
    sources=tuple(sorted(set(independent_sources)))
    if not all(isinstance(x,str) and x in allowed_sources for x in sources):
        raise ValueError("Unknown/unverified independent evidence")
    # Multiple distinct leaders in hypothetical paths are required before
    # widening >12. They are model diversity, not observed 1M trajectories.
    diverse_paths=len(heads)>=2
    ratio_30th=ordered[29][1]/ordered[0][1]
    flat=ratio_30th>=.96
    if flat:
        cap=4
        tier="SKIP_FLAT_UNCALIBRATED"
    elif exhibition_verified and sources and diverse_paths:
        cap=SAFETY_MAX_POINTS
        tier="EXHIBITION_AND_INDEPENDENT_CONTEXT"
    elif exhibition_verified:
        cap=12
        tier="EXHIBITION_ONLY"
    else:
        cap=8
        tier="NO_VERIFIED_EXHIBITION"
    selected=[]
    reasons={}
    unsupported=0
    below_cutoff=0
    for name,score in ordered:
        if len(selected)>=cap:
            break
        if score<=0:
            below_cutoff+=1
            continue
        a,b,_=name.split("-")
        rel=score/ordered[0][1]
        if len(selected)<MIN_POINTS:
            why="MINIMUM_MODEL_RANK_ONLY_NOT_OBSERVED_EVIDENCE"
        else:
            path_labels=pair_support.get(f"{a}-{b}")
            if not path_labels:
                unsupported+=1
                continue
            # Model-score floors are conservative heuristics, not probabilities.
            if len(selected)<8 and rel>=.62:
                why="SUPPORTED_PAIR_IN_HYPOTHETICAL_PATH"
            elif len(selected)<12 and exhibition_verified and rel>=.55:
                why="VERIFIED_EXHIBITION_AND_SUPPORTED_PAIR"
            elif len(selected)<SAFETY_MAX_POINTS and exhibition_verified and sources and diverse_paths and rel>=.48:
                why="EXHIBITION_AND_INDEPENDENT_SOURCE_AND_SUPPORTED_PAIR"
            else:
                below_cutoff+=1
                continue
        selected.append({"combination":name,"relative_score":score})
        reasons[name]={"basis":why,
                       "path_labels":sorted(pair_support.get(f"{a}-{b}",set())),
                       "relative_score_vs_top":round(rel,4)}
    if len(selected)>SAFETY_MAX_POINTS:
        raise ValueError("Prohibited over-broad primary tickets")
    if not selected:
        raise ValueError("No supported candidates")
    # The model is not calibrated, so even a coherent set is a WATCH only.
    status="SKIP" if flat else "WATCH"
    metadata={
        "version":VERSION,"selection":"path_pair_and_verified_pre_cutoff_evidence",
        "candidate_outcomes_analyzed":120,
        "max_issued_ticket_points":SAFETY_MAX_POINTS,
        "selected_point_count":len(selected),
        "signal_quality":tier,
        "classification":status,
        "exhibition_verified":exhibition_verified,
        "independent_sources":list(sources),
        "distinct_hypothetical_winner_heads":len(heads),
        "weak_model_discrimination":flat,
        "relative_30th_vs_top":round(ratio_30th,6),
        "skipped_unsupported_pair":unsupported,
        "skipped_low_relative_score":below_cutoff,
        "ticket_reasons":reasons,
        "not_calibrated":True,
        "no_odds_edge_measured":True,
        "expansion_requires_pre_cutoff_sources":True,
        "note":"24 is a temporary risk ceiling, not an optimized betting size; no automatic BUY.",
    }
    return selected,metadata


def justified_stakes(selected):
    if not 4<=len(selected)<=SAFETY_MAX_POINTS:
        raise ValueError("New main never issues more than 24 tickets")
    return stake_dynamic(selected, budget_yen=50000, unit_yen=1000)
