"""Offline safety and content tests for official vs Open API weather diff."""
from datetime import datetime, timedelta
import unittest

from weather_lab.official_beforeinfo_audit import (
    audit, candidates, compare, merge_archive, parse_official, SCHEMA,
)

NOW = datetime.fromisoformat("2026-11-21T10:47:00+09:00")
CUTOFF = "2026-11-21 11:00:00"


def official_html(*, wind="3", code="5", wave="4", label="10:45現在"):
    return (
        '<html><p class="weather1_title">水面気象情報 ' + label + '</p>'
        '<div class="weather1_bodyUnit is-wind">'
        '<span class="weather1_bodyUnitLabelTitle">風速</span>'
        '<span class="weather1_bodyUnitLabelData">' + wind + 'm</span></div>'
        '<div class="weather1_bodyUnit is-windDirection">'
        '<p class="weather1_bodyUnitImage is-wind' + code + '"></p></div>'
        '<div class="weather1_bodyUnit is-wave">'
        '<span class="weather1_bodyUnitLabelTitle">波高</span>'
        '<span class="weather1_bodyUnitLabelData">' + wave + 'cm</span></div>'
        "</html>"
    )


def api_payload(*, preview=None, cutoff=CUTOFF):
    if preview is None:
        preview = {"wind_speed": 3, "wind_direction_number": 5, "wave_height": 4}
    return {"programs": {"stadiums": {
        "18": {"races": {
            "1": {"closed_at": cutoff, "preview": preview},
            "2": {"closed_at": "2026-11-21 11:30:00", "preview": preview},
        }},
        "19": {"races": {
            "1": {"closed_at": "2026-11-20 11:00:00", "preview": preview}
        }},
    }}}


def official_fetch(html=None, when=NOW):
    return lambda url: (html or official_html(), when)


class OfficialWeatherAuditTests(unittest.TestCase):
    def test_official_extracts_three_fields_and_clock(self):
        source = parse_official(official_html(), 1, NOW)
        self.assertEqual(source["status"], "OBSERVATION_FRESH")
        self.assertEqual(source["values"], {
            "wind_speed": 3, "wind_direction_number": 5, "wave_height": 4})
        self.assertEqual(source["observed_at_jst"], "2026-11-21T10:45:00+09:00")
        self.assertEqual(len(source["source_block_sha256"]), 64)

    def test_time_label_can_be_stale_or_ambiguous(self):
        self.assertEqual(
            parse_official(official_html(label="09:40現在"), 1, NOW)["status"],
            "OBSERVATION_STALE")
        self.assertEqual(
            parse_official(official_html(label="1R時点"), 1, NOW)["status"],
            "OBSERVATION_CLOCK_UNKNOWN")
        self.assertEqual(
            parse_official(official_html(label="11R時点"), 1, NOW)["status"],
            "OBSERVATION_LABEL_UNVERIFIED")

    def test_absent_section_is_not_fabricated(self):
        self.assertEqual(parse_official("<html>no weather</html>", 1, NOW)["status"],
                         "WEATHER_SECTION_MISSING")
        self.assertIsNone(parse_official("<html>no weather</html>", 1, NOW)["values"])

    def test_invalid_wind_direction_cannot_be_compared(self):
        doc = parse_official(official_html(code="18"), 1, NOW)
        self.assertIsNone(doc["values"]["wind_direction_number"])

    def test_candidates_restrict_day_and_cutoff_window(self):
        rows = candidates(api_payload(), NOW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["venue_code"], "18")
        self.assertEqual(rows[0]["race"], 1)
        self.assertEqual(rows[0]["openapi_preview"]["wind_direction_number"], 5)

    def test_compare_matching_values_preserves_timing_warning(self):
        row = candidates(api_payload(), NOW)[0]
        result = compare(row, official_fetch())
        self.assertEqual(result["status"], "VALUES_MATCH_OBSERVATION_TIME_NOT_PAIRED")
        self.assertFalse(result["same_observation_time_proven"])
        self.assertFalse(result["formal_forecast_changed"])
        self.assertEqual(result["differences"], {})

    def test_detect_each_weather_field_difference(self):
        row = candidates(api_payload(), NOW)[0]
        different = compare(row, official_fetch(official_html(wind="5", code="13", wave="9")))
        self.assertEqual(different["status"], "DIFFERENCE_POSSIBLE_SOURCE_LAG")
        self.assertEqual(set(different["differences"]), {
            "wind_speed", "wind_direction_number", "wave_height"})
        self.assertTrue(all(v["status"] == "VALUE_DIFF"
                            for v in different["differences"].values()))

    def test_unverified_prior_race_weather_never_claims_match(self):
        row = candidates(api_payload(), NOW)[0]
        result = compare(row, official_fetch(official_html(label="1R時点")))
        self.assertEqual(result["status"], "OFFICIAL_TIMING_NOT_VERIFIED")

    def test_official_capture_at_4_minutes_is_too_late(self):
        row = candidates(api_payload(), NOW)[0]
        late = datetime.fromisoformat("2026-11-21T10:56:00+09:00")
        result = compare(row, official_fetch(when=late))
        self.assertEqual(result["status"], "TOO_LATE_NOT_ELIGIBLE")

    def test_openapi_missing_weather_is_diagnostic_not_zero(self):
        row = candidates(api_payload(preview={}), NOW)[0]
        result = compare(row, official_fetch())
        self.assertEqual(result["status"], "INCOMPLETE_COMPARISON")
        self.assertTrue(all(v["status"] == "FIELD_MISSING" for v in result["differences"].values()))

    def test_no_openapi_preview_has_distinct_status(self):
        row = candidates(api_payload(), NOW)[0]
        row["openapi_preview"] = None
        result = compare(row, official_fetch())
        self.assertEqual(result["status"], "OPENAPI_PREVIEW_MISSING")

    def test_no_network_does_not_generate_fake_match(self):
        row = candidates(api_payload(), NOW)[0]
        def broken(url):
            raise TimeoutError("network timeout")
        result = compare(row, broken)
        self.assertEqual(result["status"], "OFFICIAL_FETCH_FAILED")
        self.assertNotIn("values", result["official"])

    def test_audit_keeps_provenance_and_no_formal_changes(self):
        result = audit(api_payload(), NOW, official_fetch())
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["event_date"], "2026-11-21")
        self.assertEqual(result["record_count"], 1)
        self.assertTrue(result["no_formal_bet_or_model_changes"])
        self.assertEqual(result["status_counts"],
                         {"VALUES_MATCH_OBSERVATION_TIME_NOT_PAIRED": 1})
        self.assertIn("boatrace.jp", result["records"][0]["official_url"])

    def test_append_only_archive_retains_first_capture(self):
        first = audit(api_payload(), NOW, official_fetch())
        archive = merge_archive(None, first)
        self.assertEqual(len(archive["records"]), 1)
        duplicate = merge_archive(archive, first)
        self.assertEqual(len(duplicate["records"]), 1)
        second_now = NOW + timedelta(minutes=2)
        second = audit(api_payload(), second_now,
                       official_fetch(official_html(label="10:48現在"), second_now))
        merged = merge_archive(archive, second)
        self.assertEqual(len(merged["records"]), 2)
        self.assertEqual(merged["records"][0], archive["records"][0])
        self.assertTrue(merged["formal_forecasts_unchanged"])
        with self.assertRaises(ValueError):
            merge_archive({"schema": SCHEMA, "event_date": "2026-11-20"}, first)


if __name__ == "__main__":
    unittest.main()
