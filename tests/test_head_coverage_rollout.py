import copy
from datetime import datetime,timedelta
from unittest.mock import patch
from scripts import autonomous_daily as A
from test_four_factor_main import race

NOW=datetime.fromisoformat('2026-10-27T08:30:00+09:00')
ROLLOUT={'event_date':'2026-10-27','created_at_utc':NOW.isoformat(),'targets':{'18-1':{}}}
def source(r):return {'programs':{'stadiums':{'18':{'races':{'1':r}}}}}

def test_pending_only_append_and_later_exhibition_retain_policy():
    with patch.object(A,'HEAD_COVERAGE_ROLLOUT',{**ROLLOUT,'targets':{}}):
        old,_,_=A.build(None,source(race(preview=False)),NOW,'test')
    original=copy.deepcopy(old['race_records']['18-1']['versions'])
    with patch.object(A,'HEAD_COVERAGE_ROLLOUT',ROLLOUT):
        ledger,ui,_=A.build(copy.deepcopy(old),source(race(preview=False)),NOW+timedelta(minutes=1),'test')
        versions=ledger['race_records']['18-1']['versions']
        assert versions[:-1]==original
        assert versions[-1]['model_version']==A.HEAD_COVERAGE_MODEL
        assert versions[-1]['phase']=='baseline'
        assert ui['forecast_races'][0]['ticket_status']=='provisional'
        assert versions[-1]['head_coverage_control']['generated_pre_cutoff']
        base=copy.deepcopy(versions)
        again,_,_=A.build(ledger,source(race(preview=False)),NOW+timedelta(minutes=2),'test')
        assert again['race_records']['18-1']['versions']==base
        final,web,_=A.build(again,source(race()),NOW+timedelta(minutes=3),'test')
        assert final['race_records']['18-1']['versions'][:-1]==base
        v=final['race_records']['18-1']['versions'][-1]
        assert v['phase']=='exhibition' and v['model_version']==A.HEAD_COVERAGE_MODEL
        assert v['head_coverage_control']['frozen_at_utc']==v['frozen_at_utc']
        assert web['forecast_races'][0]['ticket_status']=='formal'
        assert v['sha256']==A.stable_hash({k:v for k,v in v.items() if k!='sha256'})

def test_already_formal_cutoff_other_day_and_noncohort_untouched():
    with patch.object(A,'HEAD_COVERAGE_ROLLOUT',{**ROLLOUT,'targets':{}}):
        old,_,_=A.build(None,source(race()),NOW,'test')
    original=copy.deepcopy(old['race_records']['18-1']['versions'])
    with patch.object(A,'HEAD_COVERAGE_ROLLOUT',ROLLOUT):
        same,_,_=A.build(old,source(race()),NOW+timedelta(minutes=1),'test')
        assert same['race_records']['18-1']['versions']==original
        cutoff=A.cutoff_of(race())
        pending={'versions':[{'phase':'baseline','model_version':A.FOUR_FACTOR_MODEL}]}
        assert not A.head_coverage_eligible(pending,'18-1',NOW-timedelta(seconds=1),cutoff)
        assert not A.head_coverage_eligible(pending,'18-2',NOW,cutoff)
        assert not A.head_coverage_eligible(pending,'18-1',cutoff-timedelta(seconds=180),cutoff)
        assert not A.head_coverage_eligible(pending,'18-1',NOW,cutoff+timedelta(days=1))
        late,_,_=A.build(same,source(race()),cutoff+timedelta(minutes=1),'test')
        assert late['race_records']['18-1']['versions']==original
