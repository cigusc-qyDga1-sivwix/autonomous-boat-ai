"""Mikuni video-source research integrity tests. No network/media rights assumed."""
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.error import HTTPError

from scripts.mikuni_video_autocollect import (
    SCHEMA, media_url, _check_url, _valid_host, _media_magic,
    _rows, run, video_color_audit
)

DAY="2026-10-28"
HOST="approved.mikuni.example"
TEMPLATE="https://approved.mikuni.example/video/{yyyymmdd}/mikuni-{race2}.mp4"
BEFORE=datetime.fromisoformat("2026-10-28T00:20:00+00:00")


def archive():
    boats=[{"lane":i} for i in range(1,7)]
    return {"event_date":DAY,"records":[
        {"venue_code":"10","race_code":"202610281001","race":1,"boats":boats},
        {"venue_code":"23","race_code":"202610282301","race":1,"boats":boats},
        {"venue_code":"10","race_code":"202610281002","race":2,"boats":boats},
    ]}


class MikuniCollectorTests(unittest.TestCase):
    def test_no_url_guessing_without_approved_template(self):
        ledger=run(DAY,archive(),None,None,[],now=BEFORE)
        self.assertEqual(ledger["schema"],SCHEMA)
        self.assertFalse(ledger["source_configured"])
        self.assertEqual(ledger["summary"]["exhibition_rows_seen"],2)
        self.assertEqual(ledger["summary"]["video_races_observed"],0)
        self.assertEqual(ledger["races"]["1"]["status"],"AUTHORIZED_SOURCE_CONFIGURATION_MISSING")
        self.assertEqual(ledger["races"]["3"]["status"],"AWAITING_EXHIBITION_NUMERIC_RESEARCH_ROW")
        self.assertEqual(ledger["summary"]["confirmed_boat_tracks"],0)
        self.assertEqual(ledger["summary"]["measured_turns"],0)
        self.assertEqual(ledger["summary"]["measured_post_start_stretches"],0)
        self.assertNotIn("source_url",json.dumps(ledger))
        self.assertNotIn("token",json.dumps(ledger))

    def test_https_direct_video_and_template_safety(self):
        self.assertEqual(
            media_url(TEMPLATE,DAY,2,{HOST}),
            "https://approved.mikuni.example/video/20261028/mikuni-02.mp4")
        for host in ("localhost","127.0.0.1","[::1]","192.168.0.1","internal","a.local"):
            self.assertFalse(_valid_host(host))
        for url in (
            "http://approved.mikuni.example/video/1.mp4",
            "https://127.0.0.1/stream.mp4",
            "https://localhost/a",
            "https://evil.mikuni.example/video/a.mp4",
            "https://approved.mikuni.example:444/video/a.mp4",
            "https://user:secret@approved.mikuni.example/a",
            "file:///etc/passwd",
        ):
            with self.assertRaises(ValueError,msg=url):
                _check_url(url,{HOST})
        with self.assertRaises(ValueError):
            media_url(TEMPLATE,"2026-02-30",1,{HOST})
        with self.assertRaises(ValueError):
            media_url(TEMPLATE,DAY,13,{HOST})
        with self.assertRaises(ValueError):
            media_url("https://approved.mikuni.example/{unknown}",DAY,1,{HOST})

    def test_direct_mp4_magic(self):
        self.assertTrue(_media_magic(b"\0\0\0\x18ftypisom\0\0\0\0"))
        self.assertTrue(_media_magic(b"\x1a\x45\xdf\xa3payload"))
        self.assertFalse(_media_magic(b"<html><body>not a video</body>"))
        self.assertFalse(_media_magic(b"#EXTM3U\nsomething"))

    def test_source_observation_is_not_six_boat_tracking(self):
        seen=[]
        def fake_fetch(url,target,hosts):
            seen.append((url,hosts))
            target.write_bytes(b"\0\0\0\x18ftypisom\0\0\0\0")
            return {"sha256":"e"*64,"file_size":16,"content_type":"video/mp4"}
        def fake_analysis(_):
            return {"status":"PIXEL_RESEARCH_ONLY_NOT_BOAT_IDENTITIES",
                    "sample_frames":10,"verified_boats":0,
                    "verified_turns":0,"verified_post_start_stretches":0}
        first=run(DAY,archive(),None,TEMPLATE,{HOST},
                  fetcher=fake_fetch,analyzer=fake_analysis,now=BEFORE)
        self.assertEqual(len(seen),2)
        self.assertEqual(first["summary"]["video_races_observed"],2)
        self.assertEqual(first["races"]["1"]["status"],"MEDIA_OBSERVED_PIXEL_RESEARCH_ONLY")
        self.assertEqual(first["races"]["1"]["video_observation"]["verified_turns"],0)
        self.assertNotIn(TEMPLATE,json.dumps(first))
        second=run(DAY,archive(),first,TEMPLATE,{HOST},
                   fetcher=lambda *_:self.fail("video downloaded twice"),
                   analyzer=fake_analysis,now=BEFORE)
        self.assertEqual(second["races"]["1"],first["races"]["1"])
        self.assertEqual(second["summary"]["video_races_observed"],2)

    def test_http_failures_are_sanitized(self):
        def denied(url,target,hosts):
            raise HTTPError(url,404,"not ready",None,None)
        ledger=run(DAY,archive(),None,TEMPLATE,{HOST},
                   fetcher=denied,now=BEFORE)
        self.assertEqual(ledger["races"]["1"]["reason"],"HTTP_404_NOT_READY")
        self.assertEqual(ledger["summary"]["video_races_observed"],0)
        self.assertNotIn("https://",json.dumps(ledger))
        self.assertEqual(ledger["races"]["1"]["status"],"SOURCE_OR_ANALYSIS_NOT_READY")

    def test_archive_mismatch_and_boat_count_rejected(self):
        corrupted=archive()
        corrupted["records"][0]["boats"]=[{"lane":1}]
        self.assertEqual(_rows(corrupted,DAY),{2})
        corrupted["event_date"]="2026-10-27"
        self.assertEqual(_rows(corrupted,DAY),set())

    def test_synthetic_video_cv2_pixel_analysis(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("opencv not installed")
        with TemporaryDirectory() as tmp:
            file=Path(tmp)/"synthetic.avi"
            writer=cv2.VideoWriter(str(file),cv2.VideoWriter_fourcc(*"MJPG"),10,(160,90))
            if not writer.isOpened():
                self.skipTest("MJPG codec unavailable")
            for i in range(30):
                img=np.full((90,160,3),(60,60,60),dtype=np.uint8)
                cv2.circle(img,(30+i,40),10,(0,0,255),-1)
                writer.write(img)
            writer.release()
            result=video_color_audit(file)
            self.assertEqual(result["status"],"PIXEL_RESEARCH_ONLY_NOT_BOAT_IDENTITIES")
            self.assertGreater(result["sample_frames"],0)
            self.assertGreater(result["region_counts"]["red_candidate"],0)
            self.assertEqual(result["verified_boats"],0)
            self.assertIsNone(result["estimated_turn_radius_m"])


if __name__=="__main__":
    unittest.main()
