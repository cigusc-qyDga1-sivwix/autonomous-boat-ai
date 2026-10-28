"""Offline regression tests: never fetch or save third-party media."""
import unittest

from scripts.mikuni_replay_transport_probe import new_audit, transport_kind, validate, response_content_kind, run_browser_probe, derive_probe_status


class TransportClassifierTests(unittest.TestCase):
    def test_hls_with_signed_query_is_classified_but_not_logged(self):
        url = "https://cdn.example.net/path/video.m3u8?token=SECRET_PRIVATE_VALUE"
        self.assertEqual(transport_kind(url), "HLS_MANIFEST")
        audit = new_audit("2026-10-28", 1)
        self.assertNotIn("SECRET_PRIVATE_VALUE", str(audit))
        self.assertNotIn("cdn.example.net", str(audit))

    def test_mime_and_formats(self):
        self.assertEqual(transport_kind("https://cdn.example.net/live", "application/vnd.apple.mpegurl"), "HLS_MANIFEST")
        self.assertEqual(transport_kind("https://cdn.example.net/manifest.mpd"), "DASH_MANIFEST")
        self.assertEqual(transport_kind("https://cdn.example.net/a/stream.mp4"), "VIDEO_FILE")
        self.assertEqual(transport_kind("https://cdn.example.net/seg.m4s"), "VIDEO_SEGMENT")
        self.assertEqual(transport_kind("https://cdn.example.net/seg.ts"), "VIDEO_SEGMENT")
        self.assertEqual(transport_kind("https://cdn.example.net/drm.key"), "DRM_OR_KEY")
        self.assertEqual(transport_kind("blob:https://example.net/id"), "BLOB_MEDIA")
        self.assertEqual(transport_kind("https://example.net/app.js"), "NOT_MEDIA")

    def test_invalid_transport_never_media(self):
        self.assertEqual(transport_kind("http://example.net/movie.mp4"), "NOT_MEDIA")
        self.assertEqual(transport_kind("file:///tmp/movie.mp4"), "NOT_MEDIA")

    def test_event_date_and_race_guard(self):
        validate("2026-10-28", 1)
        with self.assertRaises(ValueError):
            validate("2026-02-30", 1)
        with self.assertRaises(ValueError):
            validate("2026-10-28", 13)
        with self.assertRaises(ValueError):
            validate("2026-10-28", True)

    def test_normal_get_mime_is_metadata_or_transport_not_frames(self):
        url = "https://playback.api.streaks.jp/live?credential=PRIVATE"
        self.assertEqual(response_content_kind(url, "application/json; charset=utf-8"), "JSON_METADATA")
        self.assertEqual(response_content_kind(url, "application/vnd.apple.mpegurl"), "HLS_MANIFEST")
        self.assertEqual(response_content_kind(url, "video/mp4"), "VIDEO_FILE")
        self.assertEqual(response_content_kind(url, ""), "MIME_UNKNOWN")
        self.assertNotIn("PRIVATE", response_content_kind(url, "application/json"))

    def test_browser_opt_in_defaults_off(self):
        import inspect
        sig = inspect.signature(run_browser_probe)
        self.assertEqual(sig.parameters["inspect_normal_get"].default, False)
        self.assertEqual(sig.parameters["mobile_context"].default, False)
        audit = new_audit("2026-10-28", 1)
        self.assertFalse(audit["normal_browser_get_opt_in"])
        self.assertEqual(audit["browser_context_profile"], "DESKTOP_CHROMIUM")
        self.assertEqual(audit["normal_browser_get_request_count"], 0)
        self.assertEqual(audit["normal_browser_get_responses"], [])
        self.assertEqual(audit["video_bytes_downloaded"], 0)
        self.assertEqual(audit["frames_decoded"], 0)

    def test_status_reports_access_error_without_false_video_success(self):
        self.assertEqual(
            derive_probe_status({(403, "JSON_METADATA"): 1}, 1, {}),
            "PLAYER_API_NORMAL_GET_HTTP_403",
        )
        self.assertEqual(
            derive_probe_status({(401, "JSON_METADATA"): 1}, 1, {}),
            "PLAYER_API_NORMAL_GET_HTTP_401",
        )
        self.assertEqual(
            derive_probe_status({(200, "JSON_METADATA"): 1}, 1, {}),
            "PLAYER_API_NORMAL_GET_RESPONDED_NO_MEDIA",
        )
        self.assertEqual(
            derive_probe_status({}, 1, {}),
            "PLAYER_API_NORMAL_GET_NO_RESPONSE",
        )
        self.assertEqual(
            derive_probe_status({}, 0, {"HLS_MANIFEST": 1}),
            "MEDIA_TRANSPORT_CANDIDATE_OBSERVED_NOT_DOWNLOADED",
        )

    def test_no_success_claims_or_bets(self):
        audit = new_audit("2026-10-28", 6)
        self.assertFalse(audit["raw_media_downloaded"])
        self.assertFalse(audit["formal_forecast_modified"])
        self.assertEqual(audit["frames_decoded"], 0)
        self.assertEqual(audit["verified_six_boat_tracks"], 0)
        self.assertEqual(audit["video_bytes_downloaded"], 0)
        self.assertEqual(audit["status"], "NOT_RUN")


if __name__ == "__main__":
    unittest.main()
