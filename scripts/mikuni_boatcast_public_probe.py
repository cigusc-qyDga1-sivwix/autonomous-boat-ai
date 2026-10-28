"""Read-only comparison of BOATCAST's official exhibition replay landing.

No media requests, screenshots, HTML, request URLs, API tokens, frame images or
video bytes are collected. This is NOT a video-ingestion interface.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from urllib.parse import urlencode, urlsplit

from scripts.mikuni_replay_transport_probe import transport_kind, VIDEO_TYPES, validate

SCHEMA = "boatlabs.mikuni_boatcast_public_page_probe.v1"
BASE = "https://race.boatcast.jp/replay"


def replay_page(day, race):
    validate(day, race)
    return BASE + "?" + urlencode({
        "jo": "10", "md": "T", "race": race, "ymd": day.replace("-", "")
    })


def host_only(url):
    if not isinstance(url, str):
        return None
    p = urlsplit(url)
    if p.scheme != "https":
        return None
    return p.hostname


def run(day, race):
    replay_page(day, race)
    audit = {
        "schema": SCHEMA, "event_date": day, "venue": "三国",
        "race_requested": race,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "OFFICIAL_BOATCAST_PUBLIC_REPLAY_PAGE",
        "landing_http_status": None,
        "iframe_hosts": [], "media_requests_blocked": 0,
        "opaque_data_requests_blocked": 0,
        "video_elements": 0, "youtube_frame_present": False,
        "status": "NOT_RUN",
        "video_bytes_downloaded": 0, "video_frames_decoded": 0,
        "verified_boat_tracks": 0, "formal_forecasts_modified": False,
    }
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        audit["status"] = "BROWSER_RUNTIME_UNAVAILABLE"
        return audit
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
            try:
                context = browser.new_context(ignore_https_errors=False)
                context.set_default_timeout(6500)
                def guard(route):
                    req = route.request
                    kind = transport_kind(req.url)
                    if kind in VIDEO_TYPES or req.resource_type == "media":
                        audit["media_requests_blocked"] += 1
                        route.abort()
                    elif req.resource_type in {"xhr", "fetch"}:
                        # Unknown XHR might contain arbitrary video bytes.
                        audit["opaque_data_requests_blocked"] += 1
                        route.abort()
                    else:
                        route.continue_()
                context.route("**/*", guard)
                page = context.new_page()
                response = page.goto(replay_page(day, race), wait_until="domcontentloaded", timeout=25000)
                audit["landing_http_status"] = response.status if response else None
                if response is None or response.status >= 400:
                    audit["status"] = "PAGE_UNAVAILABLE"
                    return audit
                page.wait_for_timeout(4500)
                hosts = set()
                for frame in context.pages:
                    for el in frame.locator("iframe").all()[:25]:
                        try:
                            host = host_only(el.get_attribute("src"))
                            if host:
                                hosts.add(host)
                        except Exception:
                            continue
                audit["iframe_hosts"] = sorted(hosts)[:20]
                audit["video_elements"] = sum(p.locator("video").count() for p in context.pages)
                audit["youtube_frame_present"] = any(
                    h.endswith(".youtube.com") or h == "youtube.com" or h == "www.youtube-nocookie.com"
                    for h in hosts)
                audit["status"] = "PUBLIC_PAGE_OBSERVED_MEDIA_BLOCKED"
            finally:
                browser.close()
    except Exception:
        audit["status"] = "BROWSER_OR_NETWORK_PROBE_FAILED"
    return audit


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--race", type=int, default=1)
    args = parser.parse_args(argv)
    print(json.dumps(run(args.date, args.race), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
