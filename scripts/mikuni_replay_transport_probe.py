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


def response_content_kind(url: str, content_type: str) -> str:
    """Describe response without inspecting body, path, token, or secret values."""
    mime = (content_type or "").split(";", 1)[0].lower().strip()
    kind = transport_kind(url, mime)
    if "json" in mime:
        return "JSON_METADATA"
    if kind in VIDEO_TYPES:
        return kind
    if mime.startswith("text/") or "xml" in mime:
        return "TEXT_OR_XML"
    if mime:
        return "OTHER_CONTENT_TYPE"
    return "MIME_UNKNOWN"


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
        "requested_date_in_document": False,
        "visible_date_markers": [],
        "document_date_markers": [],
        "race_button_visible": False,
        "meeting_header_clicked": False,
        "day_header_clicked": False,
        "race_icon_matches": 0,
        "race_icon_visible_matches": 0,
        "race_icon_parent_tag": None,
        "race_icon_parent_has_link": False,
        "race_click_status": "NOT_ATTEMPTED",
        "race_button_clicked": False,
        "video_play_attempted": False,
        "media_request_types": {},
        "media_response_types": {},
        "media_requests_blocked": 0,
        "opaque_data_requests_blocked": 0,
        "safe_metadata_bootstraps_allowed": 0,
        "safe_metadata_bootstraps_rejected": 0,
        "opaque_hosts": [],
        "opaque_request_shapes": [],
        "read_only_head_results": [],
        "normal_browser_get_opt_in": False,
        "normal_browser_get_request_count": 0,
        "normal_browser_get_responses": [],
        "raw_media_downloaded": False,
        "video_bytes_downloaded": 0,
        "frames_decoded": 0,
        "verified_six_boat_tracks": 0,
        "formal_forecast_modified": False,
        "status": "NOT_RUN",
    }


