"""Tests for independent fast official payout updates; no live network."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.refresh_official_results import merge_pay, run, update

DAY="2026-10-25"
NOW=datetime(2026,10,25,16,35,tzinfo=ZoneInfo("Asia/Tokyo"))
BETS=[
 {"combination":"1-2-3","virtual_yen":15000},
 {"combination":"1-3-2","virtual_yen":12000},
 {"combination":"2-1-3","virtual_yen":12000},
 {"combination":"4-5-1","virtual_yen":11000},
]

def fixture():
    snap={"venue":"児島","race":1,"cutoff_iso_jst":DAY+"T10:00:00+09:00",
          "frozen_at_utc":"2026-10-25T00:30:00+00:00",
          "sha256":"a"*64,"model_version":"tactical-outside-start-wake-v0.9-untrained",
          "model_role":"main","phase":"baseline",
          "bets":copy.deepcopy(BETS)}
    return ({
      "event_date":DAY,
      "race_records":{"16-1":{"venue":"児島","venue_code":"16",
        "race":1,"versions":[snap],"payouts":[]}}},
      {"event_date":DAY,"mode":"auto-live",
       "updated_at_utc":"2026-10-25T05:00:00+00:00",
       "forecast_races":[copy.deepcopy(snap)],
       "official_results":{},"settlement_alerts":{}})

def pay(finish="4-5-1",yen=1320):
    return {"date":DAY,"results":{"16-1":{"finish":finish,"payout_per_100":yen}},
      "reviews":{},"cancellations":{},
      "source_url":"https://www.boatrace.jp/owpc/pc/race/pay?hd=20261025",
      "retrieved_at_utc":"2026-10-25T07:35:00+00:00"}

class FastOfficialTests(unittest.TestCase):
    def test_add_only_verified_and_preserve_frozen_sha(self):
        ledger,view=fixture()
        past=copy.deepcopy(ledger)
        a,b,c,changed,report=update(ledger,view,{},pay(),NOW)
        self.assertTrue(changed)
        self.assertEqual(report["newly_verified"],1)
        self.assertEqual(report["after_verified"],1)
        rec=a["race_records"]["16-1"]
        self.assertEqual(rec["versions"],past["race_records"]["16-1"]["versions"])
        self.assertEqual(rec["official_pay"]["source"],"boatrace_official_pay")
        self.assertEqual(b["official_results"][DAY+"|児島|1"]["finish"],"4-5-1")
        self.assertEqual(b["official_results"][DAY+"|児島|1"]["virtual_payout"],145200)
        self.assertEqual(view["official_results"],{})
        self.assertEqual(b["updated_at_utc"],"2026-10-25T07:35:00+00:00")
        self.assertEqual(c["status"],"verified_by_server_fetch")

    def test_repeat_does_not_double_count(self):
        ledger,view=fixture()
        a,b,c,changed,_=update(ledger,view,{},pay(),NOW)
        again_a,again_b,again_c,again_changed,report=update(a,b,c,pay(),NOW)
        self.assertFalse(again_changed)
        self.assertEqual(report["newly_verified"],0)
        self.assertEqual(len(again_b["official_results"]),1)
        self.assertEqual(again_a["race_records"]["16-1"]["versions"],
                         a["race_records"]["16-1"]["versions"])

    def test_check_heartbeat_publishes_without_rewriting_frozen_files(self):
        ledger,view=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            day_path=directory/(DAY+".json")
            live_path=directory/"latest.json"
            day_path.write_text(json.dumps(ledger),encoding="utf-8")
            live_path.write_text(json.dumps(view),encoding="utf-8")
            run(directory,NOW,lambda _:pay())
            before=(day_path.read_bytes(),live_path.read_bytes())
            checked=pay()
            checked["retrieved_at_utc"]="2026-10-25T07:40:00+00:00"
            # The official page can contain races without a frozen prediction.
            checked["results"]["16-2"]={"finish":"1-2-3","payout_per_100":500}
            report=run(directory,NOW+timedelta(minutes=5),lambda _:checked)
            self.assertFalse(report["changed"])
            self.assertEqual(report["newly_verified"],0)
            self.assertEqual((day_path.read_bytes(),live_path.read_bytes()),before)
            evidence=json.loads((directory/"official-pay"/(DAY+".json")).read_text())
            self.assertEqual(evidence["retrieved_at_utc"],checked["retrieved_at_utc"])
            self.assertEqual(len(evidence["results"]),2)
            self.assertEqual(evidence["status"],"verified_by_server_fetch")

    def test_conflicting_official_values_are_quarantined(self):
        ledger,view=fixture()
        old,old_view,old_pay,_,_=update(ledger,view,{},pay(),NOW)
        newer=pay("1-3-2",3450)
        a,b,c,changed,_=update(old,old_view,old_pay,newer,NOW)
        self.assertTrue(changed)
        self.assertNotIn("16-1",c["results"])
        self.assertIn("16-1",c["conflicts"])
        self.assertEqual(b["official_results"],{})
        self.assertIn(DAY+"|児島|1",b["settlement_alerts"])

    def test_early_or_mismatched_date_fails_closed(self):
        ledger,view=fixture()
        early=datetime(2026,10,25,9,55,tzinfo=ZoneInfo("Asia/Tokyo"))
        a,b,_,changed,_=update(ledger,view,{},pay(),early)
        self.assertFalse(changed)
        self.assertFalse(b["official_results"])
        fake=pay();fake["date"]="2026-10-24"
        with self.assertRaisesRegex(ValueError,"date mismatch|Date mismatch"):
            update(ledger,view,{},fake,NOW)
        fake_view=copy.deepcopy(view);fake_view["event_date"]="2026-10-24"
        with self.assertRaisesRegex(ValueError,"same-day"):
            update(ledger,fake_view,{},pay(),NOW)

    def test_preserve_verified_when_today_page_sparse(self):
        ledger,view=fixture()
        old=pay()
        new=pay();new["results"]={}
        merged=merge_pay(old,new)
        self.assertEqual(merged["results"],old["results"])
        self.assertNotIn("16-1",merged["conflicts"])

    def test_outcome_never_leaks_to_predictions(self):
        ledger,view=fixture()
        ledger["race_records"]["16-1"]["versions"][0]["legacy_control"]={
            "bets":copy.deepcopy(BETS),"sha256":"b"*64,
            "model_role":"shadow_validation",
            "model_version":"tactical-outside-start-gap-v0.7-untrained",
        }
        initial=copy.deepcopy(ledger["race_records"]["16-1"]["versions"])
        first,_,_,_,_=update(ledger,view,{},pay(),NOW)
        self.assertEqual(first["race_records"]["16-1"]["versions"],initial)

if __name__=="__main__":
    unittest.main()

