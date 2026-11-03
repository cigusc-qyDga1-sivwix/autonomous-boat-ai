"""Required independent tests; missing CV dependencies and any skips fail."""
import argparse
import importlib
from pathlib import Path
import shutil
import unittest


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--cv", action="store_true")
    args = parser.parse_args(argv)
    if args.cv:
        missing = ["ffmpeg"] if shutil.which("ffmpeg") is None else []
        for module in ("cv2", "numpy"):
            try:
                importlib.import_module(module)
            except ImportError:
                missing.append(module)
        if missing:
            print("Required vision dependencies missing: " + ", ".join(missing))
            return 1
    root = Path(__file__).resolve().parent
    suite = unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_*.py")
    if args.cv:
        suite.addTests(unittest.defaultTestLoader.discover(str(root / "cv_tests"), pattern="test_*.py"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.skipped:
        print("Skipped checks cannot prove a completed vision milestone")
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
