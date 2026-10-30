"""Cloud UI diagnostic never promotes a page view to verified video."""
import unittest
from scripts.mikuni_cloud_browser_probe import classify

class CloudBrowserTests(unittest.TestCase):
    def test_official_site_unavailable(self):
        self.assertEqual(classify({"site_loaded": False, "venue_query_verified": True}),
                         "OFFICIAL_PC_SITE_UNAVAILABLE")

    def test_wrong_venue(self):
        self.assertEqual(classify({"site_loaded": True, "venue_query_verified": False}),
                         "WRONG_VENUE_NOT_TRUSTED")

    def test_video_element_is_not_identified_replay(self):
        report = {"site_loaded": True, "venue_query_verified": True,
                  "video_elements": 1, "exhibition_menu_candidates": 2}
        self.assertEqual(classify(report), "VIDEO_ELEMENT_FOUND_REPLAY_NOT_VERIFIED")

    def test_menu_is_only_ui_availability(self):
        report = {"site_loaded": True, "venue_query_verified": True,
                  "video_elements": 0, "exhibition_menu_candidates": 1}
        self.assertEqual(classify(report), "EXHIBITION_UI_VISIBLE_REPLAY_NOT_SELECTED")

    def test_entry_only(self):
        report = {"site_loaded": True, "venue_query_verified": True,
                  "video_elements": 0, "exhibition_menu_candidates": 0}
        self.assertEqual(classify(report), "OFFICIAL_PC_ENTRY_ONLY")
