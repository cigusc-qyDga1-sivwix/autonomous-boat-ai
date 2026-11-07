"""GitHub Pages package stays small; immutable history stays in the repo."""
import json
import tempfile
import unittest
from pathlib import Path
from scripts.build_pages_site import (
    build_site, ARCHIVE_LIMIT_BYTES, REQUIRED, DATED_JSON
)


class PagesArtifactTests(unittest.TestCase):
    def fixture(self,root):
        app=root/"app"
        for name in REQUIRED:
            p=app/name
            p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(b'{}')
        keep=app/"data"/"exhibition"/"2026-11-07.json"
        keep.parent.mkdir(parents=True,exist_ok=True)
        keep.write_text('{"preserved":true}')
        archive=app/"data"/"live"/"2026-11-06.json"
        sample = {
            "event_date": "2026-11-06",
            "race_records": {"14-1": {
                "venue": "鳴門", "race": 1,
                "versions": [{
                    "venue": "鳴門", "race": 1,
                    "sha256": "a" * 64,
                    "cutoff_iso_jst": "2026-11-06T08:35:00+09:00",
                    "frozen_at_utc": "2026-11-05T23:00:00Z",
                    "cutoff_jst": "08:35",
                    "phase": "exhibition",
                    "bets": [{"combination": "1-2-3", "virtual_yen": 50000}],
                    "racers": [{"lane": i, "course": i,
                                "exhibition_st": 0.11,
                                "exhibition_time": 6.83,
                                "unrelated_metadata": "discard"} for i in range(1, 7)],
                    "extra_prediction_history": "discard"
                }],
                "official_pay": {
                    "finish": "1-2-3", "payout_per_100": 1000,
                    "verified": True, "source": "boatrace_official_pay",
                    "refunded_boats": [4],
                    "refund_source_url": "https://www.boatrace.jp/owpc/pc/race/raceresult?rno=1&jcd=14&hd=20261106",
                }
            }}
        }
        archive.write_text(json.dumps(sample) + " " * (ARCHIVE_LIMIT_BYTES+100))
        stat=app/"data"/"experiments"/"statistical-2026-11-06.json"
        stat.parent.mkdir(parents=True,exist_ok=True)
        stat.write_bytes(b'j'*(ARCHIVE_LIMIT_BYTES+200))
        archive_current=app/"data"/"live"/"2026-11-07.json"
        sample["event_date"] = "2026-11-07"
        sample["race_records"]["14-1"]["versions"][0]["cutoff_iso_jst"] = "2026-11-07T08:35:00+09:00"
        sample["race_records"]["14-1"]["versions"][0]["frozen_at_utc"] = "2026-11-06T23:00:00Z"
        sample["race_records"]["14-1"]["official_pay"]["refund_source_url"] = (
            "https://www.boatrace.jp/owpc/pc/race/raceresult?rno=1&jcd=14&hd=20261107"
        )
        archive_current.write_text(json.dumps(sample) + " " * (ARCHIVE_LIMIT_BYTES+300))
        return app,archive,stat,archive_current

    def test_archives_stay_original_and_live_assets_ship(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            app,archive,stat,active=self.fixture(root)
            dist=root/"pages"
            orig=[x.stat().st_size for x in (archive,stat,active)]
            summary=build_site(app,dist)
            self.assertEqual(summary["archived_count"],3)
            self.assertLess(summary["shipped_bytes"],ARCHIVE_LIMIT_BYTES)
            for name in REQUIRED:
                self.assertTrue((dist/name).exists(),name)
            self.assertTrue((dist/"data/exhibition/2026-11-07.json").exists())
            self.assertFalse((dist/"data/live/2026-11-06.json").exists())
            self.assertFalse((dist/"data/live/2026-11-07.json").exists())
            for date in ("2026-11-06", "2026-11-07"):
                compact_path = dist / ("data/live/settlement/" + date + ".json")
                self.assertTrue(compact_path.exists(), date)
                self.assertLess(compact_path.stat().st_size, 5000)
                compact = json.loads(compact_path.read_text())
                self.assertEqual(compact["event_date"], date)
                record = compact["race_records"]["14-1"]
                snap = record["versions"][0]
                self.assertEqual(snap["sha256"], "a" * 64)
                self.assertEqual(snap["bets"][0]["virtual_yen"], 50000)
                self.assertEqual(record["official_pay"]["refunded_boats"], [4])
                self.assertEqual(snap["racers"][0]["exhibition_time"], 6.83)
                self.assertNotIn("unrelated_metadata", snap["racers"][0])
                self.assertNotIn("extra_prediction_history", snap)
            self.assertFalse((dist/"data/experiments/statistical-2026-11-06.json").exists())
            self.assertEqual([x.stat().st_size for x in (archive,stat,active)],orig)
            manifest=json.loads((dist/"data/archive-on-github.json").read_text())
            self.assertEqual(manifest["archived_count"],3)
            self.assertTrue(all(x["source"].startswith(
                "https://github.com/cigusc-qyDga1-sivwix/autonomous-boat-ai/blob/main/app/")
                for x in manifest["archived"]))
            self.assertTrue(DATED_JSON.fullmatch("data/live/2026-11-07.json"))

    def test_missing_required_live_file_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            app,*_=self.fixture(root)
            (app/"data/live/latest.json").unlink()
            with self.assertRaisesRegex(ValueError,"Missing required Pages asset"):
                build_site(app,root/"pages")
                
    def test_no_source_deletion_on_rebuild(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            app,*_=self.fixture(root)
            dist=root/"pages"
            build_site(app,dist)
            # Simulate old stale site file removed only in output folder.
            (dist/"obsolete.html").write_text("old")
            build_site(app,dist)
            self.assertFalse((dist/"obsolete.html").exists())
            self.assertTrue((app/"data/live/latest.json").exists())


if __name__=="__main__":
    unittest.main()
