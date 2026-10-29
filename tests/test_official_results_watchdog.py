"""Exercise recovery without scheduling real jobs or calculating forecasts."""
import base64
import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from scripts.official_results_watchdog import (
    Client, COOLDOWN_SECONDS, FORECAST, PUBLIC_ROOT, PUBLISH, REPOSITORY,
    RESULTS, STALE_SECONDS, check, choose_target, snapshot_time, target_window,
)

DAY = "2026-10-29"
NOW = datetime(2026, 10, 29, 6, 30, tzinfo=timezone.utc)


def snapshot(age=0, count=1):
    return {
        "date": DAY, "status": "verified_by_server_fetch",
        "evidence_type": "official_boatrace_pay_snapshot",
        "source_url": "https://www.boatrace.jp/owpc/pc/race/pay?hd=20261029",
        "retrieved_at_utc": (NOW-timedelta(seconds=age)).isoformat(),
        "results": {str(n): {"finish": "1-2-3", "payout_per_100": 500} for n in range(count)},
    }


def select(backend=None, public=None, runs=None, elapsed=None, **kwargs):
    return choose_target(NOW, DAY, 6, backend, public, runs or [], elapsed or {}, **kwargs)


class DecisionTests(unittest.TestCase):
    def test_fresh_source_and_publication_need_no_job(self):
        self.assertIsNone(select(snapshot(30), snapshot(30)))

    def test_hour_long_gap_recovers_existing_result_collector(self):
        self.assertEqual(select(snapshot(3600), snapshot(3600)), RESULTS)
        self.assertEqual(select(snapshot(STALE_SECONDS), snapshot(STALE_SECONDS)), RESULTS)

    def test_missing_or_unverified_evidence_never_counts_as_fresh(self):
        invalid = snapshot()
        invalid["status"] = "not_verified"
        self.assertIsNone(snapshot_time(invalid, DAY, NOW))
        self.assertEqual(select(invalid, snapshot()), RESULTS)
        self.assertEqual(select(None, None), RESULTS)

    def test_future_timestamp_cannot_hide_stalled_collection(self):
        self.assertEqual(select(snapshot(-600), snapshot()), RESULTS)

    def test_queued_or_active_collector_prevents_duplicate_dispatch(self):
        for status in ("queued", "pending", "in_progress", "waiting"):
            with self.subTest(status=status):
                active = [{"path": RESULTS, "head_branch": "main", "status": status}]
                self.assertIsNone(select(snapshot(3600), snapshot(3600), active))

    def test_completed_failure_and_other_branch_do_not_block_recovery(self):
        runs = [{"path": RESULTS, "head_branch": "main", "status": "completed", "conclusion": "failure"},
                {"path": RESULTS, "head_branch": "other", "status": "in_progress"}]
        self.assertEqual(select(snapshot(3600), snapshot(3600), runs), RESULTS)

    def test_cooldown_prevents_repeated_dispatch_before_run_is_listed(self):
        self.assertIsNone(select(snapshot(3600), snapshot(3600), elapsed={RESULTS: COOLDOWN_SECONDS-1}))

    def test_fresh_backend_but_stale_publication_recovers_publisher_only(self):
        self.assertEqual(select(snapshot(60), snapshot(3600)), PUBLISH)
        self.assertEqual(select(snapshot(60), None), PUBLISH)

    def test_allow_running_publisher_and_propagation_time(self):
        active = [{"path": PUBLISH, "head_branch": "main", "status": "in_progress"}]
        self.assertIsNone(select(snapshot(60), snapshot(3600), active))
        self.assertIsNone(select(snapshot(20), snapshot(3600)))

    def test_source_recovery_has_priority_over_publishing_stale_evidence(self):
        self.assertEqual(select(snapshot(600), snapshot(3600)), RESULTS)

    def test_missing_daily_ledger_starts_only_existing_guarded_collector(self):
        self.assertEqual(select(None, None, ledger_exists=False), FORECAST)

    def test_JST_window_and_midnight_expiry(self):
        early = datetime(2026, 10, 28, 20, 0, tzinfo=timezone.utc)
        self.assertEqual(target_window(early, DAY, 6), "waiting")
        self.assertIsNone(choose_target(early, DAY, 6, None, None, [], {}))
        midnight = datetime(2026, 10, 29, 15, 0, tzinfo=timezone.utc)
        self.assertEqual(target_window(midnight, DAY, 6), "expired")
        self.assertIsNone(choose_target(midnight, DAY, 6, None, None, [], {}))
        with self.assertRaises(ValueError):
            target_window(NOW.replace(tzinfo=None), DAY, 6)


class ClientTests(unittest.TestCase):
    def test_token_is_sent_only_to_the_existing_repository_API(self):
        client = Client(REPOSITORY, "test-token")
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{}'
        with patch("scripts.official_results_watchdog.urlopen", return_value=response) as opener:
            client.request(client.api+"/actions/runs?per_page=100")
            self.assertEqual(opener.call_args.args[0].get_header("Authorization"), "Bearer test-token")
            client.request(PUBLIC_ROOT+"data/live/official-pay/"+DAY+".json")
            self.assertIsNone(opener.call_args.args[0].get_header("Authorization"))
        with self.assertRaises(ValueError):
            client.request("https://unrelated.example/")

    def test_small_API_snapshot_decodes_and_dispatch_is_main_only(self):
        client = Client(REPOSITORY, "test-token")
        doc = snapshot()
        with patch.object(client, "request") as request:
            request.return_value = {"encoding": "base64", "content": base64.b64encode(json.dumps(doc).encode()).decode()}
            self.assertEqual(client.snapshot(DAY), doc)
            client.dispatch(RESULTS)
            self.assertEqual(request.call_args.args[1], {"ref": "main"})
            self.assertTrue(request.call_args.args[0].endswith("/official-results-fast.yml/dispatches"))
            with self.assertRaises(ValueError):
                client.dispatch("unrelated.yml")

    def test_recovery_observes_progress_and_stops_duplicate_dispatches(self):
        client = MagicMock()
        client.api = "https://api.github.com/repos/"+REPOSITORY
        client.snapshot.return_value = snapshot(3600)
        client.request.side_effect = [{"workflow_runs": []}, snapshot(3600)]
        target, report = check(client, DAY, 6, NOW, {})
        self.assertEqual(target, RESULTS)
        client.dispatch.assert_called_once_with(RESULTS)
        self.assertEqual(report["source_age_seconds"], 3600)
        # A later successful fetch/publication is fresh and needs no further job.
        client.reset_mock()
        client.snapshot.return_value = snapshot(30, 2)
        client.request.side_effect = [{"workflow_runs": []}, snapshot(30, 2)]
        target, report = check(client, DAY, 6, NOW, {RESULTS: 60})
        self.assertIsNone(target)
        client.dispatch.assert_not_called()
        self.assertEqual(report["published_results"], 2)


if __name__ == "__main__":
    unittest.main()
