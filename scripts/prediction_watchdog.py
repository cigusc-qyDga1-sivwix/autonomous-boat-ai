"""Bounded incident watchdog: dispatch the existing collector, never generate bets."""
import argparse
import json
import os
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

JST = ZoneInfo('Asia/Tokyo')
TARGET = '.github/workflows/boat-lab-auto.yml'

def should_dispatch(age_seconds, active, since_dispatch):
    return not active and age_seconds >= 120 and since_dispatch >= 180

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--day', required=True)
    parser.add_argument('--minutes', type=int, default=345)
    args = parser.parse_args()
    repo = os.environ['GITHUB_REPOSITORY']
    if repo != 'cigusc-qyDga1-sivwix/autonomous-boat-ai':
        raise SystemExit('Unexpected repository')
    token = os.environ['GITHUB_TOKEN']
    api = 'https://api.github.com/repos/' + repo
    def request(url, payload=None):
        headers = {'User-Agent': 'boat-lab-prediction-watchdog'}
        if url.startswith(api + '/'):
            headers['Authorization'] = 'Bearer ' + token
            headers['Accept'] = 'application/vnd.github+json'
        data = None if payload is None else json.dumps(payload).encode()
        req = Request(url, data=data, headers=headers)
        with urlopen(req, timeout=20) as response:
            raw = response.read()
        return json.loads(raw) if raw else {}
    end = time.monotonic() + min(max(args.minutes, 1), 345)*60
    last_dispatch = float('-inf')
    while time.monotonic() < end:
        now = datetime.now(timezone.utc)
        if now.astimezone(JST).date().isoformat() != args.day:
            print('Target day ended; watchdog stopped', flush=True)
            break
        try:
            runs = request(api + '/actions/runs?per_page=50')['workflow_runs']
            active = any(r.get('path') == TARGET and r.get('head_branch') == 'main'
                         and r.get('status') != 'completed' for r in runs)
            try:
                audit = request('https://cigusc-qydga1-sivwix.github.io/autonomous-boat-ai/data/live/audit-latest.json?watchdog=' + str(int(now.timestamp())))
                stamp = datetime.fromisoformat(audit['source_updated_at_utc'])
                age = max(0, (now-stamp).total_seconds()) if audit.get('event_date') == args.day else float('inf')
            except Exception:
                age = float('inf')
            dispatch = should_dispatch(age, active, time.monotonic()-last_dispatch)
            if dispatch:
                request(api + '/actions/workflows/boat-lab-auto.yml/dispatches', {'ref':'main'})
                last_dispatch = time.monotonic()
            print(json.dumps({'checked_at_utc':now.isoformat(), 'source_age_seconds':round(age) if age != float('inf') else None,
                              'collector_active':active, 'dispatched':dispatch}), flush=True)
        except Exception as exc:
            # Never print request headers, token, or response bodies.
            print('Watchdog check failed: ' + type(exc).__name__, flush=True)
        time.sleep(30)

if __name__ == '__main__':
    main()
