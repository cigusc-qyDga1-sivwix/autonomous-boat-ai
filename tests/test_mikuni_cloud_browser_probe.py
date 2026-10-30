"""Cloud UI diagnostic never promotes a page view to verified video."""
import unittest
from scripts.mikuni_cloud_browser_probe import classify, verified_player_page

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

    def test_cloud_archive_is_separate_from_replay_verification(self):
        report = {"site_loaded": True, "venue_query_verified": True,
                  "video_elements": 0, "exhibition_menu_candidates": 0,
                  "archive_site_loaded": True,
                  "archive_requested_day_visible": True,
                  "archive_day_group_candidates": 1}
        self.assertEqual(classify(report), "OFFICIAL_PC_ENTRY_ONLY")

    def test_only_intended_official_player_is_accepted(self):
        origin = "https://livebb.jlc.ne.jp/bb_top/sp_bb/streamer/streamer26pi.php"
        good = origin + "?tenji=1&jo=10&race=01&date=20261028"
        self.assertTrue(verified_player_page(good, "2026-10-28", 1))
        bad = [
          "?tenji=1&jo=10&race=02&date=20261028",
          "?tenji=1&jo=10&race=01&date=20261027",
          "?tenji=0&jo=10&race=01&date=20261028",
          "?tenji=1&jo=01&race=01&date=20261028",
          "?tenji=1&jo=10&race=01&date=20261028&race=02",
        ]
        for query in bad:
            self.assertFalse(verified_player_page(origin + query, "2026-10-28", 1))
        self.assertFalse(verified_player_page(
            good.replace("https://", "http://"), "2026-10-28", 1))
