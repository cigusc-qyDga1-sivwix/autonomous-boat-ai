"""Forward-only 24 Nov outside 5/6 head study: fail-closed evidence tests."""
import copy
import unittest
from itertools import permutations

from scripts.outside_head_forward_shadow_v1 import build, POLICY_SHA256


def fixture():
    racers = [{"lane": i, "course": i, "exhibition_st": 0.15,
               "exhibition_time": 6.80, "average_start_timing": 0.17,
               "average_start_timing_imputed": False,
               "motor_top_2_percent": 35.0} for i in range(1, 7)]
    racers[0].update(exhibition_st=0.20, average_start_timing=0.18,
                     motor_top_2_percent=30)
    racers[3].update(exhibition_st=0.13, exhibition_time=6.74)
    racers[4].update(exhibition_st=0.11, exhibition_time=6.76,
                     average_start_timing=0.17, motor_top_2_percent=32)
    racers[5].update(exhibition_st=0.12, exhibition_time=6.77)
    ranked = [{"combination": "-".join(map(str, p)), "score": 1 / 120}
              for p in permutations(range(1, 7), 3)]
    bets = [{"combination": r["combination"], "virtual_yen": 1000,
             "relative_score": r["score"]} for r in ranked[:12]]
    bets[0]["virtual_yen"] += 38000
    snapshot = {
        "phase": "exhibition", "exhibition_origin": {"captured_before_cutoff": True},
        "frozen_at_utc": "2026-11-24T01:00:00+00:00",
        "cutoff_iso_jst": "2026-11-24T12:00:00+09:00",
        "racers": racers, "bets": bets,
    }
    return snapshot, ranked


