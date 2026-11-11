"""Tests of archive-wide availability; offline synthetic records, no provider calls."""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.venue_source_coverage import VENUES, audit_archives, main


def record(venue, wind, direction=None, race=1):
    return {
        "race_code": f"20261105{VENUES.index(venue)+1:02d}{race:02d}",
        "venue": venue, "race": race, "cutoff_jst": "09:39",
        "source_observed_jst": "2026-11-05T09:30:31+09:00",
        "weather": {"wind_mps": wind, "wave_cm": 2,
                    "wind_direction_number": direction, "observed_time_jst": "0850"}
    }


class VenueSourceCoverageTests(unittest.TestCase):
    def test_all_24_venues_and_calm_not_counted_as_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"2026-11-05.json"
            rows=[record(v, 0 if i==0 else 2, None if i==0 else 4)
                  for i,v in enumerate(VENUES)]
            p.write_text(json.dumps({"event_date":"2026-11-05","records":rows},ensure_ascii=False))
            report=audit_archives([p])
            s=report["summary"]
            self.assertEqual(s["races"],24)
            self.assertEqual(s["venues_with_wind"],24)
            self.assertEqual(s["venues_with_wave"],24)
            self.assertEqual(s["venues_with_tide"],0)
            self.assertEqual(s["wind_direction_undefined_calm"],1)
            self.assertEqual(s["wind_direction_undefined_noncalm"],0)
            self.assertEqual(s["weather_stale_gt20min"],24)
            self.assertFalse(report["formal_model_changed"])
            self.assertEqual(len(report["venues"]),24)

    def test_non_calm_missing_direction_counted_separately(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"2026-11-05.json"
            p.write_text(json.dumps({"event_date":"2026-11-05","records":[record("三国",3)]},
                                    ensure_ascii=False))
            self.assertEqual(audit_archives([p])["summary"]["wind_direction_undefined_noncalm"],1)

    def test_duplicate_day_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"2026-11-05.json"
            p.write_text(json.dumps({"event_date":"2026-11-05","records":[]}))
            with self.assertRaises(ValueError):
                audit_archives([p,p])

    def test_cli_report_write_is_only_under_reports(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"2026-11-05.json"
            p.write_text(json.dumps({"event_date":"2026-11-05","records":[record("三国",2,4)]},
                                    ensure_ascii=False))
            with self.assertRaises(SystemExit):
                main(["--archive-dir",temp,"--start","2026-11-05",
                      "--end","2026-11-05","--output",str(p)])
            self.assertEqual(json.loads(p.read_text())["event_date"],"2026-11-05")


if __name__=="__main__":
    unittest.main()
