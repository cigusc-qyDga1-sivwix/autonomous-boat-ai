import copy
import unittest
from datetime import date, datetime, timezone
from scripts.racer_context import validated

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
