"""Transient-error retry contract for exhibition data ingestion."""
import io
import unittest
from datetime import date
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from scripts.ingest_boatracecsv_exhibition import fetch


class FakeResponse:
    def __init__(self, data):
        self.data = data
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self):
        return self.data


CSV = "レースコード,締切時刻\n202611050101,10:00\n".encode("utf-8")


class ExhibitionCSVRetryTests(unittest.TestCase):
    @patch("scripts.ingest_boatracecsv_exhibition.time.sleep")
    @patch("scripts.ingest_boatracecsv_exhibition.urlopen")
    def test_transient_error_then_success(self, opener, sleep):
        opener.side_effect = [URLError("temporary"), FakeResponse(CSV)]
        rows = fetch("stt", date(2026, 11, 5))
        self.assertEqual(len(rows), 1)
        self.assertEqual(opener.call_count, 2)
        sleep.assert_called_once()

    @patch("scripts.ingest_boatracecsv_exhibition.time.sleep")
    @patch("scripts.ingest_boatracecsv_exhibition.urlopen")
    def test_unpublished_404_fails_without_retry(self, opener, sleep):
        opener.side_effect = HTTPError("test", 404, "not found", None, io.BytesIO())
        self.assertEqual(fetch("stt", date(2026, 11, 5)), [])
        self.assertEqual(opener.call_count, 1)
        sleep.assert_not_called()

    @patch("scripts.ingest_boatracecsv_exhibition.time.sleep")
    @patch("scripts.ingest_boatracecsv_exhibition.urlopen")
    def test_temporarily_empty_csv_then_success(self, opener, sleep):
        opener.side_effect = [FakeResponse(b"\xef\xbb\xbf"), FakeResponse(CSV)]
        self.assertEqual(len(fetch("tkz", date(2026, 11, 5))), 1)
        self.assertEqual(opener.call_count, 2)

    @patch("scripts.ingest_boatracecsv_exhibition.time.sleep")
    @patch("scripts.ingest_boatracecsv_exhibition.urlopen")
    def test_persistent_503_remains_unavailable(self, opener, sleep):
        opener.side_effect = HTTPError("test", 503, "unavailable", None, io.BytesIO())
        self.assertEqual(fetch("stt", date(2026, 11, 5)), [])
        self.assertEqual(opener.call_count, 3)


if __name__ == "__main__":
    unittest.main()
