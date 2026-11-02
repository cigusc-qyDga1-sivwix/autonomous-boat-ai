from scripts.prediction_watchdog import should_dispatch
import base64
import json
from datetime import datetime
from scripts.prediction_watchdog import captured_at, check
from scripts.official_results_watchdog import FORECAST

def test_stale_snapshot_starts_collector():
    assert should_dispatch(300, False, 500)

def test_active_collector_is_never_duplicated():
    assert not should_dispatch(900, True, 500)

def test_fresh_snapshot_does_not_start_work():
    assert not should_dispatch(60, False, 500)

def test_dispatch_cooldown_prevents_queue_flood():
    assert not should_dispatch(300, False, 60)

def test_unavailable_public_feed_still_requests_recovery():
    assert should_dispatch(float('inf'), False, 500)


def test_daytime_window_uses_jst_and_stops_at_next_midnight():
    from datetime import datetime
    from scripts.prediction_watchdog import target_window
    assert target_window(datetime.fromisoformat('2026-10-26T20:59:00+00:00'),'2026-10-27',6)=='waiting'
    assert target_window(datetime.fromisoformat('2026-10-26T21:00:00+00:00'),'2026-10-27',6)=='open'
    assert target_window(datetime.fromisoformat('2026-10-27T14:59:59+00:00'),'2026-10-27',6)=='open'
    assert target_window(datetime.fromisoformat('2026-10-27T15:00:00+00:00'),'2026-10-27',6)=='expired'


class ClientFixture:
    api='https://api.github.com/repos/example/boat'
    def __init__(self,heartbeat,runs=None):
        self.heartbeat=heartbeat;self.runs=runs or [];self.dispatched=[]
    def request(self,url):
        assert '/actions/workflows/boat-lab-auto.yml/runs?' in url
        return {'workflow_runs':self.runs}
    def content(self,path):
        assert path=='app/data/live/forecast-sync-latest.json'
        return {'encoding':'base64','content':base64.b64encode(json.dumps(self.heartbeat).encode()).decode()}
    def dispatch(self,target):self.dispatched.append(target)


def test_fresh_results_never_mask_a_stale_prediction_capture():
    now=datetime.fromisoformat('2026-11-03T01:00:00+00:00')
    doc={'schema':'boatlabs.forecast_capture.v1','event_date':'2026-11-03','status':'completed',
         'captured_at_utc':'2026-11-03T00:45:00+00:00','updated_at_utc':now.isoformat(),
         'official_results_updated_at_utc':now.isoformat()}
    client=ClientFixture(doc)
    dispatched,report=check(client,'2026-11-03',6,now,500)
    assert dispatched and client.dispatched==[FORECAST]
    assert report['forecast_capture_age_seconds']==900
    doc['captured_at_utc']='2026-11-03T00:59:30+00:00'
    assert not check(ClientFixture(doc),'2026-11-03',6,now,500)[0]


def test_queued_collector_and_cooldown_prevent_duplicate_dispatches():
    now=datetime.fromisoformat('2026-11-03T01:00:00+00:00')
    run={'path':FORECAST+'@main','head_branch':'main','status':'queued'}
    client=ClientFixture({},[run])
    assert not check(client,'2026-11-03',6,now,500)[0]
    assert client.dispatched==[]
    assert not check(ClientFixture({}),'2026-11-03',6,now,60)[0]


def test_bad_clock_and_day_cannot_report_a_fresh_capture():
    now=datetime.fromisoformat('2026-11-03T01:00:00+00:00')
    base={'schema':'boatlabs.forecast_capture.v1','event_date':'2026-11-03','status':'completed'}
    for stamp in ['2026-11-03T01:05:00+00:00','2026-11-03T01:00:00','bad']:
        assert captured_at({**base,'captured_at_utc':stamp},'2026-11-03',now) is None
    client=ClientFixture({})
    assert not check(client,'2026-11-02',6,now,500)[0]
    assert client.dispatched==[]
