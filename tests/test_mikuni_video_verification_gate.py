"""Local ledger checks; no video stream or user PC required."""
import copy
import unittest
from scripts.mikuni_video_verification_gate import audit


def base():
    auto = {"schema": "boatlabs.mikuni_authorized_video_ingestion.v1",
            "event_date": "2026-10-30", "venue": "三国", "venue_code": "10",
            "source_configured": False,
            "permission_provenance": "USER_REPORTED_VENUE_PERMISSION_PERSONAL_AUTO_ANALYSIS_NO_REPOST",
            "summary": {"video_races_observed": 0, "automatic_candidate_races": 0,
                        "automatic_six_candidate_races": 0, "confirmed_boat_tracks": 0}}
    shadow = {"schema": "boatlabs.mikuni_video_motion_shadow_v0.1",
              "event_date": "2026-10-30", "venue": "三国",
              "summary": {"video_shadow_frozen_races": 0,
                          "formal_forecasts_modified": 0,
                          "video_not_assumed_to_be_verified": True}}
    return auto, shadow


class EvidenceTests(unittest.TestCase):
    def test_missing_source_is_not_fake_success(self):
        report = audit(*base())
        self.assertEqual(report["state"], "AWAITING_DIRECT_MEDIA_ENDPOINT")
        self.assertEqual(report["blocker"], "DIRECT_MEDIA_ENDPOINT_NOT_CONFIGURED")
        self.assertEqual(report["venue_permission_status"], "USER_REPORTED_GRANTED_PERSONAL_AUTO_ANALYSIS_NO_REPOST")
        self.assertEqual(report["direct_media_provider_access"], "NOT_CONFIRMED_BY_BROWSER_PLAYBACK")
        self.assertFalse(report["video_ai_complete"])
        self.assertEqual(report["verified_six_boat_races"], 0)

    def test_configured_is_not_decoded(self):
        a, s = base();a["source_configured"] = True
        self.assertEqual(audit(a, s)["state"], "SOURCE_CONFIGURED_NO_DECODED_MEDIA")

    def test_real_data_still_needs_independent_identity_proof(self):
        a, s = base()
        a["source_configured"] = True
        a["summary"].update(video_races_observed=1,
                            automatic_candidate_races=1,
                            automatic_six_candidate_races=1,
                            confirmed_boat_tracks=6)
        report = audit(a, s)
        self.assertEqual(report["state"], "REAL_MEDIA_RESEARCH_UNVERIFIED")
        self.assertFalse(report["video_ai_complete"])
        self.assertEqual(report["verified_six_boat_races"], 0)

    def test_bad_input_rejected(self):
        a, s = base()
        variants = []
        v = copy.deepcopy(a);v["summary"]["video_races_observed"] = 1;variants.append((v, s))
        v = copy.deepcopy(a);v["venue_code"] = "01";variants.append((v, s))
        v = copy.deepcopy(a);v["source_configured"] = "false";variants.append((v, s))
        v = copy.deepcopy(a);v["summary"]["automatic_candidate_races"] = 2;variants.append((v, s))
        t = copy.deepcopy(s);t["summary"]["formal_forecasts_modified"] = 1;variants.append((a, t))
        t = copy.deepcopy(s);t["summary"]["video_not_assumed_to_be_verified"] = False;variants.append((a, t))
        t = copy.deepcopy(s);t["event_date"] = "2026-10-29";variants.append((a, t))
        for obj, shadow in variants:
            with self.subTest(obj=obj, shadow=shadow), self.assertRaises(ValueError):
                audit(obj, shadow)


if __name__ == "__main__":
    unittest.main()
