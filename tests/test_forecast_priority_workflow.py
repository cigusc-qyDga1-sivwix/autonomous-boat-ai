"""Critical-path guard for nationwide exhibition forecasts.

No full end-to-end GitHub runner is simulated by this test. It prevents
accidentally putting slow retrospective work before the pre-cutoff ledger save.
"""
from pathlib import Path


WORKFLOW = Path(".github/workflows/boat-lab-auto.yml")


def test_forecast_is_saved_before_all_retrospective_stages():
    text = WORKFLOW.read_text(encoding="utf-8")
    checkout = text.index("actions/checkout@v4")
    capture = text.index("Collect exhibition measurements before forecasting")
    freeze = text.index("Collect all available venues and freeze only pre-cutoff forecasts")
    early_push = text.index("Publish pre-cutoff exhibition forecasts immediately")
    research = text.index("Analyze research only after primary pre-cutoff revisions are frozen")
    shadow_push = text.index("Persist independent shadow and retrospective research")
    assert checkout < capture < freeze < early_push < research < shadow_push
    # A heavy AI trial or postrace shadow cannot be allowed to delay the
    # first publication of a verified six-boat forecast.
    assert "freeze_statistical_shadow" not in text[freeze:early_push]
    assert "research_coupling_patterns" not in text[freeze:early_push]


def test_primary_push_preserves_immutable_forecast_and_retries_safely():
    text = WORKFLOW.read_text(encoding="utf-8")
    priority = text.split("- name: Publish pre-cutoff exhibition forecasts immediately")[1]
    priority = priority.split("- name: Analyze research only after primary pre-cutoff revisions are frozen")[0]
    assert "git add app/data/live/ app/data/exhibition/ app/data/venue-profiles.json" in priority
    assert "git push origin HEAD:main" in priority
    assert "git fetch origin main" in priority
    assert "git reset --hard origin/main" in priority
    assert "python scripts/autonomous_daily.py" in priority
    assert "git push --force" not in priority
    assert "app/data/experiments/" not in priority


def test_second_push_only_recomputes_research_never_forecasts():
    text = WORKFLOW.read_text(encoding="utf-8")
    later = text.split("- name: Persist independent shadow and retrospective research")[1]
    later = later.split("- name: Keep run diagnostics")[0]
    assert "git add app/data/experiments/ app/data/exhibition/ app/data/statistical/prospective-audit.json" in later
    assert "git fetch origin main" in later
    assert "python scripts/autonomous_daily.py" not in later
    assert "git push --force" not in later
    assert "research: re-evaluate trials on newest immutable ledger" in later


def test_collector_schedule_and_safety_margin_unchanged():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "cron: '2-59/5 0-14 * * *'" in text
    assert "cron: '2-59/5 21-23 * * *'" in text
    assert "group: boat-lab-nationwide" in text
    assert "cancel-in-progress: false" in text
