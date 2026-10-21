"""Manual one-shot test: python scripts/check_wakamatsu_preview.py 20261021 6"""
import json
import sys
from boat_ai.preview_api import fetch_preview

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python scripts/check_wakamatsu_preview.py YYYYMMDD RACE")
    try:
        result = fetch_preview(sys.argv[1], int(sys.argv[2]))
    except Exception as exc:
        print(json.dumps({"status": "fetch_error", "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "complete":
        raise SystemExit(2)
