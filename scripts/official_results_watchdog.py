"""Bounded liveness checks for the existing result collector and Pages publisher.

Never calculate bets or manufacture results. Recover stale acquisition and
publication by dispatching the existing, guarded main-branch workflows.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

REPOSITORY = "cigusc-qyDga1-sivwix/autonomous-boat-ai"
JST = ZoneInfo("Asia/Tokyo")
UTC = timezone.utc
RESULTS = ".github/workflows/official-results-fast.yml"
PUBLISH = ".github/workflows/boat-lab-pages.yml"
FORECAST = ".github/workflows/boat-lab-auto.yml"
ALLOWED_TARGETS = {RESULTS, PUBLISH, FORECAST}
STALE_SECONDS = 120
COOLDOWN_SECONDS = 180
PUBLIC_ROOT = "https://cigusc-qydga1-sivwix.github.io/autonomous-boat-ai/"


def target_window(now: datetime, day: str, start_hour: int) -> str:
    if now.tzinfo is None:
        raise ValueError("An aware clock is required")
    local = now.astimezone(JST)
    if local.date().isoformat() != day:
        return "expired"
    return "waiting" if local.hour < start_hour else "open"


def snapshot_time(doc, day: str, now: datetime):
    if not isinstance(doc, dict) or (
        doc.get("date") != day
        or doc.get("status") != "verified_by_server_fetch"
        or doc.get("evidence_type") != "official_boatrace_pay_snapshot"
        or doc.get("source_url") != "https://www.boatrace.jp/owpc/pc/race/pay?hd=" + day.replace("-", "")
        or not isinstance(doc.get("results"), dict)
        or len(doc["results"]) > 288
    ):
        return None
    try:
        stamp = datetime.fromisoformat(doc["retrieved_at_utc"])
        if stamp.tzinfo is None or stamp > now + timedelta(seconds=60):
            return None
        return stamp
    except (KeyError, TypeError, ValueError):
        return None


def active_target(runs: list, target: str) -> bool:
    return any(
        r.get("path", "").split("@")[0] == target
        and r.get("head_branch") == "main"
        and r.get("status") != "completed"
        for r in runs
    )


def choose_target(now: datetime, day: str, start_hour: int, backend, published,
                  runs: list, elapsed: dict, ledger_exists: bool = True):
    if target_window(now, day, start_hour) != "open":
        return None

    def available(target):
        return not active_target(runs, target) and elapsed.get(target, float("inf")) >= COOLDOWN_SECONDS

    if not ledger_exists:
        # The existing collector still refuses to generate any post-cutoff bet.
        return FORECAST if available(FORECAST) else None
    source_time = snapshot_time(backend, day, now)
    public_time = snapshot_time(published, day, now)
    if source_time is None or (now - source_time).total_seconds() >= STALE_SECONDS:
        return RESULTS if available(RESULTS) else None
    if (public_time is None or public_time < source_time) and (now - source_time).total_seconds() >= 45:
        return PUBLISH if available(PUBLISH) else None
    return None


class Client:
    def __init__(self, repository: str, token: str):
        if repository != REPOSITORY or not token:
            raise ValueError("Expected the existing repository and workflow token")
        self.api = "https://api.github.com/repos/" + repository
        self.token = token

    def request(self, url: str, payload=None):
        headers = {"User-Agent": "boat-lab-official-result-watchdog", "Cache-Control": "no-cache"}
        if url.startswith(self.api + "/"):
            headers.update({"Authorization": "Bearer " + self.token,
                            "Accept": "application/vnd.github+json"})
        elif not url.startswith(PUBLIC_ROOT):
            raise ValueError("Unexpected watchdog destination")
        data = None if payload is None else json.dumps(payload).encode()
        with urlopen(Request(url, data=data, headers=headers), timeout=20) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Watchdog response is too large")
        return json.loads(raw) if raw else {}

    def content(self, path: str):
        return self.request(self.api + "/contents/" + path + "?ref=main")

    def snapshot(self, day: str):
        try:
            item = self.content("app/data/live/official-pay/" + day + ".json")
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        if item.get("encoding") != "base64":
            raise ValueError("Expected a small verified payout snapshot")
        return json.loads(base64.b64decode(item["content"]))

    def ledger_exists(self, day: str) -> bool:
        try:
            return self.content("app/data/live/" + day + ".json").get("type") == "file"
        except HTTPError as exc:
            if exc.code == 404:
                return False
            raise

    def dispatch(self, target: str):
        if target not in ALLOWED_TARGETS:
            raise ValueError("Unexpected recovery workflow")
        self.request(self.api + "/actions/workflows/" + target.rsplit("/", 1)[1] + "/dispatches", {"ref": "main"})


def check(client: Client, day: str, start_hour: int, now: datetime, elapsed: dict):
    runs = client.request(client.api + "/actions/runs?per_page=100")["workflow_runs"]
    backend = client.snapshot(day)
    try:
        published = client.request(PUBLIC_ROOT + "data/live/official-pay/" + day + ".json?watchdog=" + str(int(now.timestamp())))
    except Exception:
        published = None
    exists = backend is not None or client.ledger_exists(day)
    target = choose_target(now, day, start_hour, backend, published, runs, elapsed, exists)
    if target:
        client.dispatch(target)
    source_time = snapshot_time(backend, day, now)
    public_time = snapshot_time(published, day, now)
    report = {
        "checked_at_utc": now.isoformat(), "date": day, "dispatched": target,
        "source_age_seconds": max(0, round((now-source_time).total_seconds())) if source_time else None,
        "published_age_seconds": max(0, round((now-public_time).total_seconds())) if public_time else None,
        "source_results": len(backend.get("results", {})) if source_time else None,
        "published_results": len(published.get("results", {})) if public_time else None,
        "result_collector_active": active_target(runs, RESULTS),
        "publisher_active": active_target(runs, PUBLISH),
    }
    return target, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", required=True)
    parser.add_argument("--minutes", type=int, default=345)
    parser.add_argument("--start-hour", type=int, choices=range(24), default=6)
    args = parser.parse_args()
    datetime.strptime(args.day, "%Y-%m-%d")
    client = Client(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"])
    end = time.monotonic() + min(max(args.minutes, 1), 345)*60
    dispatched_at = {}
    while time.monotonic() < end:
        now = datetime.now(UTC)
        window = target_window(now, args.day, args.start_hour)
        if window == "expired":
            print("Target JST day ended; bounded watchdog stopped", flush=True)
            break
        if window == "open":
            try:
                elapsed = {key: time.monotonic()-value for key, value in dispatched_at.items()}
                target, report = check(client, args.day, args.start_hour, now, elapsed)
                if target:
                    dispatched_at[target] = time.monotonic()
                print(json.dumps(report), flush=True)
            except Exception as exc:
                # No headers, tokens, request bodies or remote error bodies in logs.
                print(json.dumps({"checked_at_utc": now.isoformat(), "check_error": type(exc).__name__}), flush=True)
        time.sleep(30)


if __name__ == "__main__":
    main()
