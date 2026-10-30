"""Read-only browser reachability of JLC Mikuni PC page on GitHub-hosted runner.

No user PC, player click, video download, HLS scraping or DRM bypass.
Only aggregate UI counts are emitted, no site URLs, images or credentials.
"""
import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from datetime import date

ENTRY = "https://livebb.jlc.ne.jp/bb_top/new_bb/index.php?tpl=10"
SCHEMA = "boatlabs.mikuni_cloud_browser_probe.v1"
ARCHIVE = "https://livebb.jlc.ne.jp/bb_top/sp_bb/tvod_10.php"


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


async def inspect_archive(context, day):
    """Count day-scoped race image groups; NEVER click unverified races."""
    target = f"{int(day[5:7])}/{int(day[8:10])}"
    result = {
        "archive_site_loaded": False,
        "archive_requested_day_visible": False,
        "archive_race_one_images_total": 0,
        "archive_day_group_candidates": 0,
        "archive_status": "ARCHIVE_SITE_UNAVAILABLE",
    }
    page = await context.new_page()
    try:
        response = await page.goto(ARCHIVE, wait_until="domcontentloaded", timeout=25000)
        result["archive_site_loaded"] = response is not None and 200 <= response.status < 400
        if not result["archive_site_loaded"]:
            return result
        await page.wait_for_timeout(2000)
        data = await page.evaluate("""target=>{
          const srcIsOne=img=>/(?:^|\/)1R\.(?:png|gif)(?:\?|$)/i.test(
            img.getAttribute('src')||'');
          const one=[...document.images].filter(srcIsOne);
          const visibleText=(document.body.innerText||'');
          const leaves=[...document.querySelectorAll('body *')].filter(
            e=>e.children.length===0 &&
            (e.textContent||'').trim().includes(target));
          const groups=new Set();
          for(const leaf of leaves.slice(0,30)){
            let parent=leaf;
            for(let depth=0;depth<7 && parent;depth++,parent=parent.parentElement){
              const imgs=[...parent.querySelectorAll('img')];
              const raceOnes=imgs.filter(srcIsOne).length;
              // Isolated date section should contain 12 race icons and
              // exactly one 1R icon. Generic whole-page ancestors rejected.
              if(imgs.length>=12 && imgs.length<=24 && raceOnes===1){
                groups.add(parent);break;
              }
            }
          }
          return {
            day_visible:visibleText.includes(target),
            race_one_images:one.length,
            date_group_candidates:groups.size,
          };
        }""", target)
        result["archive_requested_day_visible"] = bool(data["day_visible"])
        result["archive_race_one_images_total"] = int(data["race_one_images"])
        result["archive_day_group_candidates"] = int(data["date_group_candidates"])
        if not result["archive_requested_day_visible"]:
            result["archive_status"] = "ARCHIVE_TARGET_DAY_NOT_VISIBLE"
        elif result["archive_day_group_candidates"] == 1:
            result["archive_status"] = "ARCHIVE_DAY_RACE_GROUP_CANDIDATE_ONLY"
        else:
            result["archive_status"] = "ARCHIVE_DATE_VISIBLE_GROUP_AMBIGUOUS"
    except Exception:
        result["archive_status"] = "ARCHIVE_UI_DIAGNOSTIC_UNAVAILABLE"
    finally:
        await page.close()
    return result


def verified_player_page(url, day, race):
    """Accept only the official replay URL obtained after a real UI click."""
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "livebb.jlc.ne.jp" or
            parsed.path != "/bb_top/sp_bb/streamer/streamer26pi.php"):
        return False
    params = parse_qs(parsed.query, keep_blank_values=True)
    expected = {"tenji": "1", "jo": "10", "race": f"{race:02d}",
                "date": day.replace("-", "")}
    return all(params.get(key) == [value] for key, value in expected.items())


