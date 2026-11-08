"""Midnight source 404 must not erase immutable forecasts or fake cancellations."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError

import pytest
from scripts import autonomous_daily as A


def test_unpublished_day_404_preserves_previous_predictions():
    with TemporaryDirectory() as root:
        path = Path(root)
        (path / "latest.json").write_text('{"event_date":"2026-11-08","forecast_races":[{"sha256":"unchanged"}]}',encoding="utf-8")
        old = (path / "latest.json").read_bytes()
        out = StringIO()
        missing = HTTPError("https://boatraceopenapi.github.io", 404, "Not Found", {}, None)
        argv = ["autonomous_daily.py","--now-iso","2026-11-09T00:05:00+09:00","--out-dir",str(path)]
        with patch.object(sys, "argv", argv), patch.object(A, "retrieve", side_effect=missing), redirect_stdout(out):
            A.main()
        status = json.loads(out.getvalue().strip())
        assert status["status"] == "PROGRAM_SOURCE_NOT_YET_PUBLISHED"
        assert status["forecast_created"] is False
        assert status["retry_by_next_scheduled_run"] is True
        assert (path / "latest.json").read_bytes() == old
        assert not (path / "2026-11-09.json").exists()


def test_other_http_errors_are_not_relabelled_as_unpublished():
    with TemporaryDirectory() as root:
        invalid = HTTPError("https://example.invalid", 500, "Server Error", {}, None)
        argv = ["autonomous_daily.py","--now-iso","2026-11-09T00:05:00+09:00","--out-dir",root]
        with patch.object(sys, "argv", argv), patch.object(A, "retrieve", side_effect=invalid):
            with pytest.raises(HTTPError) as exc:
                A.main()
        assert exc.value.code == 500
