"""Guard the repository's blobless critical-path checkout configuration."""
from pathlib import Path


def test_sparse_excludes_old_ledgers_but_includes_jst_day():
    s = Path(".github/workflows/boat-lab-auto.yml").read_text(encoding="utf-8")
    assert "id: jst_day" in s
    assert "actions/checkout@v4" in s
    assert "sparse-checkout-cone-mode: false" in s
    assert "!/app/data/live/20??-??-??.json" in s
    assert "/app/data/live/${{ steps.jst_day.outputs.day }}.json" in s
    # Setting filter explicitly would override sparse-checkout in checkout@v4.
    checkout_settings = s.split("- uses: actions/checkout@v4", 1)[1].split(
        "- name: Verify sparse checkout", 1
    )[0]
    assert "filter:" not in checkout_settings
    assert "git status --porcelain" in s
    assert "ref: main" in checkout_settings


def test_midnight_guard_blocks_publishing_unfetched_daily_ledger():
    s = Path(".github/workflows/boat-lab-auto.yml").read_text(encoding="utf-8")
    assert s.count('$(TZ=Asia/Tokyo date +%F)') >= 3
    assert "JST day rolled over; do not publish an unmaterialized daily ledger" in s


def test_full_history_statistical_audit_remains_separate():
    s = Path(".github/workflows/boat-lab-auto.yml").read_text(encoding="utf-8")
    stat = Path(".github/workflows/boat-lab-statistical.yml").read_text(encoding="utf-8")
    assert "python -m scripts.audit_statistical_shadow" not in s
    assert "python -m scripts.audit_statistical_shadow" in stat
    assert "python -m scripts.freeze_statistical_shadow" in s
