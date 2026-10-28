"""Offline tests. Network/browser access is injected and never used here."""
import unittest
from scripts.mikuni_domestic_access_check import (
    SCHEMA, access_decision, compact_profile, normal_get_statuses, run_comparison
)


def fake_probe(day, race, *, inspect_normal_get, mobile_context):
    assert (day, race) == ("2026-10-28", 1)
    assert inspect_normal_get is True
    return {
        "landing_http_status": 200,
        "meeting_header_clicked": True,
        "day_header_clicked": True,
        "race_button_clicked": True,
        "normal_browser_get_responses": [
            {"http_status": 403, "content_kind": "JSON_METADATA", "count": 1}
        ],
        "normal_browser_get_error_codes": [
            {"code": "REQUEST_FAILED", "id": 124, "status": 403}
        ],
        "access_category_hypothesis": "POSSIBLE_GEOGRAPHIC_RESTRICTION_UNCONFIRMED",
        "status": "PLAYER_API_NORMAL_GET_HTTP_403",
    }


class DomesticAccessCheckTests(unittest.TestCase):
    def test_two_probes_and_honest_access_blocker(self):
        audit = run_comparison("2026-10-28", 1, probe=fake_probe)
        self.assertEqual(audit["schema"], SCHEMA)
        self.assertEqual(audit["access_decision"], "BOTH_PROFILES_HTTP_403")
        self.assertEqual(len(audit["profiles"]), 2)
        self.assertEqual(audit["profiles"][0]["normal_get_statuses"], [403])
        self.assertEqual(audit["profiles"][1]["normal_get_statuses"], [403])
        self.assertEqual(audit["cloud_baseline"]["error_id"], 124)
        self.assertEqual(audit["verified_official_video_races"], 0)
        self.assertEqual(audit["video_bytes_downloaded"], 0)
        self.assertEqual(audit["video_frames_decoded"], 0)
        self.assertEqual(audit["six_boat_tracks_verified"], 0)
        self.assertFalse(audit["formal_forecast_modified"])

    def test_two_hundred_never_means_video(self):
        self.assertEqual(
            access_decision([
                {"normal_browser_get_responses": [{"http_status": 200}]},
                {"normal_browser_get_responses": [{"http_status": 403}]},
            ]),
            "NORMAL_GET_RESPONDED_2XX_VIDEO_NOT_VERIFIED"
        )

    def test_missing_responses_are_failure(self):
        self.assertEqual(access_decision([{}, {}]), "NO_BROWSER_GET_RESPONSE")
        self.assertEqual(access_decision([{}]), "DIAGNOSTIC_INCOMPLETE")
        self.assertEqual(
            access_decision([
                {"normal_browser_get_responses": [{"http_status": 401}]},
                {"normal_browser_get_responses": []},
            ]), "HTTP_RESPONDED_BUT_ACCESS_UNCONFIRMED"
        )

    def test_invalid_host_result_and_secret_safe_projection(self):
        probe = fake_probe("2026-10-28", 1, inspect_normal_get=True, mobile_context=True)
        probe["url"] = "https://SECRET-JLC-TOKEN.EXAMPLE/?token=SECRET"
        probe["authorization"] = "bearer SECRET"
        out = compact_profile(probe, "MOBILE_CHROMIUM_PIXEL7")
        self.assertNotIn("SECRET", repr(out))
        self.assertNotIn("authorization", repr(out))
        self.assertNotIn("url", out)
        self.assertEqual(normal_get_statuses(probe), [403])

    def test_no_baseline_for_unrelated_date(self):
        def different_date_probe(day, race, **kwargs):
            return {"normal_browser_get_responses": [{"http_status": 200}]}
        out = run_comparison("2026-10-29", 2, probe=different_date_probe)
        self.assertIsNone(out["cloud_baseline"])
        self.assertEqual(out["access_decision"], "NORMAL_GET_RESPONDED_2XX_VIDEO_NOT_VERIFIED")


if __name__ == "__main__":
    unittest.main()