class OutsideHeadForwardShadowTests(unittest.TestCase):
    def test_course5_candidate_is_prospective_and_same_budget(self):
        snap, ranked = fixture()
        frozen_original = copy.deepcopy(snap)
        report = build(snap, ranked)
        self.assertEqual(report["status"], "PRE_CUTOFF_SHADOW_SWAP_FROZEN")
        self.assertEqual(report["policy_sha256"], POLICY_SHA256)
        self.assertEqual(report["replacement"]["outside_course"], 5)
        self.assertEqual(report["replacement"]["added"].split("-")[0], "5")
        self.assertEqual(len(report["shadow_alternative_bets"]), len(snap["bets"]))
        self.assertEqual(sum(b["virtual_yen"] for b in report["shadow_alternative_bets"]), 50000)
        self.assertEqual(report["control_bets"], snap["bets"])
        self.assertFalse(report["formal_tickets_changed"])
        self.assertFalse(report["result_data_used"])
        self.assertFalse(report["calibrated"])
        self.assertEqual(snap, frozen_original)

    def test_course6_can_qualify_when_faster_than_course5(self):
        snap, ranked = fixture()
        snap["racers"][4]["exhibition_st"] = 0.16  # 5 no longer qualifies
        snap["racers"][5]["exhibition_st"] = 0.10  # 6 beats 5's ST
        snap["racers"][5]["exhibition_time"] = 6.75
        report = build(snap, ranked)
        self.assertEqual(report["status"], "PRE_CUTOFF_SHADOW_SWAP_FROZEN")
        self.assertEqual(report["replacement"]["outside_course"], 6)
        self.assertEqual(report["replacement"]["added"].split("-")[0], "6")

    def test_old_or_late_snapshot_rejected(self):
        snap, ranked = fixture()
        snap["frozen_at_utc"] = "2026-11-23T01:00:00+00:00"
        snap["cutoff_iso_jst"] = "2026-11-23T12:00:00+09:00"
        self.assertEqual(build(snap, ranked)["status"], "NOT_PROSPECTIVELY_ELIGIBLE")
        snap, ranked = fixture()
        snap["frozen_at_utc"] = "2026-11-24T02:59:00+00:00"
        self.assertEqual(build(snap, ranked)["status"], "NOT_PROSPECTIVELY_ELIGIBLE")

    def test_missing_exhibition_or_f_disables_swap(self):
        snap, ranked = fixture()
        snap["exhibition_origin"]["captured_before_cutoff"] = False
        self.assertEqual(build(snap, ranked)["status"], "NO_PRE_CUTOFF_EXHIBITION")
        snap, ranked = fixture()
        snap["racers"][4]["exhibition_st"] = -0.02
        self.assertEqual(build(snap, ranked)["status"], "INCOMPLETE_OR_IMPUTED_EXHIBITION")
        snap, ranked = fixture()
        snap["racers"][0]["average_start_timing_imputed"] = True
        self.assertEqual(build(snap, ranked)["status"], "INCOMPLETE_OR_IMPUTED_EXHIBITION")

    def test_duplicate_actual_entry_and_postrace_input_fail(self):
        snap, ranked = fixture()
        snap["racers"][4]["course"] = 4
        self.assertEqual(build(snap, ranked)["status"], "INVALID_SIX_BOAT_ENTRY")
        snap, ranked = fixture()
        snap["result"] = {"finish": "5-1-2"}
        self.assertEqual(build(snap, ranked)["status"], "REJECTED_POSTRACE_INPUT")
        snap, ranked = fixture()
        snap["racers"][0]["actual_finish"] = 2
        self.assertEqual(build(snap, ranked)["status"], "INVALID_OR_POSTRACE_RACER")

    def test_official_audit_uses_only_frozen_same_point_pairs(self):
        from scripts.forecast_audit import _outside_head_forward_shadow_report
        snap, ranked = fixture()
        snap.update({"venue": "徳山", "race": 1, "cutoff_jst": "12:00",
                     "ticket_status": "formal",
                     "model_version": "four-factor-learned-v1-conditional-choice-trained"})
        snap["outside_head_forward_shadow_v1"] = build(snap, ranked)
        source = {"verified": True, "source": "boatrace_official_pay",
                  "virtual_stake": 50000, "finish": "5-1-2",
                  "payout_per_100": 2000}
        official = {"2026-11-24|徳山|1": source}
        result = _outside_head_forward_shadow_report(
            [snap], official, {}, "2026-11-24")
        self.assertEqual(result["official_verified_sha_matched_pairs"], 1)
        self.assertEqual(result["formal"]["hits"], 0)
        self.assertEqual(result["outside_head_shadow"]["hits"], 1)
        self.assertEqual(result["head_misses_recovered"], 1)
        self.assertEqual(result["outside_head_shadow"]["virtual_stake_yen"], 50000)
        # No official evidence: must not fabricate winning payouts.
        missing = _outside_head_forward_shadow_report(
            [snap], {}, {}, "2026-11-24")
        self.assertEqual(missing["official_verified_sha_matched_pairs"], 0)
        self.assertEqual(missing["exclusions"]["unverified"], 1)
        # If the frozen control was tampered with, pair is excluded.
        modified = copy.deepcopy(snap)
        modified["bets"][0]["virtual_yen"] += 1000
        modified["bets"][1]["virtual_yen"] -= 1000
        bad = _outside_head_forward_shadow_report(
            [modified], official, {}, "2026-11-24")
        self.assertEqual(bad["official_verified_sha_matched_pairs"], 0)
        self.assertEqual(bad["exclusions"]["control_or_trial_sha_mismatch"], 1)

    def test_no_supported_signal_preserves_control(self):
        snap, ranked = fixture()
        snap["racers"][4]["exhibition_st"] = 0.21
        snap["racers"][5]["exhibition_st"] = 0.21
        report = build(snap, ranked)
        self.assertEqual(report["status"], "NO_SUPPORTED_OUTSIDE_HEAD")
        self.assertNotIn("shadow_alternative_bets", report)


if __name__ == "__main__":
    unittest.main()
