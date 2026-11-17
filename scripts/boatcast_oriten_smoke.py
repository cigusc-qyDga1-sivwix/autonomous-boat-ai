"""One-request BOATCAST bc_oriten source probe. Research only; no forecast writes.

Source format: shimomo/boatrace-php-scraper-boatcast TimeScraper.php.
Access terms must be reviewed before any operational/batch collection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

NAMES = {"一周": "lap_time", "半周ラップ": "half_lap_time",
         "まわり足": "turn_time", "直線": "straight_time"}
RANGES = {"lap_time": (30, 55), "half_lap_time": (15, 25),
          "turn_time": (4, 15), "straight_time": (5, 12)}


def url(day: date, venue: int, race: int) -> str:
    if not 1 <= venue <= 24 or not 1 <= race <= 12:
        raise ValueError("invalid venue or race")
    return (f"https://race.boatcast.jp/txt/{venue:02d}/"
            f"bc_oriten_{day:%Y%m%d}_{venue:02d}_{race:02d}.txt")


def label(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def parse(body: bytes) -> dict:
    """Require source sentinel, measured=1, 6 distinct entries and all offered values.

    Empty / unmeasured / invalid data fail closed. A venue not measuring
    straight or lap has a legitimately absent key; no interpolation is done.
    """
    errors = []
    for encoding in ("utf-8-sig", "cp932"):
        try:
            data = body.decode(encoding)
            rows = [line.rstrip("\r").split("\t") for line in data.splitlines()
                    if line.strip()]
            if len(rows) < 9 or rows[0][0].strip() != "data=":
                raise ValueError("missing sentinel or six-boat TSV")
            if rows[1][0].strip() != "1":
                raise ValueError("not yet measured: " + rows[1][0][:25])
            count = int(rows[1][1])
            if count not in (2, 3) or len(rows[2]) < count:
                raise ValueError("invalid metric count")
            metrics = [NAMES.get(label(x)) for x in rows[2][:count]]
            if any(m is None for m in metrics) or len(set(metrics)) != count:
                raise ValueError("unknown/duplicate metric label")
            boats = {}
            for cells in rows[3:]:
                if not cells[0].isdigit():
                    continue
                lane = int(cells[0])
                if lane not in range(1, 7) or lane in boats or len(cells) < count + 2:
                    raise ValueError("ambiguous boat index")
                name = label(cells[1])
                if not name:
                    raise ValueError("missing racer name")
                entry = {"lane": lane, "name": name}
                for metric, raw in zip(metrics, cells[2:2+count]):
                    v = float(raw)
                    lo, hi = RANGES[metric]
                    if not math.isfinite(v) or not lo <= v <= hi:
                        raise ValueError("missing/invalid " + metric)
                    entry[metric] = v
                boats[lane] = entry
            if set(boats) != set(range(1, 7)):
                raise ValueError("six boats not complete")
            return {"metrics": metrics, "boats": [boats[n] for n in range(1, 7)],
                    "encoding": encoding}
        except (ValueError, IndexError, UnicodeError) as e:
            errors.append(type(e).__name__ + ":" + str(e)[:70])
    raise ValueError("; ".join(errors))


def probe(day: date, venue: int, race: int, timeout: int = 12) -> dict:
    target = url(day, venue, race)
    output = {"schema": "boatlabs.boatcast_oriten_smoke.v1",
              "date": day.isoformat(), "venue_code": f"{venue:02d}",
              "race_number": race, "source_url": target,
              "requested_at_utc": datetime.now(timezone.utc).isoformat(),
              "http_status": None, "status": "SOURCE_UNAVAILABLE",
              "metrics": [], "boats": [],
              "research_only": True, "pre_cutoff_verified": False,
              "formal_forecast_eligible": False}
    try:
        req = Request(target, headers={"User-Agent": "BOAT-LAB-one-race-research/0.1"})
        with urlopen(req, timeout=timeout) as rsp:
            output["http_status"] = rsp.status
            if rsp.geturl() != target:
                raise ValueError("unexpected redirect")
            raw = rsp.read(100001)
            if len(raw) > 100000:
                raise ValueError("oversize")
        output["captured_at_utc"] = datetime.now(timezone.utc).isoformat()
        output["source_body_sha256"] = hashlib.sha256(raw).hexdigest()
        parsed = parse(raw)
        output.update({"status": "SIX_BOAT_PARSED_RESEARCH_ONLY",
                       "metrics": parsed["metrics"], "boats": parsed["boats"],
                       "encoding": parsed["encoding"],
                       "measurement_sha256": hashlib.sha256(json.dumps(
                           parsed["boats"], ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")).hexdigest()})
    except HTTPError as e:
        output.update({"http_status": e.code, "reason": "HTTP_" + str(e.code)})
    except (URLError, TimeoutError, ValueError, OSError) as e:
        output["reason"] = type(e).__name__ + ":" + str(e)[:180]
        if output["http_status"] == 200:
            output["status"] = "INVALID_OR_INCOMPLETE"
    return output


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--venue", required=True, type=int)
    p.add_argument("--race", required=True, type=int)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()
    result = probe(date.fromisoformat(args.date), args.venue, args.race)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({"status": result["status"],
                      "http_status": result["http_status"],
                      "metrics": result["metrics"],
                      "complete_boats": len(result["boats"]),
                      "reason": result.get("reason"),
                      "url": result["source_url"],
                      "research_only": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
