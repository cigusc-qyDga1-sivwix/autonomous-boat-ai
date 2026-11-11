import unittest
from dataclasses import replace
from scripts.nationwide_video_registry import (
    REGISTRY, active_codes, coverage, validate_candidate,
)

class RegistryTests(unittest.TestCase):
    def test_coverage(self):
        self.assertEqual(len(REGISTRY), 24)
        self.assertEqual(len(active_codes()), 23)
        self.assertNotIn("03", active_codes())
        self.assertFalse(any(x.ready for x in REGISTRY.values()))
        self.assertEqual(coverage()["approved_sources"], 0)

    def test_safe_fail_closed(self):
        self.assertEqual(validate_candidate("10", "https://example.org/stream")["reason"],
                         "PROVIDER_APPROVAL_OR_PLAYBACK_UNVERIFIED")
        self.assertEqual(validate_candidate("03", "https://example.org/stream")["reason"],
                         "EXCLUDED_VENUE")
        self.assertEqual(validate_candidate("99", "https://example.org/stream")["reason"],
                         "UNKNOWN_VENUE")

    def test_approved_host_exact_only(self):
        approved = replace(REGISTRY["10"], status="READY", provider_name="Test",
            approved_host="media.example.org", provider_verified=True, terms_verified=True,
            permission_verified=True, playback_verified=True)
        self.assertTrue(validate_candidate("10", "https://media.example.org/live", approved)["allowed"])
        for url in ("http://media.example.org/live", "https://media.example.org.evil.test/",
                    "https://media.example.org:8443/", "https://user@media.example.org/",
                    "https://evil.test/?next=media.example.org"):
            self.assertFalse(validate_candidate("10", url, approved)["allowed"])
        self.assertFalse(validate_candidate("11", "https://media.example.org/", approved)["allowed"])
        not_approved = replace(approved, permission_verified=False)
        self.assertFalse(validate_candidate("10", "https://media.example.org/", not_approved)["allowed"])

if __name__ == "__main__":
    unittest.main()
