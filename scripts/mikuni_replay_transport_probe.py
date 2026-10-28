"""Read-only browser transport reconnaissance for the official Mikuni JLC replay.

This does NOT download media, evade access controls, reverse engineer tokens, or
make verified race/boat claims. A public replay landing page is loaded normally;
known media and manifest requests are aborted before response bodies. Only a
small sanitized JSON audit is emitted. No original request URLs are persisted.

The user reports that BOAT RACE Mikuni authorized personal video analysis. The
JLC distribution route can have separate requirements. This probe intentionally
does not ingest JLC media before those requirements are understood.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

SCHEMA = "boatlabs.mikuni_replay_transport_probe.v1"
LANDING = "https://livebb.jlc.ne.jp/bb_top/sp_bb/tvod_10.php"
VIDEO_TYPES = {"HLS_MANIFEST", "DASH_MANIFEST", "VIDEO_FILE",
               "VIDEO_SEGMENT", "DRM_OR_KEY", "BLOB_MEDIA"}
VALID_DAY = re.compile(r"20\d\d-\d\d-\d\d$")


def validate(day: str, race: int) -> None:
    if not isinstance(day, str) or not VALID_DAY.fullmatch(day):
        raise ValueError("invalid_date")
    datetime.strptime(day, "%Y-%m-%d")
    if isinstance(race, bool) or not isinstance(race, int) or not 1 <= race <= 12:
        raise ValueError("invalid_race")


def transport_kind(url: str, content_type: str = "") -> str:
    """Classify HTTP transport; NEVER store or log URLs or query strings."""
    scheme = urlsplit(url).scheme.lower()
    if scheme == "blob":
        return "BLOB_MEDIA"
    if scheme != "https":
        return "NOT_MEDIA"
    path = urlsplit(url).path.lower()
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if path.endswith(".m3u8") or mime in {
        "application/vnd.apple.mpegurl", "application/x-mpegurl",
        "audio/mpegurl", "audio/x-mpegurl",
    }:
        return "HLS_MANIFEST"
    if path.endswith(".mpd") or mime == "application/dash+xml":
        return "DASH_MANIFEST"
    if path.endswith((".key", ".widevine", ".license")):
        return "DRM_OR_KEY"
    if path.endswith((".ts", ".m4s", ".cmfv", ".cmfa")) or mime == "video/mp2t":
        return "VIDEO_SEGMENT"
    if path.endswith((".mp4", ".webm", ".mov", ".avi", ".mkv")) or mime.startswith("video/"):
        return "VIDEO_FILE"
    return "NOT_MEDIA"


def new_audit(day: str, race: int) -> dict:
    validate(day, race)
    return {
        "schema": SCHEMA,
        "event_date": day,
        "venue": "三国",
        "race_requested": race,
        "inspection_target": "PUBLIC_JLC_REPLAY_LANDING",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "TRANSPORT_METADATA_ONLY_NO_VIDEO_DOWNLOAD",
        "landing_http_status": None,
        "requested_date_visible": False,
        "race_button_visible": False,
        "race_button_clicked": False,
        "video_play_attempted": False,
        "media_request_types": {},
        "media_response_types": {},
        "media_requests_blocked": 0,
        "raw_media_downloaded": False,
        "video_bytes_downloaded": 0,
        "frames_decoded": 0,
        "verified_six_boat_tracks": 0,
        "formal_forecast_modified": False,
        "status": "NOT_RUN",
    }


def run_browser_probe(day: str, race: int, *, wait_ms: int = 4200) -> dict:
    audit = new_audit(day, race)
    requests = Counter()
    responses = Counter()
    blocked = [0]
    # Import at runtime so pure, network-free unit tests require no Playwright.
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
                context.set_default_timeout(6000)

                def observe_request(request):
                    kind = transport_kind(request.url)
                    if kind in VIDEO_TYPES:
                        requests[kind] += 1

                def observe_response(response):
                    kind = transport_kind(response.url, response.headers.get("content-type", ""))
                    if kind in VIDEO_TYPES:
                        responses[kind] += 1

                def guard(route):
                    # Critical: media and manifests are not fetched by this probe.
                    kind = transport_kind(route.request.url)
                    if kind in VIDEO_TYPES or route.request.resource_type in {"media", "xhr", "fetch"}:
                        # Unknown XHR/fetch may carry opaque media bytes.
                        # Block it too: this is discovery, not a downloader.
                        blocked[0] += 1
                        route.abort()
                    else:
                        route.continue_()

                context.on("request", observe_request)
                context.on("response", observe_response)
                context.route("**/*", guard)
                page = context.new_page()
                response = page.goto(LANDING, wait_until="domcontentloaded", timeout=18000)
                audit["landing_http_status"] = response.status if response else None
                if response is None or response.status >= 400:
                    audit["status"] = "PUBLIC_LANDING_NOT_ACCESSIBLE"
                    return audit
                body = page.locator("body").inner_text(timeout=7000)
                monthday = f"{int(day[5:7])}/{int(day[8:10])}"
                audit["requested_date_visible"] = monthday in body
                # Click a race icon only if the requested date is visible.
                # We do not certify its event-day association from this action.
                selector = f'img[src*="{race}R.png"]'
                icon = page.locator(selector)
                audit["race_button_visible"] = icon.count() > 0
                if audit["requested_date_visible"] and audit["race_button_visible"]:
                    try:
                        icon.first.click(timeout=6000)
                        audit["race_button_clicked"] = True
                    except Exception:
                        pass
                for tab in context.pages:
                    try:
                        video = tab.locator("video").first
                        if video.count():
                            audit["video_play_attempted"] = True
                            # Request metadata only; blocked media never reaches decoder.
                            video.evaluate(
                                "(el) => { el.muted = true; el.play().catch(() => {}); }",
                                timeout=2000,
                            )
                    except Exception:
                        continue
                page.wait_for_timeout(max(0, min(int(wait_ms), 8000)))
                audit["status"] = (
                    "MEDIA_TRANSPORT_CANDIDATE_OBSERVED_NOT_DOWNLOADED"
                    if requests else
                    "PUBLIC_PAGE_LOADED_NO_MEDIA_REQUEST_OBSERVED"
                )
            finally:
                browser.close()
    except Exception:
        # No URL, token, headers, local path or raw exception in the public audit.
        audit["status"] = "BROWSER_OR_NETWORK_PROBE_FAILED"
    finally:
        audit["media_request_types"] = dict(sorted(requests.items()))
        audit["media_response_types"] = dict(sorted(responses.items()))
        audit["media_requests_blocked"] = blocked[0]
    return audit


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mikuni public replay transport: metadata only")
    parser.add_argument("--date", required=True)
    parser.add_argument("--race", type=int, default=1)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    result = run_browser_probe(args.date, args.race)
    data = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(data, encoding="utf-8")
    print(data, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
