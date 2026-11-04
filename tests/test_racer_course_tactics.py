import pytest
from scripts.racer_course_tactics import rate, profile, pairwise_note


REF = {"technique": {x: .1 for x in (
    "escape", "sashi", "makuri", "makurizashi", "nuki", "megumare")},
    "defense": {"makurare": .2, "sasare": .2, "nigasashi": .2}}
SHA = "a" * 64


def example(*, starts=40):
    return {"racer_id": 4321, "course": 4, "starts": starts,
            "wins_by_technique": {"makuri": 8 if starts >= 8 else 0},
            "defended": {"makurare": {"opportunities": 30, "occurrences": 6},
                         "sasare": {"opportunities": 25, "occurrences": 4}},
            "observed_until_utc": "2026-11-03T10:00:00+00:00",
            "source_sha256": SHA}


def build(row=None):
    return profile(example() if row is None else row, REF, target_racer_id=4321,
                   course=4, cutoff_at_utc="2026-11-04T01:00:00+00:00")


def test_shrinkage_and_denominators():
    p = build()
    assert p["technique_per_start"]["makuri"] == pytest.approx((8 + 3) / 70)
    assert p["defense_per_opportunity"]["makurare"] == pytest.approx((6 + 6) / 60)
    assert not p["formal_forecast_eligible"]
    assert p["status"] == "RESEARCH_READY"


def test_missing_samples_only_reference_no_false_skill():
    p = build(example(starts=0))
    assert p["status"] == "INSUFFICIENT"
    assert p["technique_per_start"]["makuri"] == pytest.approx(.1)
    assert pairwise_note(p, p, attack="makuri")["status"] == "NO_ADJUSTMENT"


def test_no_result_leakage_or_identity_crossjoin():
    x = example()
    x["observed_until_utc"] = "2026-11-04T01:00:00+00:00"
    with pytest.raises(ValueError):
        build(x)
    x = example()
    x["course"] = 3
    with pytest.raises(ValueError):
        build(x)
    x = example()
    x["source_sha256"] = ""
    with pytest.raises(ValueError):
        build(x)


def test_counts_and_denominators_validated():
    x = example()
    x["wins_by_technique"]["makuri"] = 41
    with pytest.raises(ValueError):
        build(x)
    x = example()
    x["defended"]["sasare"]["occurrences"] = 26
    with pytest.raises(ValueError):
        build(x)
    with pytest.raises(ValueError):
        rate(2, 1, prior_rate=.1)


def test_pairwise_has_no_fake_success_probability():
    p = build()
    result = pairwise_note(p, p, attack="makuri")
    assert result["status"] == "RESEARCH_SIGNAL"
    assert "probability" not in result
    assert "note" in result