async def try_replay_from_archive(context, day, race):
    """No selection if day group or race image is ambiguous."""
    result = {
        "player_status": "ARCHIVE_TARGET_UNVERIFIED",
        "ui_click_attempted": False,
        "exact_day_race_verified": False,
        "video_element_count": 0,
        "video_play_invoked": False,
        "video_time_advanced": False,
    }
    page = await context.new_page()
    try:
        response = await page.goto(ARCHIVE, wait_until="domcontentloaded", timeout=25000)
        if response is None or not 200 <= response.status < 400:
            result["player_status"] = "ARCHIVE_UNAVAILABLE"
            return result
        await page.wait_for_timeout(1800)
        phase = "EXPAND_MEETING_AND_DAY"
        # Open the *visible* meeting/day sections in the official UI, as the
        # verified Windows Edge probe did. No race link is activated yet.
        expansion = await page.evaluate("""async args=>{
          const visible=e=>!!e.getClientRects().length &&
            getComputedStyle(e).visibility!=='hidden';
          const clickText=needle=>{
            const hits=[...document.querySelectorAll('span,button,a,div,td,p,li')]
              .filter(e=>visible(e)&&(e.textContent||'').trim().includes(needle)
                && (e.textContent||'').trim().length<140);
            hits.sort((a,b)=>a.textContent.trim().length-b.textContent.trim().length);
            if(!hits.length)return false;
            hits[0].click();return true;
          };
          const str=document.body.innerText||'';
          const found=[...new Set(str.match(/20[0-9]{2}[/][0-9]{1,2}[/][0-9]{1,2}/g)||[])]
            .filter(v=>new Date(v)<=new Date(args.full)).sort();
          const meeting=found.length?clickText(found[found.length-1]):false;
          await new Promise(resolve=>setTimeout(resolve,500));
          const day=clickText(args.short);
          await new Promise(resolve=>setTimeout(resolve,500));
          return {meeting,day};
        }""", {"full":day.replace("-","/").replace("-","/"),
                 "short":f"{int(day[5:7])}/{int(day[8:10])}"})
        result["meeting_toggle_clicked"]=bool(expansion["meeting"])
        result["day_toggle_clicked"]=bool(expansion["day"])
        phase = "LOCATE_UNIQUE_RACE_ICON"
        handle = await page.evaluate_handle("""args=>{
          const imgIs=(img,n)=>new RegExp('(?:^|/)' + n +
            'R[.](?:png|gif)(?:[?]|$)','i').test(img.getAttribute('src')||'');
          const leaves=[...document.querySelectorAll('body *')].filter(
            el=>el.children.length===0 && (el.textContent||'').trim().includes(args.day));
          const groups=new Set();
          for(const leaf of leaves.slice(0,30)){
            let el=leaf;
            for(let level=0;level<7 && el;level++,el=el.parentElement){
              const images=[...el.querySelectorAll('img')];
              if(images.length>=12 && images.length<=24 &&
                 images.filter(img=>imgIs(img,1)).length===1){
                groups.add(el);break;
              }
            }
          }
          if(groups.size!==1)return null;
          const matches=[...[...groups][0].querySelectorAll('img')].filter(
            img=>imgIs(img,args.race));
          return matches.length===1?matches[0]:null;
        }""", {"day":f"{int(day[5:7])}/{int(day[8:10])}", "race":race})
        icon=handle.as_element()
        if icon is None:
            result["player_status"] = "TARGET_DAY_RACE_AMBIGUOUS"
            return result
        # The official page sometimes scrolls/collapses after expanding.
        # Check a fresh point hit against the exact day-group 1R anchor.
        result["target_image_visible"]=bool(await icon.is_visible())
        if not result["target_image_visible"]:
            result["player_status"]="TARGET_IMAGE_COLLAPSED_NO_CLICK"
            return result
        phase = "SCROLL_TARGET_IMAGE"
        try:
            await icon.scroll_into_view_if_needed(timeout=4500)
        except Exception:
            result["player_status"]="TARGET_IMAGE_NOT_SCROLLABLE_NO_CLICK"
            return result
        box = await icon.bounding_box()
        result["target_has_box"]=bool(box and box["width"]>1 and box["height"]>1)
        if not result["target_has_box"]:
            result["player_status"]="TARGET_IMAGE_NOT_VISIBLE_NO_CLICK"
            return result
        point={"x":box["x"]+box["width"]/2,"y":box["y"]+box["height"]/2}
        hit=await page.evaluate("""point=>{
          const el=document.elementFromPoint(point.x,point.y);
          if(!el)return false;
          const imgIs=e=>e && e.tagName==='IMG' &&
            /(?:^|\/)1R[.]png(?:[?]|$)/i.test(e.getAttribute('src')||'');
          if(imgIs(el))return true;
          const anchor=el.closest('a');
          return !!anchor && [...anchor.querySelectorAll('img')].some(imgIs);
        }""",point)
        result["target_click_hit_verified"]=bool(hit)
        if not hit:
            result["player_status"]="RACE_ICON_HIT_NOT_VERIFIED_NO_CLICK"
            return result
        popups=[]
        page.on("popup", lambda p: popups.append(p))
        phase = "TRUSTED_RACE_ICON_CLICK"
        await page.mouse.click(point["x"],point["y"])
        result["ui_click_attempted"]=True
        phase = "PLAYER_URL_VERIFY"
        await page.wait_for_timeout(3500)
        player=popups[-1] if popups else page
        try:
            await player.wait_for_load_state("domcontentloaded", timeout=7000)
        except Exception:
            pass
        if not verified_player_page(player.url, day, race):
            result["player_status"] = "OPENED_PAGE_NOT_VERIFIED_REPLAY"
            return result
        result["exact_day_race_verified"]=True
        result["player_status"]="VERIFIED_REPLAY_NO_VIDEO"
        await player.wait_for_timeout(3200)
        phase = "PLAYER_VIDEO_STATE"
        for frame in player.frames[:16]:
            try:
                sample=await frame.evaluate("""async()=>{
                  const vs=[...document.querySelectorAll('video')];
                  if(vs.length!==1)return {count:vs.length,started:false,advanced:false};
                  const v=vs[0],before=v.currentTime;
                  let started=false;
                  if(v.paused){
                    try{await v.play();started=true;}catch(e){
                      return {count:1,started:true,advanced:false};
                    }
                  }
                  await new Promise(resolve=>setTimeout(resolve,2200));
                  return {count:1,started,advanced:!v.paused && !v.ended &&
                    v.currentTime>before+0.25};
                }""")
                result["video_element_count"] += int(sample["count"])
                result["video_play_invoked"] |= bool(sample["started"])
                result["video_time_advanced"] |= bool(sample["advanced"])
            except Exception:
                pass
        if result["video_time_advanced"]:
            result["player_status"]="CLOUD_OFFICIAL_REPLAY_CLOCK_ADVANCING"
        elif result["video_element_count"]:
            result["player_status"]="VERIFIED_PLAYER_NO_PLAYBACK_PROGRESS"
        return result
    except Exception as exc:
        result["player_status"]="CLOUD_PLAYER_DIAGNOSTIC_UNAVAILABLE"
        result["failure_stage"]=locals().get("phase","ARCHIVE_OPEN")
        result["failure_exception_type"]=type(exc).__name__
        return result
    finally:
        await page.close()


async def inspect(day, race, try_player=False):
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
        "archive_site_loaded": False,
        "archive_requested_day_visible": False,
        "archive_race_one_images_total": 0,
        "archive_day_group_candidates": 0,
        "archive_status": "ARCHIVE_NOT_TESTED",
        "player_status": "NOT_REQUESTED",
        "ui_click_attempted": False,
        "video_play_invoked": False,
        "video_time_advanced": False,
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
                report.update(await inspect_archive(context, day))
                if try_player and report["archive_day_group_candidates"] == 1:
                    report.update(await try_replay_from_archive(context, day, race))
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
    parser.add_argument("--try-player", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(inspect(args.date, args.race, try_player=args.try_player))
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
