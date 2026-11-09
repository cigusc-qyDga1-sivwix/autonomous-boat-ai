"""Regression: six-boat exhibition must not disappear when weather CSV is unavailable."""
import unittest
from datetime import date, datetime, timezone
from ingest_boatracecsv_exhibition import build

class OptionalWeatherTests(unittest.TestCase):
    def test_original_capture_time_is_independent_of_later_weather_revision(self):
        code = "202610260601"
        st = {"レースコード": code, "締切時刻": "10:42",
              "取得日時": "2026-10-26T10:35:00+09:00"}
        tk = {"レースコード": code}
        og = {"レースコード": code, "取得日時": "2026-10-26T10:36:00+09:00",
              "計測項目1": "一周", "計測項目2": "まわり足", "計測項目3": "直線"}
        for i in range(1, 7):
            st[f"艇{i}_コース"] = str(i)
            st[f"艇{i}_スタート展示"] = "0.10"
            tk[f"艇{i}_展示タイム"] = "6.80"
            og[f"艇{i}_選手名"] = f"選手{i}"
            og[f"艇{i}_値1"] = "36.00"
            og[f"艇{i}_値2"] = "5.50"
            og[f"艇{i}_値3"] = "7.60"
        captured = datetime(2026, 10, 26, 1, 37, tzinfo=timezone.utc)
        first = build(date(2026, 10, 26), {
            "stt": [st], "tkz": [tk], "original": [og]},
            collected_at=captured)
        a = first["records"][0]
        self.assertIsNotNone(a["original_exhibition_sha256"])
        self.assertEqual(a["original_exhibition_captured_at_utc"], captured.isoformat())
        self.assertEqual(a["original_exhibition_observed_jst"], og["取得日時"])
        # Later weather revision changes composite fingerprint, but the measured
        # original values were already seen at the earlier instant.
        later = build(date(2026, 10, 26), {
            "stt": [st], "tkz": [tk], "original": [og],
            "sui": [{"レースコード": code, "風速(m)": "4"}]},
            prior=first, collected_at=datetime(2026, 10, 26, 3, tzinfo=timezone.utc))
        b = later["records"][0]
        self.assertNotEqual(b["preview_sha256"], a["preview_sha256"])
        self.assertNotEqual(b["preview_captured_at_utc"], a["preview_captured_at_utc"])
        self.assertEqual(b["original_exhibition_sha256"], a["original_exhibition_sha256"])
        self.assertEqual(b["original_exhibition_captured_at_utc"], a["original_exhibition_captured_at_utc"])
        changed = dict(og)
        changed["艇3_値3"] = "7.40"
        third = build(date(2026, 10, 26), {
            "stt": [st], "tkz": [tk], "original": [changed]},
            prior=later, collected_at=datetime(2026, 10, 26, 4, tzinfo=timezone.utc))
        c = third["records"][0]
        self.assertNotEqual(c["original_exhibition_sha256"], b["original_exhibition_sha256"])
        self.assertEqual(c["original_exhibition_captured_at_utc"], datetime(
            2026, 10, 26, 4, tzinfo=timezone.utc).isoformat())

    def test_six_boats_without_weather(self):
        code = "202610260601"
        st = {"レースコード": code, "締切時刻": "10:42",
              "取得日時": "2026-10-26T10:35:00+09:00"}
        tk = {"レースコード": code}
        for i in range(1, 7):
            st[f"艇{i}_コース"] = str(i)
            st[f"艇{i}_スタート展示"] = "0.10"
            tk[f"艇{i}_展示タイム"] = "6.80"
        data = build(date(2026, 10, 26), {
            "stt": [st], "tkz": [tk]
        })
        self.assertEqual(data["coverage"]["race_count"], 1)
        self.assertEqual(len(data["records"][0]["boats"]), 6)
        self.assertIsNone(data["records"][0]["weather"]["wind_mps"])
        self.assertEqual(data["records"][0]["source_status"],
                         "historical_research_only_not_frozen_forecast")

if __name__ == "__main__":
    unittest.main()
