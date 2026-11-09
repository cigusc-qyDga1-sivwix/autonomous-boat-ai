"""Transport regressions for timely original-exhibition CSV capture.

No network access and no changes to historical pre-cutoff predictions.
"""
import io
import unittest
from datetime import date
from unittest.mock import patch
from urllib.error import HTTPError

from scripts import ingest_boatracecsv_exhibition as ingest


DAY = date(2026, 11, 10)
HEADER = "レースコード,取得日時\n"
CSV = HEADER + "202611102101,2026-11-10T08:25:24+09:00\n"


class RawSourceFallbackTests(unittest.TestCase):
    def test_canonical_github_first_when_pages_would_be_missing(self):
        requested = []

        def open_source(request, timeout):
            requested.append(request.full_url)
            if "raw.githubusercontent.com" in request.full_url:
                return io.BytesIO(CSV.encode())
            raise AssertionError("Lagging Pages must not be queried after successful raw")

        with patch.object(ingest, "urlopen", side_effect=open_source):
            rows = ingest.fetch("original", DAY)
        self.assertEqual(rows[0]["レースコード"], "202611102101")
        self.assertEqual(len(requested), 1)
        self.assertEqual(
            requested[0],
            "https://raw.githubusercontent.com/BoatraceCSV/boatracecsv.github.io/main/data/previews/original_exhibition/2026/11/10.csv",
        )

    def test_falls_back_to_pages_when_canonical_url_returns_404(self):
        requested = []

        def open_source(request, timeout):
            requested.append(request.full_url)
            if "raw.githubusercontent.com" in request.full_url:
                raise HTTPError(request.full_url, 404, "not published", {}, None)
            return io.BytesIO(CSV.encode())

        with patch.object(ingest, "urlopen", side_effect=open_source):
            rows = ingest.fetch("stt", DAY)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(requested), 2)
        self.assertTrue(requested[1].startswith("https://boatracecsv.github.io/data/previews/stt/"))

    def test_empty_raw_file_tries_pages_instead_of_marking_success(self):
        with patch.object(ingest, "urlopen", side_effect=[
            io.BytesIO(HEADER.encode()), io.BytesIO(CSV.encode())
        ]) as opened:
            rows = ingest.fetch("tkz", DAY)
        self.assertEqual(len(rows), 1)
        self.assertEqual(opened.call_count, 2)

    def test_both_sources_missing_do_not_fabricate_exhibition(self):
        def missing(request, timeout):
            raise HTTPError(request.full_url, 404, "not published", {}, None)

        with patch.object(ingest, "urlopen", side_effect=missing):
            self.assertEqual(ingest.fetch("original", DAY), [])


if __name__ == "__main__":
    unittest.main()
