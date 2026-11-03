"""Windows Edge: official UI -> rendered frames in RAM -> unverified numbers.

Reuses PR #154's independent tracker and the rendered-frame gates developed in
scripts/mikuni_cloud_frame_research.py (blob 13ad0ec). No production imports,
stream discovery, network interception, raw media export or forecast writes.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import median
import sys
import time
from urllib.parse import parse_qs, urlsplit

from .analyzer import _no_postrace_fields, _valid_day
from .pipeline import _numeric_hash, _simultaneous
from .report_io import write_report

SCHEMA = "boatlabs.vision_ai.windows_rendered_candidate_run.v1"
MODEL = "vision-windows-rendered-candidates-v0.1"
ENTRY = "https://livebb.jlc.ne.jp/bb_top/new_bb/index.php?tpl=10"
PLAYER_HOST = "front.player.boatrace-cdn.jp"
JST = timezone(timedelta(hours=9))
MAX_FRAME_BYTES = 3_000_000
MAX_SEQUENCE_BYTES = 24_000_000
SUCCESS = "RENDERED_CANDIDATES_UNVERIFIED"
TERMINAL = {"VIEWING_DENIED", "PLAYER_IDENTITY_MISMATCH", "PLAYER_AMBIGUOUS", "VISIBLE_VIDEO_AMBIGUOUS", "PLAY_BUTTON_AMBIGUOUS", "RUNTIME_UNAVAILABLE", "BROWSER_RUNTIME_FAILED"}

class CaptureError(Exception):
    """Only a fixed, non-sensitive classification is logged."""
    pass


def validate_config(config, *, now=None):
    if not isinstance(config, dict):
        raise ValueError("config_object_required")
    _no_postrace_fields(config)
    allowed = {"schema", "venue_code", "event_date", "races", "permission_reference", "sample_count", "sample_interval_ms", "clip_starts_seconds", "max_attempts", "retry_interval_seconds"}
    if set(config) - allowed or config.get("schema") != "boatlabs.vision_ai.windows_runner_config.v1":
        raise ValueError("config_schema_invalid")
    if config.get("venue_code") != "10":
        raise ValueError("initial_runner_is_mikuni_only")
    reference = config.get("permission_reference")
    if not isinstance(reference, str) or not 1 <= len(reference.strip()) <= 200:
        raise ValueError("permission_reference_required")
    day = config.get("event_date")
    today = (now or datetime.now(JST)).astimezone(JST).date()
    if day == "today":
        day = today.isoformat()
    if not _valid_day(day) or date.fromisoformat(day) > today:
        raise ValueError("valid_nonfuture_event_date_required")
    races = config.get("races")
    if (not isinstance(races, list) or not 1 <= len(races) <= 12 or
        any(type(r) is not int or not 1 <= r <= 12 for r in races) or len(set(races)) != len(races)):
        raise ValueError("unique_races_1_to_12_required")
    count = config.get("sample_count", 12)
    interval = config.get("sample_interval_ms", 700)
    attempts = config.get("max_attempts", 3)
    retry = config.get("retry_interval_seconds", 180)
    for value, lower, upper, label in [(count, 6, 24, "sample_count"), (interval, 300, 1500, "sample_interval"), (attempts, 1, 5, "attempts"), (retry, 120, 3600, "retry_interval")]:
        if type(value) is not int or not lower <= value <= upper:
            raise ValueError("invalid_" + label)
    clips = config.get("clip_starts_seconds", [0, 30, 60])
    if (not isinstance(clips, list) or not 1 <= len(clips) <= 3 or
        any(type(t) is not int or not 0 <= t <= 180 for t in clips) or len(set(clips)) != len(clips)):
        raise ValueError("invalid_clip_starts")
    return {**config, "event_date": day, "sample_count": count, "sample_interval_ms": interval,
            "clip_starts_seconds": sorted(clips), "max_attempts": attempts, "retry_interval_seconds": retry}


def _query(url, host, path):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname != host or parsed.path != path
                or parsed.username or parsed.password or parsed.port not in (None, 443)):
            return None
        values = parse_qs(parsed.query, keep_blank_values=True)
        if any(len(v) != 1 for v in values.values()):
            return None
        return {k: v[0] for k, v in values.items()}
    except (ValueError, TypeError):
        return None


def matches_player(url, day, race):
    q = _query(url, PLAYER_HOST, "/player/vod")
    return bool(q and q.get("service") == "jyobb" and q.get("stadium") == "10mikuni"
                and q.get("raceType") == "exhibition" and q.get("raceDate") == day.replace("-", "")
                and q.get("raceNumber") in {str(race), f"{race:02}"})


def matches_wrapper(url, day, race):
    q = _query(url, "livebb.jlc.ne.jp", "/bb_top/new_bb/streamer/streamer.php")
    return bool(q and q.get("md") == "T" and q.get("jo") == "10" and q.get("ymd") == day
                and q.get("race") in {str(race), f"{race:02}"})


def parse_official_link(handler):
    """Read only the public date/R/type attributes; never execute supplied JS."""
    if not isinstance(handler, str) or len(handler) > 200:
        return None
    match = re.fullmatch(r"\s*ymd='(\d{4}-\d{2}-\d{2})';race=(\d{1,2});md='T';createpageset\(\);?\s*", handler)
    if not match or not _valid_day(match[1]) or not 1 <= int(match[2]) <= 12:
        return None
    return match[1], int(match[2])


def base_report(config, race):
    return {"schema": SCHEMA, "model_version": MODEL, "event_date": config["event_date"], "venue_code": "10", "race": race,
            "permission_reference": config["permission_reference"], "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "NOT_STARTED", "input_kind": "official_player_rendered_frames", "source_media_sha256": None,
            "original_media_bytes_received": False, "rendered_frame_sequence_sha256": None,
            "stages": {"official_race_selected": False, "player_identity_matched": False, "playback_clock_advanced": False,
                       "rendered_frames_received": False, "dynamic_pixels_observed": False, "candidate_tracking_computed": False,
                       "six_candidates_simultaneous": False},
            "candidate_boat_tracks": 0, "confirmed_boat_tracks": 0, "real_footage_independently_verified": False,
            "physical_speed_calibrated": False, "eligible_for_formal_forecast": False, "eligible_for_shadow_forecast": False,
            "official_results_used": False, "bets_generated": 0, "raw_media_bytes_persisted": 0, "raw_frames_persisted": 0,
            "persistence_counter_scope": "APPLICATION_OUTPUT_ONLY",
            "browser_storage": "TEMPORARY_ISOLATED_PROFILE", "cloud_sync": "NOT_CONFIGURED_LOCAL_NUMERIC_OUTBOX_ONLY"}


def finish(report):
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    report.pop("report_sha256", None)
    report["report_sha256"] = _numeric_hash(report)
    return report


def analyze_rendered_samples(images, timestamps):
    """Conservative actual-pixel gate, followed by PR #154's unchanged tracker."""
    import cv2
    import numpy as np
    from .tracking import analyze_automatic_frames
    if not isinstance(images, (list, tuple)) or not 6 <= len(images) <= 24 or len(images) != len(timestamps):
        raise ValueError("insufficient_rendered_frames")
    if (any(type(t) not in (float, int) or not math.isfinite(t) or t < 0 for t in timestamps)
            or any(not .15 <= b-a <= 3 for a,b in zip(timestamps, timestamps[1:]))):
        raise ValueError("video_clock_invalid_or_stalled")
    intervals = [b-a for a,b in zip(timestamps, timestamps[1:])]
    dt = median(intervals)
    if any(abs(gap-dt) > .25*dt for gap in intervals):
        raise ValueError("rendered_sample_timing_unstable")
    frames, jpegs = [], []
    original_shape = None
    digest = hashlib.sha256()
    total = 0
    for encoded, timestamp in zip(images, timestamps):
        if not isinstance(encoded, bytes) or not 100 <= len(encoded) <= MAX_FRAME_BYTES:
            raise ValueError("invalid_rendered_frame")
        total += len(encoded)
        if total > MAX_SEQUENCE_BYTES:
            raise ValueError("rendered_sequence_too_large")
        im = cv2.imdecode(np.frombuffer(encoded, np.uint8), cv2.IMREAD_COLOR)
        if im is None:
            raise ValueError("unreadable_rendered_frame")
        height, width = im.shape[:2]
        if not 120 <= width <= 1920 or not 80 <= height <= 1080:
            raise ValueError("rendered_frame_dimensions_invalid")
        if original_shape is not None and original_shape != im.shape:
            raise ValueError("rendered_frame_dimensions_changed")
        original_shape = im.shape
        digest.update(len(encoded).to_bytes(4, 'big'))
        digest.update(f"{timestamp:.6f}".encode('ascii'))
        digest.update(encoded)
        scaled = im if width <= 640 else cv2.resize(im, (640, round(height*640/width)), interpolation=cv2.INTER_AREA)
        frames.append(scaled)
        ok, jpeg = cv2.imencode('.jpg', scaled, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            raise ValueError("rendered_frame_encode_failed")
        jpegs.append(jpeg.tobytes())
    result = {"rendered_frame_sequence_sha256": digest.hexdigest(), "sampled_frames": len(frames),
              "sample_video_timestamps_s": [round(t, 4) for t in timestamps],
              "rendered_frame_size": {"width": width, "height": height},
              "analysis_frame_size": {"width": frames[0].shape[1], "height": frames[0].shape[0]},
              "median_sample_interval_s": round(dt, 4)}
    try:
        brightness = float(np.mean([np.mean(im) for im in frames]))
        contrast = float(np.mean([np.std(im) for im in frames]))
        moving = sum(float(np.mean(cv2.absdiff(a,b))) >= 1.0 for a,b in zip(frames,frames[1:]))
        result.update({"brightness_mean": round(brightness, 3), "contrast_mean": round(contrast, 3), "visually_changing_frame_pairs": moving})
        if brightness < 8 or contrast < 4 or moving < max(3, len(frames)//3):
            result["status"] = "RENDERED_FRAMES_STATIC_OR_BLACK"
            return result
        tracking = analyze_automatic_frames(jpegs, sample_interval_s=dt)
        tracking['motion_timebase'] = 'median_browser_clock_interval_approximate'
        # Preserve the actual browser clock, rather than claiming regular samples.
        for track in tracking['unverified_tracks']:
            for sample in track['samples']:
                sample['t_s'] = round(timestamps[sample['frame']] - timestamps[0], 4)
        simultaneous = _simultaneous(tracking)
        result.update({"status": SUCCESS, "tracking": tracking, "candidate_boat_tracks": tracking['candidate_boat_tracks'],
                       "simultaneous_six_candidate_frames": simultaneous, "six_candidates_simultaneous": simultaneous >= 4})
        return result
    finally:
        frames.clear()
        jpegs.clear()


_STATE_JS = """v=>({time:v.currentTime,ready:v.readyState,width:v.videoWidth,height:v.videoHeight,
 paused:v.paused,ended:v.ended,duration:Number.isFinite(v.duration)?v.duration:null,error:!!v.error})"""
_DENIED = ('視聴は許可されていません', '視聴が許可されていません', 'access denied', 'not authorized', 'not permitted')


def check_denied(frame):
    try:
        text = frame.locator('body').inner_text(timeout=1200).lower()
    except Exception:
        return
    if any(s in text for s in _DENIED):
        raise CaptureError('VIEWING_DENIED')


def pick_player(page, day, race):
    wrappers = [f for f in page.frames if matches_wrapper(f.url, day, race)]
    players = [f for f in page.frames if matches_player(f.url, day, race)]
    if len(wrappers) != 1 or len(players) != 1:
        raise CaptureError('PLAYER_AMBIGUOUS' if len(players) > 1 or len(wrappers) > 1 else 'PLAYER_NOT_READY')
    parent = players[0].parent_frame
    if parent != wrappers[0]:
        raise CaptureError('PLAYER_IDENTITY_MISMATCH')
    return players[0]


def verify_player(frame, day, race):
    if not matches_player(frame.url, day, race) or not matches_wrapper(frame.parent_frame.url, day, race):
        raise CaptureError('PLAYER_IDENTITY_MISMATCH')
    check_denied(frame)


def _select_race(page, day, race):
    tab = page.locator('#switcher_tenji')
    tab.wait_for(state='visible', timeout=15000)
    tab.click()
    page.locator('#container_right a[onclick]').first.wait_for(state='visible', timeout=15000)
    links = page.locator('#container_right a[onclick]')
    selected = []
    for link in links.all():
        if link.is_visible() and parse_official_link(link.get_attribute('onclick')) == (day, race):
            selected.append(link)
    if len(selected) != 1:
        raise CaptureError('RACE_NOT_AVAILABLE' if not selected else 'RACE_LINK_AMBIGUOUS')
    selected[0].click()


def _wait_visible_video(frame, day, race, diagnostics=None):
    """The player iframe can exist before its video is created or shown."""
    probe = diagnostics if diagnostics is not None else {}
    clicked = False
    for attempt in range(51):
        verify_player(frame, day, race)
        videos = frame.locator('video').all()
        visible = [video for video in videos if video.is_visible()]
        probe.update(video_elements=len(videos), visible_video_elements=len(visible),
                     wait_intervals=attempt, play_button_clicked=clicked)
        if len(visible) > 1:
            raise CaptureError('VISIBLE_VIDEO_AMBIGUOUS')
        if len(visible) == 1:
            return visible[0]
        buttons = [button for button in frame.get_by_role('button', name='Play Video', exact=True).all()
                   if button.is_visible()]
        probe['visible_play_buttons'] = len(buttons)
        if len(buttons) > 1:
            raise CaptureError('PLAY_BUTTON_AMBIGUOUS')
        if not clicked and buttons:
            buttons[0].click()
            clicked = True
            probe['play_button_clicked'] = True
        if attempt < 50:
            frame.wait_for_timeout(400)
    raise CaptureError('VISIBLE_VIDEO_NOT_READY')


def _start_playback(frame, day, race, diagnostics=None):
    video = _wait_visible_video(frame, day, race, diagnostics)
    probe = diagnostics if diagnostics is not None else {}
    video.evaluate("v=>{v.muted=true;}")
    clicked = False
    requested = False
    start = None
    for attempt in range(75):
        verify_player(frame, day, race)
        buttons = [b for b in frame.get_by_role('button', name='Play Video', exact=True).all() if b.is_visible()]
        if len(buttons) > 1:
            raise CaptureError('PLAY_BUTTON_AMBIGUOUS')
        if buttons and not clicked:
            buttons[0].click()
            clicked = True
        state = video.evaluate(_STATE_JS)
        if state['paused'] and not requested:
            video.evaluate("v=>{v.muted=true;const p=v.play();if(p)p.catch(()=>{});}")
            requested = True
        probe.update(playback_last_state=state, playback_wait_intervals=attempt,
                     playback_button_clicked=clicked, html_play_requested=requested)
        if state['ready'] >= 2 and state['width'] > 0 and state['height'] > 0 and not state['paused'] and not state['ended']:
            if start is None:
                start = state['time']
            elif state['time'] - start >= .2:
                return video
        frame.wait_for_timeout(400)
    raise CaptureError('PLAYBACK_CLOCK_NOT_ADVANCING')


def _capture_window(frame, video, config, race, start):
    day = config['event_date']
    verify_player(frame, day, race)
    state = video.evaluate(_STATE_JS)
    need = config['sample_count'] * config['sample_interval_ms'] / 1000 + 2
    if start and (state['duration'] is None or state['duration'] < start + need):
        return None
    if start:
        video.evaluate('(v,t)=>{v.currentTime=t;}', start)
        # A regular seek; never request a segment or raw media URL ourselves.
        for _ in range(20):
            verify_player(frame, day, race)
            s = video.evaluate(_STATE_JS)
            if s['ready'] >= 2 and abs(s['time']-start) < 3:
                break
            frame.wait_for_timeout(200)
        else:
            raise CaptureError('NORMAL_SEEK_NOT_READY')
    images, stamps = [], []
    total = 0
    try:
        for _ in range(config['sample_count']):
            verify_player(frame, day, race)
            s = video.evaluate(_STATE_JS)
            if s['paused'] or s['ended'] or s['ready'] < 2 or s['width'] <= 0 or s['height'] <= 0:
                raise CaptureError('PLAYBACK_INTERRUPTED')
            # Renderer screenshot is held only in RAM. It is not original media.
            png = video.screenshot(type='png', timeout=4500, animations='disabled')
            total += len(png)
            if total > MAX_SEQUENCE_BYTES or len(png) > MAX_FRAME_BYTES:
                raise CaptureError('FRAME_MEMORY_LIMIT')
            images.append(png)
            stamps.append(float(s['time']))
            frame.wait_for_timeout(config['sample_interval_ms'])
        return analyze_rendered_samples(images, stamps)
    finally:
        images.clear()
        stamps.clear()


def capture_once(config, race, *, browser_factory=None):
    config = validate_config(config)
    if race not in config['races']:
        raise ValueError('race_not_in_config')
    report = base_report(config, race)
    browser = None
    try:
        if browser_factory is None:
            from playwright.sync_api import sync_playwright
            manager = sync_playwright()
        else:
            manager = browser_factory()
        with manager as pw:
            try:
                # Installed Edge, private temporary profile. No downloaded browser.
                browser = pw.chromium.launch(channel='msedge', headless=False)
                context = browser.new_context(accept_downloads=False, ignore_https_errors=False, viewport={'width':1280,'height':800})
                context.set_default_timeout(6500)
                page = context.new_page()
                response = page.goto(ENTRY, wait_until='domcontentloaded', timeout=25000)
                if response is None or response.status >= 400:
                    raise CaptureError('OFFICIAL_PAGE_UNAVAILABLE')
                if page.url.split('#',1)[0] != ENTRY:
                    raise CaptureError('OFFICIAL_ENTRY_MISMATCH')
                _select_race(page, config['event_date'], race)
                report['stages']['official_race_selected'] = True
                player = None
                for _ in range(25):
                    try:
                        player = pick_player(page, config['event_date'], race)
                        break
                    except CaptureError as exc:
                        if str(exc) != 'PLAYER_NOT_READY':
                            raise
                    page.wait_for_timeout(400)
                if player is None:
                    raise CaptureError('PLAYER_NOT_READY')
                report['stages']['player_identity_matched'] = True
                report['player_initialization'] = {}
                video = _start_playback(player, config['event_date'], race, report['player_initialization'])
                report['stages']['playback_clock_advanced'] = True
                best = None
                windows = []
                for start in config['clip_starts_seconds']:
                    data = _capture_window(player, video, config, race, start)
                    if data is None:
                        continue
                    report['stages']['rendered_frames_received'] = True
                    windows.append({'clip_start_seconds':start,'status':data['status'],'sampled_frames':data['sampled_frames']})
                    score = (data.get('simultaneous_six_candidate_frames',0),data.get('candidate_boat_tracks',0),data.get('visually_changing_frame_pairs',0))
                    if best is None or score > best[0]:
                        best = (score,start,data)
                    if data.get('six_candidates_simultaneous'):
                        break
                report['capture_windows'] = windows
                if best is None:
                    raise CaptureError('NO_USABLE_CAPTURE_WINDOW')
                _, selected, selected_data = best
                report.update(selected_data)
                report['selected_clip_start_seconds'] = selected
                if selected_data['status'] == SUCCESS:
                    report['stages']['dynamic_pixels_observed'] = True
                    report['stages']['candidate_tracking_computed'] = True
                    report['stages']['six_candidates_simultaneous'] = selected_data['six_candidates_simultaneous']
                verify_player(player, config['event_date'], race)
            finally:
                if browser is not None:
                    browser.close()
    except ImportError:
        report['status'] = 'RUNTIME_UNAVAILABLE'
    except CaptureError as exc:
        report['status'] = str(exc)
    except ValueError as exc:
        report['status'] = 'FRAME_VALIDATION_FAILED'
        # Only our closed validation vocabulary, never arbitrary page content.
        label = str(exc)
        if re.fullmatch('[a-z_]{1,80}', label):
            report['failure_reason'] = label
    except Exception:
        report['status'] = 'BROWSER_RUNTIME_FAILED'
    return finish(report)


def save_attempt(report, output):
    output = Path(output)
    if output.suffix:
        raise ValueError('output_directory_required')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    name = f"{report['event_date']}-10-R{report['race']:02}-{stamp}.json"
    destination = output / name
    write_report(report, destination)
    return destination


def run_queue(config, output, *, watch=False, processor=capture_once, sleep=time.sleep):
    config = validate_config(config)
    maximum = config['max_attempts'] if watch else 1
    last = {}
    for attempt in range(maximum):
        for race in config['races']:
            if last.get(race) == SUCCESS:
                continue
            report = processor(config, race)
            save_attempt(report, output)
            last[race] = report['status']
            print(f"R{race:02}: {report['status']} | frames={int(report['stages']['rendered_frames_received'])} | candidates={report['candidate_boat_tracks']} | confirmed=0", flush=True)
            if report['status'] in TERMINAL:
                return 2
        if all(s == SUCCESS for s in last.values()):
            return 0
        if attempt + 1 < maximum:
            print(f"Waiting {config['retry_interval_seconds']} seconds; Ctrl+C stops the runner.", flush=True)
            sleep(config['retry_interval_seconds'])
    return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description='BOAT VISION Windows Edge research runner')
    parser.add_argument('--config', type=Path, default=Path('config.json'))
    parser.add_argument('--output', type=Path, default=Path('outbox'))
    parser.add_argument('--watch', action='store_true', help='Bounded retries only; viewing denial stops immediately')
    parser.add_argument('--check-runtime', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.check_runtime:
            import cv2
            import numpy
            from playwright.sync_api import sync_playwright
            print('READY: Python, OpenCV, NumPy and Playwright imported. Edge playback is not yet verified.')
            return 0
        config = json.loads(args.config.read_text(encoding='utf-8-sig'))
        return run_queue(config, args.output, watch=args.watch)
    except KeyboardInterrupt:
        print('Stopped. No video or frame files were saved.')
        return 130
    except (ValueError, OSError, ImportError):
        print('SETUP_OR_CONFIG_ERROR: check config.json, runtime and the writable outbox folder. No successful capture was recorded.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
