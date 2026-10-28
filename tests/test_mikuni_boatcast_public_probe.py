import unittest
from scripts.mikuni_boatcast_public_probe import host_only, replay_page


class BoatcastPublicProbeTests(unittest.TestCase):
    def test_official_exhibition_key(self):
        self.assertEqual(
            replay_page("2026-10-28", 1),
            "https://race.boatcast.jp/replay?jo=10&md=T&race=1&ymd=20261028",
        )

    def test_unapproved_url_scheme_not_a_hostname(self):
        self.assertIsNone(host_only("blob:https://example.com/key"))
        self.assertIsNone(host_only("http://example.com/movie.mp4"))
        self.assertIsNone(host_only("javascript:alert(1)"))
        self.assertEqual(host_only("https://www.youtube.com/embed/id?token=SECRET"), "www.youtube.com")

    def test_no_guessed_invalid_race(self):
        with self.assertRaises(ValueError):
            replay_page("2026-10-28", 13)
        with self.assertRaises(ValueError):
            replay_page("2026-02-30", 1)


if __name__ == "__main__":
    unittest.main()
