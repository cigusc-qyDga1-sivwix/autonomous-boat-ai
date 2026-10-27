import copy,json
from datetime import datetime,timedelta
from unittest.mock import patch
from scripts import autonomous_daily as A
from scripts.forecast_audit import analyze
from scripts.freeze_statistical_shadow import freeze
from boat_ai.statistical import allocate,digest,distributions
from test_four_factor_main import race
from test_statistical import zero_model

NOW=datetime.fromisoformat('2026-10-28T08:00:00+09:00')
def source(preview=False):return {'programs':{'stadiums':{'23':{'races':{'1':race('2026-10-28',preview)}}}}}

def test_day_activation_formal_gate_append_only_and_past_unchanged():
    with patch.object(A,'POINT_FREE_DATE',NOW.date()+timedelta(days=1)):
        ledger,_,_=A.build(None,source(),NOW,'fixture')
    before=copy.deepcopy(ledger['race_records']['23-1']['versions'])
    ledger,ui,stats=A.build(ledger,source(),NOW+timedelta(minutes=1),'fixture')
    vs=ledger['race_records']['23-1']['versions']
    assert vs[:-1]==before and vs[-1]['model_version']==A.POINT_FREE_MODEL
    assert ui['forecast_races'][0]['ticket_status']=='provisional'
    baseline=copy.deepcopy(vs)
    ledger,ui,_=A.build(ledger,source(True),NOW+timedelta(minutes=2),'fixture')
    vs=ledger['race_records']['23-1']['versions'];assert vs[:-1]==baseline
    v=vs[-1];assert v['phase']=='exhibition' and v['model_version']==A.POINT_FREE_MODEL
    assert ui['forecast_races'][0]['ticket_status']=='formal'
    assert len(v['bets'])>12 and sum(b['virtual_yen'] for b in v['bets'])==50000
    assert v['point_free_control']['frozen_at_utc']==v['frozen_at_utc']
    assert v['sha256']==A.stable_hash({k:x for k,x in v.items() if k!='sha256'})
    copied=copy.deepcopy(vs)
    later,_,_=A.build(ledger,source(True),NOW+timedelta(minutes=3),'fixture')
    assert later['race_records']['23-1']['versions']==copied
    late,_,_=A.build(ledger,source(True),NOW+timedelta(hours=3),'fixture')
    assert late['race_records']['23-1']['versions']==copied
    old=A.prediction(race('2026-10-27'), '唐津',1,'exhibition',NOW-timedelta(days=1),'fixture')
    assert old['model_version']!=A.POINT_FREE_MODEL
    assert 4<=len(old['bets'])<=12
    tomorrow=A.prediction(race('2026-10-29'), '唐津',1,'exhibition',NOW+timedelta(days=1),'fixture')
    assert tomorrow['model_version']!=A.POINT_FREE_MODEL


def test_settlement_and_same_time_predecessor_comparison():
    _,ui,_=A.build(None,source(True),NOW,'fixture');r=ui['forecast_races'][0]
    win=r['bets'][-1]['combination'];key=f"2026-10-28|唐津|1"
    ui['official_results']={key:{'verified':True,'source':'boatrace_official_pay','snapshot_sha256':r['sha256'],
        'finish':win,'payout_per_100':1230,'virtual_stake':50000}}
    out=analyze(ui);assert out['metrics']['verified_races']==1 and out['metrics']['hits']==1
    assert out['point_free_comparison']['trial']['verified_races']==1
    assert out['point_free_comparison']['previous']['verified_races']==1
    # Broad tickets under an old model identity must still be rejected.
    ui['forecast_races'][0]['model_version']=A.VENUE_TACTICS_MODEL
    assert analyze(ui)['metrics']['verified_races']==0


def test_statistical_shadow_matches_broad_count_and_currency_unit():
    ledger,ui,_=A.build(None,source(True),NOW,'fixture');v=ledger['race_records']['23-1']['versions'][-1]
    ui['forecast_races'][0]['_immutable_source']=v
    model=zero_model('2026-10-27T22:00:00+09:00');model['trained_through']='2026-10-27'
    model['model_sha256']=digest({k:x for k,x in model.items() if k!='model_sha256'})
    shadow,n=freeze(ui,model,None,NOW+timedelta(minutes=1));assert n==1
    b=shadow['race_records']['唐津-1'][-1]
    assert len(b['bets'])==len(v['bets']) and b['stake_unit_yen']==100
    assert b['source_sha256']==v['sha256']
    ranked=distributions(v,model)
    for count in [1,3,19,120]:
        bets=allocate(ranked,count,point_free=True)
        assert len(bets)==count and sum(x['virtual_yen'] for x in bets)==50000
        assert all(x['virtual_yen']>=100 and x['virtual_yen']%100==0 for x in bets)
