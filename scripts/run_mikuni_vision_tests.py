"""Required CV/decoder integration checks: missing dependencies/skips fail CI."""
import importlib
import shutil
import sys
import unittest


def main():
    missing = [name for name in ("ffmpeg",) if shutil.which(name) is None]
    for module in ("cv2", "numpy"):
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(module)
    if missing:
        print("Required video dependencies missing: " + ", ".join(missing), file=sys.stderr)
        return 1
    suite = unittest.TestSuite()
    for pattern in ("test_mikuni_auto_vision.py", "test_mikuni_video_motion_pipeline.py",
                    "test_mikuni_six_boat_tracker.py", "test_mikuni_video_autocollect.py",
                    "test_mikuni_official_video_catalog.py"):
        suite.addTests(unittest.defaultTestLoader.discover("tests", pattern=pattern))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.skipped:
        print("Required video checks were skipped; refusing a successful CI result.", file=sys.stderr)
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
