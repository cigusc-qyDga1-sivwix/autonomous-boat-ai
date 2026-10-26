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
