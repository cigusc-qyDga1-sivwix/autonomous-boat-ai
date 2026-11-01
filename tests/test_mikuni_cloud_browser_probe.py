"""Cloud UI diagnostic never promotes a page view to verified video."""
import unittest
from types import SimpleNamespace
from scripts.mikuni_cloud_browser_probe import (
    classify, verified_player_page, verified_player_surfaces,
)

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

    def test_verified_playback_refusal_is_not_reported_as_entry_only(self):
        report = {"site_loaded": True, "venue_query_verified": True,
                  "exact_day_race_verified": True,
                  "player_status": "OFFICIAL_PLAYER_VIEWING_NOT_PERMITTED"}
        self.assertEqual(classify(report), 'OFFICIAL_PLAYER_VIEWING_NOT_PERMITTED')

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

    def test_observed_pj_player_and_races_two_through_twelve(self):
        origin = "https://livebb.jlc.ne.jp/bb_top/sp_bb/streamer/streamer26pj.php"
        for race in range(1, 13):
            good = origin + f"?tenji=1&jo=10&race={race:02d}&date=20261028"
            with self.subTest(race=race):
                self.assertTrue(verified_player_page(good, "2026-10-28", race))
                self.assertFalse(verified_player_page(good, "2026-10-27", race))
                self.assertFalse(verified_player_page(good, "2026-10-28", race % 12 + 1))

    def test_player_host_path_credentials_and_bad_inputs_are_rejected(self):
        good = ("https://livebb.jlc.ne.jp/bb_top/sp_bb/streamer/streamer26pj.php"
                "?tenji=1&jo=10&race=01&date=20261028")
        bad = [good.replace(".ne.jp/", ".ne.jp.example.org/"),
               good.replace("streamer26pj.php", "other.php"),
               good.replace("https://", "https://user:pass@"),
               good.replace(".ne.jp/", ".ne.jp:8443/"), good + "#fragment"]
        for url in bad:
            self.assertFalse(verified_player_page(url, "2026-10-28", 1))
        for race in (True, 0, 13, "1"):
            self.assertFalse(verified_player_page(good, "2026-10-28", race))
        self.assertFalse(verified_player_page(good, "2026-02-30", 1))

    def test_tab_and_its_main_frame_are_one_player(self):
        frame = object()
        tab = SimpleNamespace(main_frame=frame)
        url = ("https://livebb.jlc.ne.jp/bb_top/sp_bb/streamer/streamer26pj.php"
               "?tenji=1&jo=10&race=01&date=20261028")
        matches = verified_player_surfaces([(tab, None, url), (tab, frame, url)],
                                          "2026-10-28", 1)
        self.assertEqual(matches, [(tab, None)])

    def test_two_real_players_stay_ambiguous(self):
        first = SimpleNamespace(main_frame=object())
        second = SimpleNamespace(main_frame=object())
        url = ("https://livebb.jlc.ne.jp/bb_top/sp_bb/streamer/streamer26pi.php"
               "?tenji=1&jo=10&race=01&date=20261028")
        self.assertEqual(len(verified_player_surfaces(
            [(first, None, url), (second, None, url)], "2026-10-28", 1)), 2)
        nested = object()
        self.assertEqual(len(verified_player_surfaces(
            [(first, None, url), (first, nested, url)], "2026-10-28", 1)), 2)
