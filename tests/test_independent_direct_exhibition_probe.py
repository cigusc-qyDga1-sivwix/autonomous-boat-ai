"""Offline and safety regression tests for independent direct-preview probe."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "isolated_exhibition_collector",
    ROOT / "services" / "exhibition-bridge" / "collector.py",
)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
JST = ZoneInfo("Asia/Tokyo")

def tkz():
    return "data=\n1\n" + "".join(
        f"選手{i}\t{6.70 + i/100:.2f}\t0\t000\t52.0\t1\t- 0.5\n"
        for i in range(1, 7)
    ) + "1\t.18\t\t2\t.15\n"

def stt():
    return "data=\n1\n" + "".join(
        f"{i}\t{i}\t選手{i}\t.15\t.0{i}\t{'F' if i == 2 else ''}\t2.0\n"
        for i in range(1, 7)
    )

def captured():
    return datetime(2026, 11, 6, 12, 0, 0, tzinfo=JST)

def test_six_boat_parser_preserves_entry_and_start_f():
    boats = m.assemble(stt(), tkz())
    assert len(boats) == 6
    assert boats[0]["course"] == 1
    assert boats[1]["exhibition_f"] is True
    assert boats[1]["exhibition_st"] == -.02
    assert boats[5]["exhibition_time"] == 6.76
    assert boats[0]["tilt"] == -.5

def test_candidate_is_research_only_and_audit_ready():
    first = m.candidate("2026-11-06", 23, 7, "12:10",
                        stt(), tkz(), captured())
    second = m.candidate("2026-11-06", 23, 7, "12:10",
                         stt(), tkz(), captured() + timedelta(seconds=3))
    assert first["race_code"] == "202611062307"
    assert first["captured_at_utc"] == "2026-11-06T03:00:00+00:00"
    assert first["measurement_sha256"] == second["measurement_sha256"]
    assert first["source_observed_jst"] is None
    assert first["formal_forecast_authorized"] is False
    assert first["result_or_payout_used"] is False
    assert first["status"] == "research_only_not_formal"
    assert len(first["source_pages"]) == 2

def test_reject_cutoff_boundary_and_cross_day():
    for when in (
        captured() + timedelta(minutes=7),
        captured() + timedelta(minutes=10),
        captured() + timedelta(days=1),
    ):
        with pytest.raises(m.InvalidPreview):
            m.candidate("2026-11-06", 23, 7, "12:10", stt(), tkz(), when)

def test_disallow_incomplete_duplicate_course_bad_status_and_html():
    src = stt()
    with pytest.raises(m.InvalidPreview):
        m.assemble(src.replace("6\t6\t", "1\t6\t"), tkz())
    with pytest.raises(m.InvalidPreview):
        m.assemble(src.replace(".03\t", "\t"), tkz())
    with pytest.raises(m.InvalidPreview):
        m.assemble(src.replace("data=\n1\n", "data=\n0\n"), tkz())
    with pytest.raises(m.InvalidPreview):
        m.assemble("<!doctype html><html>not found</html>", tkz())
    with pytest.raises(m.InvalidPreview):
        m.assemble(src, tkz().replace("6.76", "99.76"))

def test_late_start_l_flag_not_falsely_normalized():
    with pytest.raises(m.InvalidPreview):
        m.assemble(stt().replace(".02\tF", ".02\tL"), tkz())

def test_one_race_url_and_input_restrictions():
    assert m.endpoint("stt", "2026-11-06", 23, 7).endswith(
        "hp_txt/23/bc_j_stt_20261106_23_07.txt")
    with pytest.raises(ValueError):
        m.endpoint("payout", "2026-11-06", 23, 7)
    with pytest.raises(ValueError):
        m.endpoint("tkz", "2026-11-06", 25, 1)

def test_live_network_off_by_default(monkeypatch):
    monkeypatch.delenv("BOATCAST_DIRECT_FETCH_APPROVED", raising=False)
    monkeypatch.setattr(m, "fetch_once", lambda _: pytest.fail("Network used"))
    local_today = datetime.now(timezone.utc).astimezone(JST).date().isoformat()
    assert m.main(["--date", local_today, "--venue", "23",
                   "--race", "7", "--cutoff", "23:59", "--live"]) == 2
