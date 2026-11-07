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
        if DATED_JSON.fullmatch(rel) and size >= ARCHIVE_LIMIT_BYTES:
            archived.append({
                "path": rel,
                "bytes": size,
                "source": GITHUB_ARCHIVE_BASE + rel,
                "reason": "large_historical_json_not_required_for_live_pwa",
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
