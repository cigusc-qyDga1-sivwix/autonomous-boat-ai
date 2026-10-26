"""Regression: six-boat exhibition must not disappear when weather CSV is unavailable."""
import unittest
from datetime import date
from ingest_boatracecsv_exhibition import build

class OptionalWeatherTests(unittest.TestCase):
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
