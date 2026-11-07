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
        archive.write_bytes(b'x'*(ARCHIVE_LIMIT_BYTES+100))
        stat=app/"data"/"experiments"/"statistical-2026-11-06.json"
        stat.parent.mkdir(parents=True,exist_ok=True)
        stat.write_bytes(b'j'*(ARCHIVE_LIMIT_BYTES+200))
        archive_current=app/"data"/"live"/"2026-11-07.json"
        archive_current.write_bytes(b'f'*(ARCHIVE_LIMIT_BYTES+300))
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
