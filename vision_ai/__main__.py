"""Offline candidate-only CLI: python -m vision_ai --input tracker.json --output candidates.json."""
import argparse
import json
from pathlib import Path
from .analyzer import analyze


def main():
    parser = argparse.ArgumentParser(description="BOAT VISION AI research-only motion candidates")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    destination = args.output.resolve()
    if any(p in ("live", "official-pay", "formal", "forecasts", "results") for p in destination.parts):
        parser.error("Writing into production forecast/result folders is prohibited")
    if args.input.resolve() == destination:
        parser.error("Refusing to overwrite the input tracker evidence")
    try:
        result = analyze(json.loads(args.input.read_text(encoding="utf-8")))
    except (ValueError, TypeError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix+".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    temporary.replace(destination)
    print("BOAT VISION AI: "+result["status"]+", independently verified 0R, formal picks 0")


if __name__ == "__main__":
    main()
