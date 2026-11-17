"""Research-only collector for Gamagori's OFFICIAL original exhibition times.

This is deliberately disconnected from BOAT LAB's frozen forecasts and model.
It does not trust third-party source timestamps as proof of pre-cutoff use.
Run for one race at a time, with respectful frequency and provider rules review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

VENUE_CODE = "07"
VENUE_NAME = "蒲郡"
OFFICIAL_HOST = "www.gamagori-kyotei.com"
ROOT = "https://" + OFFICIAL_HOST + "/asp/gamagori/sp/kyogi/kyogihtml/recomend/"
METRIC_RANGES = {"exhibition_time": (5.0, 10.0), "lap_time": (30.0, 55.0),
                 "turn_time": (4.0, 15.0), "straight_time": (5.0, 12.0)}


def official_url(day: date, race: int) -> str:
    if not 1 <= race <= 12:
        raise ValueError("race must be 1..12")
    return f"{ROOT}recomend{day:%Y%m%d}{VENUE_CODE}{race:02d}.htm"


class _Tables(HTMLParser):
    """Read only displayed table cells, not script or style content."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.tables = []
        self.text_chunks = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        if tag == "table":
            self.stack.append({"rows": [], "row": None, "cell": None})
        elif self.stack and tag == "tr":
            self.stack[-1]["row"] = []
        elif self.stack and tag in ("td", "th"):
            self.stack[-1]["cell"] = []

    def handle_data(self, data):
        if self.hidden:
            return
        self.text_chunks.append(data)
        if self.stack and self.stack[-1]["cell"] is not None:
            self.stack[-1]["cell"].append(data)

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.hidden:
            self.hidden -= 1
        if not self.stack:
            return
        top = self.stack[-1]
        if tag in ("td", "th") and top["cell"] is not None:
            if top["row"] is not None:
                top["row"].append("".join(top["cell"]).strip())
            top["cell"] = None
        elif tag == "tr" and top["row"] is not None:
            top["rows"].append(top["row"])
            top["row"] = None
        elif tag == "table":
            self.tables.append(self.stack.pop()["rows"])


def _number(text: str, name: str) -> float | None:
    cleaned = re.sub(r"\s+", "", text).replace("．", ".")
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", cleaned):
        return None
    num = float(cleaned)
    low, high = METRIC_RANGES[name]
    return num if low <= num <= high else None


def parse_official(html: str, day: date, race: int) -> list[dict]:
    """Fail closed unless the official page identifies the race and all 6 rows."""
    tables = _Tables()
    tables.feed(html)
    page = re.sub(r"\s+", "", "".join(tables.text_chunks))
    # A redirect, stale page or template must not be accepted as this race.
    if f"{day.month}/{day.day}" not in page or f"{race}R" not in page:
        raise ValueError("race date/number missing from official page")
    for table in tables.tables:
        label = "".join("".join(row) for row in table)
        if not all(s in label for s in ("一周", "まわり足", "直線", "展示")):
            continue
        boats = []
        for row in table:
            cells = [re.sub(r"\s+", "", x) for x in row]
            if len(cells) < 6 or not all(re.fullmatch("[1-6]", x) for x in cells[:2]):
                continue
            course, lane = int(cells[0]), int(cells[1])
            fields = ("exhibition_time", "lap_time", "turn_time", "straight_time")
            readings = {k: _number(v, k) for k, v in zip(fields, cells[2:6])}
            if any(value is None for value in readings.values()):
                raise ValueError("missing or invalid original measurement")
            boats.append({"lane": lane, "course": course, **readings})
        if (len(boats) == 6
                and {b["lane"] for b in boats} == set(range(1, 7))
                and {b["course"] for b in boats} == set(range(1, 7))):
            return sorted(boats, key=lambda b: b["lane"])
    raise ValueError("no unambiguous six-boat original exhibition table")


def _decode(raw: bytes, charset: str | None) -> str:
    for candidate in [charset, "utf-8-sig", "cp932", "euc_jp"]:
        if not candidate:
            continue
        try:
            return raw.decode(candidate)
        except (LookupError, UnicodeError):
            pass
    raise ValueError("unrecognized page encoding")


def collect(day: date, race: int, timeout: int = 10) -> dict:
    endpoint = official_url(day, race)
    captured = datetime.now(timezone.utc).isoformat()
    result = {
        "schema": "boatlabs.official_original_exhibition_research.v0.1",
        "event_date": day.isoformat(), "venue": VENUE_NAME,
        "venue_code": VENUE_CODE, "race": race,
        "race_code": f"{day:%Y%m%d}{VENUE_CODE}{race:02d}",
        "source_url": endpoint, "provider": "BOAT RACE 蒲郡公式サイト",
        "captured_at_utc": captured,
        "status": "MISSING", "boats": [],
        "verified_against_openapi_six_boats": False,
        "eligible_for_formal_prediction": False,
        "reason": "source data have not been cross-checked against the same pre-cutoff OpenAPI snapshot",
        "research_only": True,
    }
    try:
        request = Request(endpoint, headers={
            "User-Agent": "BOAT-LAB-research/0.1 (one-race-per-request)"})
        with urlopen(request, timeout=timeout) as response:
            if response.geturl().split("/")[2] != OFFICIAL_HOST:
                raise ValueError("unexpected source redirect")
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError("response too large")
            charset = response.headers.get_content_charset()
        parsed = parse_official(_decode(raw, charset), day, race)
        result.update({
            "status": "SIX_BOAT_SOURCE_CAPTURED_NOT_CROSSCHECKED",
            "boats": parsed,
            "raw_html_sha256": hashlib.sha256(raw).hexdigest(),
            "measurement_sha256": hashlib.sha256(json.dumps(
                parsed, ensure_ascii=False, sort_keys=True,
                separators=(",", ":")).encode("utf-8")).hexdigest(),
        })
    except (HTTPError, URLError, TimeoutError, UnicodeError,
            ValueError, OSError) as exc:
        if isinstance(exc, HTTPError):
            reason = f"HTTP_{exc.code}"
        else:
            reason = type(exc).__name__ + ": " + str(exc)[:160]
        result["reason"] = reason
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD JST")
    ap.add_argument("--race", type=int, required=True)
    ap.add_argument("--output-dir", type=Path,
                    default=Path("app/data/exhibition/official-source-research"))
    args = ap.parse_args()
    day = date.fromisoformat(args.date)
    result = collect(day, args.race)
    # Save a new source capture, not a replacement of a forecast or earlier proof.
    stamp = result["captured_at_utc"].replace("-", "").replace(":", "").replace("+", "_")
    target = args.output_dir / args.date / (
        f"gamagori_{args.race:02d}R_{stamp}.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as out:
        json.dump(result, out, ensure_ascii=False, indent=2)
        out.write("\n")
    print(json.dumps({"path": str(target), "status": result["status"],
                      "boats": len(result["boats"]),
                      "formal_eligible": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
