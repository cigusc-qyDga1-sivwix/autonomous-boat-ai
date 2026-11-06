"""Independent, single-race numeric exhibition probe.

NOT a BOAT LAB formal forecast input. Live requests are disabled unless a
human explicitly enables them after reviewing source terms. No video,
result, payout, or multi-race crawler is included in this initial pilot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

UTC = timezone.utc
JST = ZoneInfo("Asia/Tokyo")
HOST = "https://race.boatcast.jp"
SAFE_LEAD = timedelta(seconds=180)
MAX_BYTES = 64_000


class InvalidPreview(ValueError):
    pass


def canonical_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def finite(value: str):
    try:
        number = float(str(value).strip().replace(" ", "").replace("\u3000", ""))
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def lines_of(body: str) -> list[str]:
    stripped = body.lstrip()
    if stripped.startswith("<") or not body.splitlines() or not body.splitlines()[0].strip().startswith("data="):
        raise InvalidPreview("Not a recognized TSV preview (HTML fallback or missing header)")
    rows = [line for line in body.splitlines()[1:] if line.strip()]
    if not rows or rows[0].split("\t")[0].strip() != "1":
        raise InvalidPreview("Preview not ready or status not normal")
    return rows[1:]


def parse_tkz(body: str) -> dict[int, dict]:
    lines = lines_of(body)
    if len(lines) < 6:
        raise InvalidPreview("Fewer than six exhibition-time rows")
    boats = {}
    for lane, line in enumerate(lines[:6], start=1):
        parts = line.split("\t")
        if len(parts) < 7:
            raise InvalidPreview("Incomplete exhibition-time row")
        exhibition_time = finite(parts[1])
        if exhibition_time is None or not 5 <= exhibition_time <= 10:
            raise InvalidPreview("Invalid exhibition time")
        boats[lane] = {"lane": lane, "exhibition_time": exhibition_time,
                       "tilt": finite(parts[6])}
    return boats


def parse_stt(body: str) -> dict[int, dict]:
    boats = {}
    for line in lines_of(body):
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        try:
            course, lane = int(parts[0].strip()), int(parts[1].strip())
        except ValueError:
            continue
        if lane not in range(1, 7) or course not in range(1, 7) or lane in boats:
            raise InvalidPreview("Duplicate lane or invalid entry course")
        flag = parts[5].strip().upper()
        if flag not in ("", "F"):
            raise InvalidPreview("Incomplete or late-start exhibition ST")
        st = finite(parts[4])
        if st is None:
            raise InvalidPreview("Missing exhibition ST")
        st = -abs(st) if flag == "F" else st
        if not -0.5 <= st <= 1.0:
            raise InvalidPreview("Out-of-range exhibition ST")
        boats[lane] = {"course": course, "exhibition_st": st,
                       "exhibition_f": flag == "F"}
    if set(boats) != set(range(1, 7)) or len({b["course"] for b in boats.values()}) != 6:
        raise InvalidPreview("Six unique lanes and six entry courses are required")
    return boats


def assemble(stt: str, tkz: str) -> list[dict]:
    a, b = parse_stt(stt), parse_tkz(tkz)
    return [{**b[lane], **a[lane]} for lane in range(1, 7)]


def endpoint(kind: str, day: str, venue: int, race: int) -> str:
    if kind not in ("stt", "tkz"):
        raise ValueError("Unsupported input")
    datetime.strptime(day, "%Y-%m-%d")
    if not (1 <= venue <= 24 and 1 <= race <= 12):
        raise ValueError("Invalid venue or race")
    code = day.replace("-", "")
    return f"{HOST}/hp_txt/{venue:02d}/bc_j_{kind}_{code}_{venue:02d}_{race:02d}.txt"


def fetch_once(url: str) -> str:
    request = Request(url, headers={
        "User-Agent": "BOAT-LAB-Exhibition-Bridge-Probe/0.1 (research; contact via project GitHub)",
        "Accept": "text/plain",
    })
    try:
        with urlopen(request, timeout=8) as response:
            if response.status != 200:
                raise InvalidPreview(f"HTTP {response.status}")
            payload = response.read(MAX_BYTES + 1)
    except HTTPError as exc:
        raise InvalidPreview(f"HTTP {exc.code} (no retry or bypass)") from exc
    except (URLError, TimeoutError) as exc:
        raise InvalidPreview(f"Network unavailable: {type(exc).__name__}") from exc
    if len(payload) > MAX_BYTES:
        raise InvalidPreview("Preview payload too large")
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidPreview("Invalid source encoding") from exc


def candidate(day: str, venue: int, race: int, cutoff_hm: str,
              stt_body: str, tkz_body: str, captured_at: datetime,
              *, mode: str = "offline_fixture") -> dict:
    if captured_at.tzinfo is None:
        raise ValueError("Capture clock requires timezone")
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", cutoff_hm):
        raise ValueError("Invalid cutoff time")
    cutoff = datetime.fromisoformat(f"{day}T{cutoff_hm}:00+09:00")
    if captured_at.astimezone(JST).date() != cutoff.date():
        raise InvalidPreview("Source date differs from capture JST day")
    if captured_at >= cutoff - SAFE_LEAD:
        raise InvalidPreview("Capture too late for three-minute pre-cutoff margin")
    boats = assemble(stt_body, tkz_body)
    values = {"race_code": f"{day.replace('-', '')}{venue:02d}{race:02d}",
              "boats": boats}
    return {
        "schema": "boatlabs.direct_exhibition_candidate.v1",
        "status": "research_only_not_formal",
        "mode": mode,
        "event_date": day,
        "race_code": values["race_code"],
        "venue_code": f"{venue:02d}",
        "race": race,
        "cutoff_at_jst": cutoff.isoformat(),
        "cutoff_source": "operator_supplied_not_independently_verified",
        "captured_at_utc": captured_at.astimezone(UTC).isoformat(),
        "source_observed_jst": None,
        "source": "BOATCAST_numeric_tsv_candidate",
        "source_pages": [endpoint(k, day, venue, race) for k in ("stt", "tkz")],
        "measurement_sha256": canonical_hash(values),
        "boats": boats,
        "not_proof_of_upstream_publish_time": True,
        "formal_forecast_authorized": False,
        "result_or_payout_used": False,
    }


def store_gcs(candidate_doc: dict, bucket_name: str):
    """Create-only GCS object; no GitHub commit and no overwrite of live ledger."""
    from google.cloud import storage
    code = candidate_doc["race_code"]
    digest = candidate_doc["measurement_sha256"]
    object_name = f"exhibition-bridge/v1/{candidate_doc['event_date']}/{code}/{digest}.json"
    blob = storage.Client().bucket(bucket_name).blob(object_name)
    blob.upload_from_string(json.dumps(candidate_doc, ensure_ascii=False, sort_keys=True),
                            content_type="application/json", if_generation_match=0)
    return f"gs://{bucket_name}/{object_name}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="today", help="YYYY-MM-DD or today (JST)")
    parser.add_argument("--venue", type=int, required=True)
    parser.add_argument("--race", type=int, required=True)
    parser.add_argument("--cutoff", required=True, help="HH:MM JST from verified race card")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true")
    mode.add_argument("--fixture-dir", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--gcs-bucket", help="Optional private GCS bucket, create-only")
    args = parser.parse_args(argv)

    now = datetime.now(UTC)
    day = now.astimezone(JST).date().isoformat() if args.date == "today" else args.date
    try:
        endpoint("stt", day, args.venue, args.race)
        cutoff = datetime.fromisoformat(f"{day}T{args.cutoff}:00+09:00")
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", args.cutoff):
            raise ValueError("Invalid cutoff")
        if args.live:
            if os.environ.get("BOATCAST_DIRECT_FETCH_APPROVED") != "1":
                raise InvalidPreview("Direct fetch disabled pending source approval")
            if now.astimezone(JST).date().isoformat() != day or now >= cutoff - SAFE_LEAD:
                raise InvalidPreview("Live mode requires current JST day and pre-cutoff safety")
            # Two GETs for exactly one race; no retries, bypass, or bulk crawling.
            stt = fetch_once(endpoint("stt", day, args.venue, args.race))
            time.sleep(1.0)
            tkz = fetch_once(endpoint("tkz", day, args.venue, args.race))
            observed = datetime.now(UTC)
        else:
            stt = (args.fixture_dir / "stt.txt").read_text(encoding="utf-8")
            tkz = (args.fixture_dir / "tkz.txt").read_text(encoding="utf-8")
            # Offline fixtures prove parsing, not live pre-cutoff availability.
            observed = now
        doc = candidate(day, args.venue, args.race, args.cutoff, stt, tkz,
                        observed, mode="live_probe" if args.live else "offline_fixture")
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
        location = store_gcs(doc, args.gcs_bucket) if args.gcs_bucket else None
        print(json.dumps({"status": doc["status"], "race_code": doc["race_code"],
                          "measurement_sha256": doc["measurement_sha256"],
                          "captured_at_utc": doc["captured_at_utc"],
                          "gcs": location}, ensure_ascii=False))
        return 0
    except (InvalidPreview, ValueError, OSError) as exc:
        print(json.dumps({"status": "no_eligible_candidate",
                          "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
