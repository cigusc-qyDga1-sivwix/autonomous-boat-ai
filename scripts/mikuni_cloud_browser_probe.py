"""Read-only browser reachability of JLC Mikuni PC page on GitHub-hosted runner.

No user PC, player click, video download, HLS scraping or DRM bypass.
Only aggregate UI counts are emitted, no site URLs, images or credentials.
"""
import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit
from datetime import date

ENTRY = "https://livebb.jlc.ne.jp/bb_top/new_bb/index.php?tpl=10"
SCHEMA = "boatlabs.mikuni_cloud_browser_probe.v1"


def classify(report):
    if not report["site_loaded"]:
        return "OFFICIAL_PC_SITE_UNAVAILABLE"
    if not report["venue_query_verified"]:
        return "WRONG_VENUE_NOT_TRUSTED"
    if report["video_elements"]:
        return "VIDEO_ELEMENT_FOUND_REPLAY_NOT_VERIFIED"
    if report["exhibition_menu_candidates"]:
        return "EXHIBITION_UI_VISIBLE_REPLAY_NOT_SELECTED"
    return "OFFICIAL_PC_ENTRY_ONLY"


async def inventory(frame):
    try:
        return await frame.evaluate("""() => {
          const items=[...document.querySelectorAll('a,button,[role=tab]')].slice(0,1200);
          const txt=items.map(x=>(x.textContent||'').trim().replace(/\\s+/g,' '));
          return {
            menu:txt.filter(s=>s==='展示リプレイ'||s==='展示').length,
            race:txt.filter(s=>/^1\\s*R$/i.test(s)).length,
            video:document.querySelectorAll('video').length
          };
        }""")
    except Exception:
        return {"menu": 0, "race": 0, "video": 0, "error": True}


async def inspect(day, race):
    from playwright.async_api import async_playwright
    if date.fromisoformat(day).isoformat() != day or race not in range(1, 13):
        raise ValueError("invalid_date_or_race")
    report = {
        "schema": SCHEMA, "date": day, "venue_code": "10", "race": race,
        "probe_kind": "OFFICIAL_UI_READ_ONLY",
        "browser_started": False, "site_loaded": False,
        "venue_query_verified": (urlsplit(ENTRY).query == "tpl=10"),
        "official_frames": 0, "external_frames": 0, "uninspectable_frames": 0,
        "exhibition_menu_candidates": 0, "race_one_control_candidates": 0,
        "video_elements": 0, "exact_day_race_verified": False,
        "video_bytes_saved": 0, "images_saved": 0,
        "formal_forecasts_modified": False,
    }
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="msedge", headless=True,
                args=["--no-first-run", "--disable-extensions"], timeout=20000)
            report["browser_started"] = True
            try:
                context = await browser.new_context(accept_downloads=False, service_workers="block")
                page = await context.new_page()
                response = await page.goto(ENTRY, wait_until="domcontentloaded", timeout=25000)
                report["site_loaded"] = response is not None and 200 <= response.status < 400
                if report["site_loaded"]:
                    await page.wait_for_timeout(3500)
                    for frame in page.frames[:16]:
                        host = urlsplit(frame.url).hostname
                        if host == "livebb.jlc.ne.jp":
                            report["official_frames"] += 1
                        elif host:
                            report["external_frames"] += 1
                        values = await inventory(frame)
                        report["exhibition_menu_candidates"] += values["menu"]
                        report["race_one_control_candidates"] += values["race"]
                        report["video_elements"] += values["video"]
                        if values.get("error"):
                            report["uninspectable_frames"] += 1
                await context.close()
            finally:
                await browser.close()
    except Exception:
        report["failure_kind"] = "BROWSER_OR_NETWORK_UNAVAILABLE"
    report["status"] = classify(report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-10-28")
    parser.add_argument("--race", type=int, default=1)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = asyncio.run(inspect(args.date, args.race))
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
