"""Offline candidate-only CLI: python -m vision_ai --input tracker.json --output candidates.json."""
import argparse
import json
from pathlib import Path
from .analyzer import analyze
from .report_io import write_report


def main():
    parser = argparse.ArgumentParser(description="BOAT VISION AI research-only motion candidates")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = analyze(json.loads(args.input.read_text(encoding="utf-8")))
        write_report(result, args.output, inputs=(args.input,))
    except (ValueError, TypeError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print("BOAT VISION AI: "+result["status"]+", independently verified 0R, formal picks 0")


if __name__ == "__main__":
    main()
