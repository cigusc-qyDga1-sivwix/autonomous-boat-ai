"""Safety gates for lightweight numeric exhibition capture."""
from pathlib import Path
import re

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/boat-lab-exhibition-fast.yml"


def test_early_collector_is_preview_only_and_never_rewrites_formal():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "ingest_boatracecsv_exhibition.py" in source
    assert "--previews-only --date" in source
    assert "scripts/autonomous_daily.py" not in source
    assert "official_pay.py" not in source
    assert "app/data/live/" not in "\n".join(
        line for line in source.splitlines()
        if line.strip().startswith("git add "))
    assert "git push --force" not in source
    assert "git reset --hard origin/main" in source
    assert "TZ=Asia/Tokyo date +%F" in source


def test_two_nonoverlapping_5min_schedules():
    source = WORKFLOW.read_text(encoding="utf-8")
    schedules = re.findall(r"cron: '([^']+)'", source)
    assert schedules == ["0-59/5 21-23 * * *", "0-59/5 0-14 * * *"]
    primary = (WORKFLOW.parent / "boat-lab-auto.yml").read_text(encoding="utf-8")
    assert "2-59/5" in primary
    assert "github.ref == 'refs/heads/main'" in source
    assert "concurrency:" in source
