"""Bounded incident watchdog: dispatch the existing collector, never generate bets."""
import argparse
import base64
import json
import os
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
if __package__:
    from .official_results_watchdog import Client, FORECAST, active_target
else:
    from official_results_watchdog import Client, FORECAST, active_target

JST = ZoneInfo('Asia/Tokyo')
TARGET = '.github/workflows/boat-lab-auto.yml'

def should_dispatch(age_seconds, active, since_dispatch):
    return not active and age_seconds >= 120 and since_dispatch >= 180

def target_window(now, day, start_hour):
    if now.tzinfo is None:
        raise ValueError('An aware clock is required')
    local = now.astimezone(JST)
    if local.date().isoformat() != day:
        return 'expired'
    return 'waiting' if local.hour < start_hour else 'open'


def captured_at(doc, day, now):
    if (not isinstance(doc, dict) or doc.get('schema') != 'boatlabs.forecast_capture.v1'
            or doc.get('event_date') != day or doc.get('status') != 'completed'):
        return None
    try:
        stamp = datetime.fromisoformat(doc['captured_at_utc'])
        if stamp.tzinfo is None or (stamp-now).total_seconds() > 60:
            return None
        return stamp
    except (KeyError, ValueError, TypeError):
        return None


def check(client, day, start_hour, now, since_dispatch):
    if target_window(now, day, start_hour) != 'open':
        return False, {'date': day, 'window': target_window(now, day, start_hour)}
    runs = client.request(client.api + '/actions/workflows/boat-lab-auto.yml/runs?branch=main&per_page=30')['workflow_runs']
    active = active_target(runs, FORECAST)
    doc = None
    try:
        item = client.content('app/data/live/forecast-sync-latest.json')
        if item.get('encoding') == 'base64':
            doc = json.loads(base64.b64decode(item['content']))
    except Exception:
        pass
    stamp = captured_at(doc, day, now)
    age = max(0, (now-stamp).total_seconds()) if stamp else float('inf')
    dispatch = should_dispatch(age, active, since_dispatch)
    if dispatch:
        client.dispatch(FORECAST)
    return dispatch, {
        'checked_at_utc': now.isoformat(), 'date': day,
        'forecast_capture_age_seconds': round(age) if stamp else None,
        'collector_active': active, 'dispatched': dispatch,
        'freshness_source': 'forecast_capture_only_not_result_or_audit_updates',
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--day', required=True)
    parser.add_argument('--minutes', type=int, default=345)
    parser.add_argument('--start-hour', type=int, choices=range(24), default=0)
    args = parser.parse_args()
    datetime.strptime(args.day, '%Y-%m-%d')
    client = Client(os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_TOKEN'])
    end = time.monotonic() + min(max(args.minutes, 1), 345)*60
    last_dispatch = float('-inf')
    while time.monotonic() < end:
        now = datetime.now(timezone.utc)
        window = target_window(now, args.day, args.start_hour)
        if window == 'expired':
            print('Target day ended; watchdog stopped', flush=True)
            break
        if window == 'waiting':
            time.sleep(30)
            continue
        try:
            dispatch, report = check(client, args.day, args.start_hour, now,
                                     time.monotonic()-last_dispatch)
            if dispatch:
                last_dispatch = time.monotonic()
            print(json.dumps(report), flush=True)
        except Exception as exc:
            # Never print request headers, token, or response bodies.
            print('Watchdog check failed: ' + type(exc).__name__, flush=True)
        time.sleep(30)

if __name__ == '__main__':
    main()
