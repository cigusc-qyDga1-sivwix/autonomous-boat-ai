#!/usr/bin/env python3
"""Make a small GitHub Pages artifact without touching archived source data.

The immutable full dated ledgers remain on GitHub main and are NOT deleted.
The live app uses latest.json and the small status/official files, not the giant
dated archives. Pages deployment is too slow when the full app (~860MB) is
uploaded every few minutes. Limit the deployment payload, keep a discoverable
index of archived files and explicit links back to immutable GitHub versions.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

GITHUB_ARCHIVE_BASE = (
    "https://github.com/cigusc-qyDga1-sivwix/autonomous-boat-ai/blob/main/app/"
)
# Only large date-specific historical JSON is kept off Pages.
# All source files, live pointers, status, current predictions and HTML remain.
DATED_JSON = re.compile(r"^data/.+/(?:[a-z][a-z0-9-]*-)?\d{4}-\d{2}-\d{2}\.json$")
ARCHIVE_LIMIT_BYTES = 1_500_000
# Do not include the full immutable ledger in the PWA. Publish only the
# fields the official settlement verifier needs, beginning Nov 4 JST.
SETTLEMENT_START_DAY = "2026-11-04"
SETTLEMENT_LEDGER = re.compile(r"^data/live/(\d{4}-\d{2}-\d{2})\.json$")
SITE_LIMIT_BYTES = 120_000_000
REQUIRED = (
    "index.html",
    "app.js",
    "service-worker.js",
    "premium-ui.css",
    "exhibition-audit.js",
    "canonical-exhibition-feed.js",
    "data/live/latest.json",
    "data/live/forecast-sync-latest.json",
    "data/exhibition/status-latest.json",
)


def compact_settlement_ledger(file: Path, day: str) -> bytes:
    """Keep the original settlement inputs and final frozen version, not history.

    No prediction, official result, stake, SHA or refund is recalculated here.
    Same event_date/race_records interface as the audited browser summarizer.
    """
    with file.open(encoding="utf-8") as handle:
        doc = json.load(handle)
    if not isinstance(doc, dict) or doc.get("event_date") != day:
        raise ValueError("Settlement ledger event_date mismatch: " + day)
    records = doc.get("race_records")
    if not isinstance(records, dict) or len(records) > 288:
        raise ValueError("Settlement ledger race_records invalid: " + day)
    kept = {}
    for race_id, rec in records.items():
        if not isinstance(rec, dict):
            continue
        versions = rec.get("versions")
        final = versions[-1] if isinstance(versions, list) and versions else None
        snap = {}
        if isinstance(final, dict):
            for name in (
                "venue", "race", "sha256", "cutoff_iso_jst", "frozen_at_utc",
                "bets", "classification", "phase", "cutoff_jst", "model_version"
            ):
                if name in final:
                    snap[name] = final[name]
            if isinstance(final.get("racers"), list):
                snap["racers"] = [
                    {key: row[key] for key in (
                        "lane", "course", "exhibition_st", "exhibition_time"
                    ) if key in row} if isinstance(row, dict) else row
                    for row in final["racers"]
                ]
        minimal = {
            "venue": rec.get("venue"),
            "race": rec.get("race"),
            "versions": [snap] if isinstance(final, dict) else [],
        }
        for name in ("official_pay", "official_conflict", "official_review"):
            if name in rec:
                minimal[name] = rec[name]
        kept[race_id] = minimal
    result = {"event_date": day, "race_records": kept}
    return (json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def build_site(source: Path, output: Path, *, source_root: str = "app") -> dict:
    source = source.resolve()
    output = output.resolve()
    if not source.is_dir():
        raise ValueError("App source directory is unavailable")
    if source == output or source in output.parents:
        raise ValueError("Pages output must not be located inside the source app")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    shipped, archived = [], []
    for item in sorted(source.rglob("*")):
        if item.is_symlink() or not item.is_file():
            continue
        rel = item.relative_to(source).as_posix()
        size = item.stat().st_size
        settlement_match = SETTLEMENT_LEDGER.fullmatch(rel)
        if settlement_match and settlement_match.group(1) >= SETTLEMENT_START_DAY:
            day = settlement_match.group(1)
            compact = compact_settlement_ledger(item, day)
            compact_rel = "data/live/settlement/" + day + ".json"
            compact_target = output / compact_rel
            compact_target.parent.mkdir(parents=True, exist_ok=True)
            compact_target.write_bytes(compact)
            shipped.append((compact_rel, len(compact)))
        if DATED_JSON.fullmatch(rel) and size >= ARCHIVE_LIMIT_BYTES:
            archived.append({
                "path": rel,
                "bytes": size,
                "source": GITHUB_ARCHIVE_BASE + rel,
                "reason": "large_historical_json_replaced_by_compact_settlement_for_pwa" if settlement_match and settlement_match.group(1) >= SETTLEMENT_START_DAY else "large_historical_json_not_required_for_live_pwa",
            })
            continue
        target = output / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)
        shipped.append((rel, size))
    for rel in REQUIRED:
        if not (output / rel).is_file():
            raise ValueError("Missing required Pages asset: " + rel)
    shipped_bytes = sum(n for _, n in shipped)
    if shipped_bytes >= SITE_LIMIT_BYTES:
        raise ValueError("Pages artifact remains excessively large: " + str(shipped_bytes))
    manifest = {
        "schema": "boatlabs.pages.archive-index.v1",
        "policy": "only large dated JSON omitted from published Pages; GitHub main archive intact",
        "archived_count": len(archived),
        "archived_bytes": sum(x["bytes"] for x in archived),
        "shipped_count": len(shipped),
        "shipped_bytes": shipped_bytes,
        "archived": archived,
    }
    target = output / "data" / "archive-on-github.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, default=Path("app"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    summary = build_site(args.app, args.out)
    print(json.dumps({
        "schema": summary["schema"],
        "archived_count": summary["archived_count"],
        "archived_MB": round(summary["archived_bytes"] / 1_000_000, 2),
        "shipped_count": summary["shipped_count"],
        "shipped_MB": round(summary["shipped_bytes"] / 1_000_000, 2),
        "source_archive_preserved": True,
        "live_json_included": True,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
