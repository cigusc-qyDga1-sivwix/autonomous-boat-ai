import copy
import unittest
from datetime import date, datetime, timezone
from scripts.racer_context import validated, in_meeting_start_consistency, collect

class ContextTests(unittest.TestCase):
    def setUp(self):
        self.day=date(2026,10,27)
        self.now=datetime.fromisoformat('2026-10-26T15:20:00+00:00')
        def source(name):
            return {'state':'available','fetched_at_utc':'2026-10-26T15:15:00+00:00','sha256':'a'*64,
                    'url':f'https://boatracecsv.github.io/data/programs/{name}/2026/10/27.csv'}
        self.row={'lane':2,'racer_id':3716,'values':{'frame_win':6,'frame_st':.13,'national_top3':59},
                  'sources':{'race_cards':source('race_cards'),'waku10':source('waku10')}}
    def test_jst_midnight_identity_and_provenance(self):
        x=validated(self.row,{'number':3716},2,self.now,self.day)
        self.assertEqual(x['values']['frame_win'],6)
        self.assertEqual(x['sources']['race_cards']['sha256'],'a'*64)
    def test_wrong_racer_and_lane_rejected(self):
        self.assertIsNone(validated(self.row,{'number':9999},2,self.now,self.day))
        self.assertIsNone(validated(self.row,{'number':3716},1,self.now,self.day))
    def test_late_stale_undated_source_rejected(self):
        for stamp in ['2026-10-26T15:21:00+00:00','2026-10-26T13:00:00+00:00','2026-10-26T15:15:00']:
            x=copy.deepcopy(self.row);x['sources']['race_cards']['fetched_at_utc']=stamp
            self.assertIsNone(validated(x,{'number':3716},2,self.now,self.day))
    def test_wrong_day_url_or_missing_hash_rejected(self):
        for k,v in [('url','https://boatracecsv.github.io/data/programs/race_cards/2026/10/26.csv'),('sha256',None)]:
            x=copy.deepcopy(self.row);x['sources']['race_cards'][k]=v
            self.assertIsNone(validated(x,{'number':3716},2,self.now,self.day))
    def test_bad_frame_source_does_not_destroy_verified_basic_context(self):
        x=copy.deepcopy(self.row);x['sources']['waku10']['state']='unavailable'
        y=validated(x,{'number':3716},2,self.now,self.day)
        self.assertEqual(y['values']['national_top3'],59)
        self.assertIsNone(y['values']['frame_win'])
        self.assertEqual(self.row['values']['frame_win'],6)


class StartVarianceTests(unittest.TestCase):
    def sample(self, starts):
        card = {}
        for ix, value in enumerate(starts):
            key = f"艇2_節D{ix//2+1}走{ix%2+1}_"
            card[key+"R番号"] = str(ix%12+1)
            card[key+"ST"] = str(value) if value is not None else ""
        return card

    def test_in_meeting_std_and_trend_are_legal_start_only(self):
        card = self.sample([.20, .20, .20, .10, .10, .10, -.05, None])
        stats = in_meeting_start_consistency(card, 2)
        self.assertEqual(stats["meeting_st_legal_count"], 6)
        self.assertEqual(stats["meeting_st_mean"], .15)
        self.assertEqual(stats["meeting_st_sd"], .05)
        self.assertEqual(stats["meeting_st_recent_mean"], .10)
        self.assertEqual(stats["meeting_st_recent_minus_older"], -.10)
        self.assertEqual(stats["meeting_st_f_count"], 1)

    def test_sparse_outlier_or_missing_data_cannot_fake_stability(self):
        card = self.sample([.10, None, -.08, .92])
        stats = in_meeting_start_consistency(card, 2)
        self.assertEqual(stats["meeting_st_legal_count"], 1)
        self.assertIsNone(stats["meeting_st_sd"])
        self.assertIsNone(stats["meeting_st_mean"])
        self.assertEqual(stats["meeting_st_f_count"], 1)
        self.assertIsNone(stats["meeting_st_recent_minus_older"])

    def test_no_race_identity_or_unpopulated_slot_is_counted(self):
        card = self.sample([.10, .20, .30])
        card["艇2_節D1走1_R番号"] = ""  # ST alone is not a confirmed run
        self.assertEqual(in_meeting_start_consistency(card, 2)["meeting_st_legal_count"], 2)
        self.assertIsNone(in_meeting_start_consistency(card, 2)["meeting_st_sd"])

    def test_recent_st_is_collected_but_requires_verified_current_source(self):
        from unittest.mock import patch
        from datetime import date
        day = date(2026, 11, 3)
        race_code = "202611031203"
        card = {"レースコード": race_code, "艇2_登録番号":"3716"}
        card.update(self.sample([.20, .20, .20, .10, .10, .10]))
        metadata = lambda source: {
            "url": f"https://boatracecsv.github.io/data/programs/{source}/2026/11/03.csv",
            "state": "available", "sha256": "b"*64,
            "fetched_at_utc": "2026-11-03T00:05:00+00:00",
        }
        def fake_fetch(source, selected_day):
            self.assertEqual(selected_day, day)
            if source == "race_cards":
                return [card], metadata(source)
            return [{"レースコード": race_code}], metadata(source)
        with patch("scripts.racer_context.fetch_csv", side_effect=fake_fetch):
            ctx = collect(day)[race_code][2]
        self.assertEqual(ctx["values"]["meeting_st_sd"], .05)
        good = validated(ctx, {"number":3716}, 2,
                         datetime.fromisoformat("2026-11-03T00:10:00+00:00"), day)
        self.assertEqual(good["values"]["meeting_st_recent_minus_older"], -.1)
        self.assertNotIn("bets", good)
        bad = copy.deepcopy(ctx)
        bad["sources"]["race_cards"]["fetched_at_utc"] = "2026-11-03T00:13:00+00:00"
        self.assertIsNone(validated(bad, {"number":3716}, 2,
                         datetime.fromisoformat("2026-11-03T00:10:00+00:00"), day))
