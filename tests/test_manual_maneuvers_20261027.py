"""Provenance and no-retroactive-prediction guard for two user-described 1M cases."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "tamagawa": ROOT / "research/manual-maneuvers/2026-10-27-tamagawa-01.json",
    "mikuni": ROOT / "research/manual-maneuvers/2026-10-27-mikuni-05.json",
}


def test_two_observation_records_keep_trajectories_attributed_and_separate_from_forecasts():
    cases = {name: json.loads(file.read_text(encoding="utf-8"))
             for name, file in FILES.items()}
    assert {key: row["race_id"] for key, row in cases.items()} == {
        "tamagawa": "202610270501", "mikuni": "202610271005"}
    assert cases["tamagawa"]["official_result_evidence"]["final_order"] == [6, 1, 2]
    assert cases["mikuni"]["official_result_evidence"]["final_order"] == [5, 6, 1]
    for entry in cases.values():
        assert entry["schema"] == "boatlabs.manual-maneuver-observation.v1"
        assert entry["provenance"]["kind"] == "user_reported_race_observation"
        assert entry["provenance"]["independently_video_reviewed"] is False
        assert entry["use_policy"]["retrospective_label_only"] is True
        assert entry["use_policy"]["historical_forecast_modified"] is False
        assert entry["use_policy"]["production_weights_changed"] is False
        assert entry["use_policy"]["no_postrace_features_in_predictions"] is True
        assert entry["observation_sequence"]
        assert "boatrace.jp/" in entry["official_result_evidence"]["source_url"]
    assert (cases["tamagawa"]["after_start_outcome_only_diagnostics"]
            ["official_actual_race_start_timing_seconds"]["1"] == 0.06)
    assert (cases["tamagawa"]["after_start_outcome_only_diagnostics"]
            ["official_actual_race_start_timing_seconds"]["6"] == 0.13)
    assert cases["tamagawa"]["observation_sequence"][0]["status"].startswith(
        "user_reported_disputed")
    # Faster exhibition follower must not be misrepresented as an attacker.
    m = cases["mikuni"]["pre_cutoff_observable_context_from_prior_review"]
    assert m["exhibit_time_lane_6"] < m["exhibit_time_lane_5"]
