"""Offline regression tests: never fetch or save third-party media."""
import unittest

from scripts.mikuni_replay_transport_probe import new_audit, transport_kind, validate, response_content_kind, run_browser_probe, derive_probe_status, safe_player_error_fields, safe_request_header_presence, probable_access_category


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

    def test_allowlisted_error_fields_never_save_raw_errors(self):
        payload = {
            "code": "REQUEST_FAILED", "id": 126, "status": 403,
            "message": "SECRET_TOKEN PRIVATE_URL",
            "extra": {"access_token": "SHOULD_NOT_PERSIST"},
        }
        out = safe_player_error_fields(payload)
        self.assertEqual(out, {"code": "REQUEST_FAILED", "id": 126, "status": 403})
        self.assertNotIn("SECRET_TOKEN", repr(out))
        self.assertNotIn("SHOULD_NOT_PERSIST", repr(out))
        self.assertEqual(safe_player_error_fields({"code": "token=abc"}), {})

    def test_auth_header_presence_is_boolean_only(self):
        headers = ["origin", "referer", "x-api-key", "cookie", "authorization"]
        flags = safe_request_header_presence(headers)
        self.assertEqual(flags, {
            "has_origin": True, "has_referer": True,
            "has_authorization": True, "has_cookie": True,
            "has_api_key_header": True
        })
        self.assertTrue(all(isinstance(v, bool) for v in flags.values()))
        self.assertFalse(safe_request_header_presence([])["has_api_key_header"])

    def test_probable_geo_category_only_for_exact_403_124(self):
        self.assertEqual(
            probable_access_category([{"code": "REQUEST_FAILED", "id": 124, "status": 403}]),
            "POSSIBLE_GEOGRAPHIC_RESTRICTION_UNCONFIRMED"
        )
        self.assertEqual(
            probable_access_category([{"code": "REQUEST_FAILED", "id": 126, "status": 403}]),
            "POSSIBLE_PROVIDER_CREDENTIAL_REJECTION_UNCONFIRMED"
        )
        self.assertEqual(probable_access_category([]), "CAUSE_UNDETERMINED")

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
