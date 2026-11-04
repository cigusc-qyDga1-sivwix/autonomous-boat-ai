"""v2.0 issue no 120-point tickets; expansion needs pre-race sources."""
from itertools import permutations
import pytest
from scripts.justified_main_points import justified_selection, justified_stakes, SAFETY_MAX_POINTS

COMBOS = ["-".join(str(x) for x in p) for p in permutations(range(1,7),3)]


def ranked(flat=False):
    return [{"combination":combo,"relative_score":1.0 if flat else 120-i}
            for i,combo in enumerate(COMBOS)]


def paths(rows):
    # Five independently named HYPOTHETICAL paths. A pair supported in one
    # path remains a hypothesis, not a verified 1M interaction.
    offsets=(0,5,10,18,60)
    return [{"scenario":f"scenario_{j}",
             "top_3":[(rows[i]["combination"],.01)
                      for i in range(start,start+3)]}
            for j,start in enumerate(offsets)]


def test_flat_ambiguity_means_skip_and_no_blind_spread():
    rows=ranked(flat=True)
    picks,meta=justified_selection(rows,paths(rows),
        exhibition_verified=True,
        independent_sources=["site_observed_weather"])
    assert len(picks)==4
    assert meta["classification"]=="SKIP"
    assert meta["weak_model_discrimination"]
    assert all("NOT_OBSERVED_EVIDENCE" in item["basis"]
               for item in meta["ticket_reasons"].values())
    assert sum(x["virtual_yen"] for x in justified_stakes(picks))==50000


def test_evidence_gates_not_120_spread():
    rows=ranked()
    paths5=paths(rows)
    base,m0=justified_selection(rows,paths5,exhibition_verified=False)
    exhibition,m1=justified_selection(rows,paths5,exhibition_verified=True)
    supported,m2=justified_selection(rows,paths5,exhibition_verified=True,
                                independent_sources=["site_observed_weather"])
    assert 4<=len(base)<=8
    assert len(base)<=len(exhibition)<=12
    assert len(exhibition)<=len(supported)<=SAFETY_MAX_POINTS
    assert m2["candidate_outcomes_analyzed"]==120
    assert m2["max_issued_ticket_points"]==24
    assert "ticket_reasons" in m2
    assert m0["independent_sources"]==[]
    for picks in (base,exhibition,supported):
        stakes=justified_stakes(picks)
        assert len(stakes)==len(picks)
        assert sum(x["virtual_yen"] for x in stakes)==50000
        assert all(x["virtual_yen"]>=1000 and x["virtual_yen"]%1000==0 for x in stakes)


def test_unverified_context_does_not_authorize_widening():
    rows=ranked()
    p=paths(rows)
    unverified,_=justified_selection(rows,p,exhibition_verified=False,
                                independent_sources=["site_observed_weather"])
    assert len(unverified)<=8
    with pytest.raises(ValueError):
        justified_selection(rows,p,exhibition_verified=True,
                            independent_sources=["invented_source"])
    with pytest.raises(ValueError):
        justified_selection(rows,p,exhibition_verified="yes")
    with pytest.raises(ValueError):
        justified_stakes([{"combination":c,"relative_score":1.0}
                          for c in COMBOS[:25]])


def test_invalid_ranked_data_not_silently_accepted():
    rows=ranked()
    with pytest.raises(ValueError):
        justified_selection(rows[:119],paths(rows),exhibition_verified=False)
    rows[0]["combination"]=rows[1]["combination"]
    with pytest.raises(ValueError):
        justified_selection(rows,paths(ranked()),exhibition_verified=False)
