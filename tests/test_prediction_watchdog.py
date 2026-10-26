from scripts.prediction_watchdog import should_dispatch

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