def run_browser_probe(day: str, race: int, *, wait_ms: int = 4200, inspect_normal_get: bool = False) -> dict:
    audit = new_audit(day, race)
    requests = Counter()
    responses = Counter()
    blocked = [0]
    opaque_blocked = [0]
    allowed_metadata = [0]
    rejected_metadata = [0]
    opaque_hosts = set()
    opaque_shapes = set()
    opaque_get_urls = {}
    browser_get_requests = [0]
    browser_get_responses = {}
    audit["normal_browser_get_opt_in"] = bool(inspect_normal_get)
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
                    request = response.request
                    parts = urlsplit(response.url)
                    if (inspect_normal_get and parts.scheme == "https"
                            and parts.hostname == "playback.api.streaks.jp"
                            and request.method == "GET"
                            and request.resource_type in {"xhr", "fetch"}):
                        content_kind = response_content_kind(
                            response.url, response.headers.get("content-type", ""))
                        # Only the HTTP status and content-type CLASS are recorded.
                        # Never touch response.text()/body(), URL paths, cookies or tokens.
                        record_key = (response.status, content_kind)
                        browser_get_responses[record_key] = browser_get_responses.get(record_key, 0) + 1

                def guard(route):
                    # Critical: media and manifests are not fetched by this probe.
                    kind = transport_kind(route.request.url)
                    if kind in VIDEO_TYPES or route.request.resource_type == "media":
                        blocked[0] += 1
                        route.abort()
                    elif route.request.resource_type in {"xhr", "fetch"}:
                        parts = urlsplit(route.request.url)
                        host = parts.hostname
                        if (inspect_normal_get and parts.scheme == "https"
                                and host == "playback.api.streaks.jp"
                                and route.request.method == "GET"
                                and browser_get_requests[0] < 5):
                            # Observe the exact browser's ordinary GET with its natural
                            # session. No manual tokens, guessed URLs or authentication bypass.
                            browser_get_requests[0] += 1
                            route.continue_()
                            return
                        if host:
                            opaque_hosts.add(host.lower())
                            if (host.lower() in {"front.player.boatrace-cdn.jp", "livebb.jlc.ne.jp", "playback.api.streaks.jp"}
                                    and route.request.method == "GET"
                                    and urlsplit(route.request.url).scheme == "https"):
                                opaque_get_urls[host.lower()] = route.request.url
                            suffix = Path(urlsplit(route.request.url).path).suffix.lower()
                            if not re.fullmatch(r"\.[a-z0-9]{1,6}", suffix):
                                suffix = "(none)"
                            opaque_shapes.add((host.lower(), route.request.method,
                                               route.request.resource_type, suffix))
                        # Permit only public, HEAD-verified small metadata responses.
                        # The HEAD preflight never downloads a video body.
                        if (host in {"front.player.boatrace-cdn.jp", "livebb.jlc.ne.jp", "playback.api.streaks.jp"}
                                and route.request.method == "GET"):
                            try:
                                head = route.fetch(method="HEAD", timeout=5000, max_redirects=0)
                                mime = head.headers.get("content-type", "").split(";", 1)[0].lower()
                                length = head.headers.get("content-length", "")
                                permitted_type = ("json" in mime or mime in {
                                    "text/html", "text/plain", "text/xml",
                                    "application/xml", "application/javascript",
                                })
                                safe_size = not length.isdigit() or int(length) <= 1048576
                                if head.status == 200 and permitted_type and safe_size:
                                    allowed_metadata[0] += 1
                                    route.continue_()
                                    return
                            except Exception:
                                pass
                            rejected_metadata[0] += 1
                        opaque_blocked[0] += 1
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
                page.wait_for_timeout(1200)
                body = page.locator("body").inner_text(timeout=7000)
                markup = page.content()
                monthday = f"{int(day[5:7])}/{int(day[8:10])}"
                audit["visible_date_markers"] = sorted(set(re.findall(r"(?:20\d{2}[/\\-])?\d{1,2}[/\\-]\d{1,2}", body)))[:12]
                audit["document_date_markers"] = sorted(set(re.findall(r"(?:20\d{2}[/\\-])?\d{1,2}[/\\-]\d{1,2}", markup)))[:12]
                audit["requested_date_visible"] = monthday in body
                audit["requested_date_in_document"] = monthday in markup
                # The public replay list uses collapsed meeting/day accordion sections.
                # Expand only the newest meeting that started on/before the target day.
                # Clicking does not fetch any media: route guard blocks video and opaque XHR.
                def open_visible_text(token):
                    for loc in page.get_by_text(token, exact=False).all()[:8]:
                        try:
                            if loc.is_visible():
                                loc.click(timeout=1600)
                                return True
                        except Exception:
                            continue
                    return False

                meet_candidates = sorted(set(re.findall(
                    r"20\d{2}/\d{1,2}/\d{1,2}", body
                )))
                target_slash = day.replace("-", "/")
                matching_meets = [d for d in meet_candidates if d <= target_slash]
                if matching_meets:
                    audit["meeting_header_clicked"] = open_visible_text(matching_meets[-1])
                    page.wait_for_timeout(300)
                if (audit["requested_date_visible"] or audit["requested_date_in_document"]):
                    audit["day_header_clicked"] = open_visible_text(monthday)
                    page.wait_for_timeout(300)

                # We do not independently verify date/race linkage on visual click.
                selector = f'img[src*="{race}R.png"]'
                icon = page.locator(selector)
                visible_icon = page.locator(selector + ":visible")
                audit["race_icon_matches"] = icon.count()
                audit["race_icon_visible_matches"] = visible_icon.count()
                audit["race_button_visible"] = visible_icon.count() > 0
                if icon.count():
                    audit["race_icon_parent_tag"] = icon.first.evaluate(
                        "(el) => el.parentElement?.tagName?.toLowerCase() || null")
                    audit["race_icon_parent_has_link"] = icon.first.evaluate(
                        "(el) => Boolean(el.closest('a'))")
                if not (audit["requested_date_visible"] or audit["requested_date_in_document"]):
                    audit["race_click_status"] = "REQUESTED_DATE_NOT_IN_PAGE"
                elif not audit["race_button_visible"]:
                    audit["race_click_status"] = "RACE_BUTTON_NOT_VISIBLE"
                else:
                    try:
                        visible_icon.first.click(timeout=4500)
                        audit["race_button_clicked"] = True
                        audit["race_click_status"] = "CLICKED_UNVERIFIED_DAY_ASSOCIATION"
                    except Exception:
                        audit["race_click_status"] = "CLICK_FAILED_NO_UNVERIFIED_PLAYBACK"
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
                # HEAD request sends no response-body download. URLs remain local
                # in memory and are not saved, printed, or exposed to users.
                for host, url in sorted(opaque_get_urls.items()):
                    record = {"host": host, "head_http_status": None,
                              "content_kind": "UNKNOWN", "content_length_band": "UNKNOWN"}
                    try:
                        head = context.request.head(url, timeout=5500, max_redirects=0)
                        record["head_http_status"] = head.status
                        mime = head.headers.get("content-type", "").split(";", 1)[0].lower()
                        kind = transport_kind(url, mime)
                        if kind in VIDEO_TYPES:
                            record["content_kind"] = kind
                        elif "json" in mime:
                            record["content_kind"] = "JSON_METADATA"
                        elif mime.startswith("text/") or "xml" in mime:
                            record["content_kind"] = "TEXT_OR_XML_METADATA"
                        elif mime:
                            record["content_kind"] = "OTHER_CONTENT_TYPE"
                        size = head.headers.get("content-length", "")
                        if size.isdigit():
                            record["content_length_band"] = (
                                "UNDER_1MB" if int(size) < 1048576 else "AT_LEAST_1MB")
                    except Exception:
                        record["head_http_status"] = "HEAD_NOT_AVAILABLE"
                    audit["read_only_head_results"].append(record)
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
        audit["opaque_data_requests_blocked"] = opaque_blocked[0]
        audit["normal_browser_get_request_count"] = browser_get_requests[0]
        audit["normal_browser_get_responses"] = [
            {"http_status": status, "content_kind": kind, "count": n}
            for (status, kind), n in sorted(browser_get_responses.items())
        ]
        audit["safe_metadata_bootstraps_allowed"] = allowed_metadata[0]
        audit["safe_metadata_bootstraps_rejected"] = rejected_metadata[0]
        audit["opaque_hosts"] = sorted(opaque_hosts)[:12]
        audit["opaque_request_shapes"] = [
            {"host": h, "method": m, "resource_type": t, "path_suffix": s}
            for h, m, t, s in sorted(opaque_shapes)[:20]
        ]
    return audit


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mikuni public replay transport: metadata only")
    parser.add_argument("--date", required=True)
    parser.add_argument("--race", type=int, default=1)
    parser.add_argument(
        "--inspect-normal-get", action="store_true",
        help="Allow only browser-initiated playback.api.streaks.jp GET and audit status/MIME, no media file download",
    )
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    result = run_browser_probe(args.date, args.race, inspect_normal_get=args.inspect_normal_get)
    data = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(data, encoding="utf-8")
    print(data, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
