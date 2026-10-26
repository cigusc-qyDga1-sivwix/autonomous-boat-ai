import copy
from datetime import datetime
from scripts import autonomous_daily as A

NOW=datetime.fromisoformat('2026-10-27T08:30:00+09:00')
def race(day='2026-10-27',preview=True):
    r={'closed_at':day+' 10:00:00','racers':{str(i):{'name':f'選手{i}','number':4000+i,'national_win_rate':5+i*.2,'average_start_timing':.17,'motor_top_2_percent':30} for i in range(1,7)}}
    if preview:r['preview']={'wind_speed':3,'wave_height':1,'racers':{str(i):{'course_number':i,'exhibition_time':6.8-i*.01,'start_timing':.15,'tilt_adjustment':0} for i in range(1,7)}}
    return r

def test_new_main_freezes_four_factors_and_same_time_v09_control():
    r=race();src={'programs':{'stadiums':{'18':{'races':{'1':r}}}}}
    ledger,ui,_=A.build(None,src,NOW,'fixture')
    final=ledger['race_records']['18-1']['versions'][-1]
    assert final['model_version']==A.FOUR_FACTOR_MODEL
    assert final['four_factor']['weights']=={'athlete':.6,'motor':.25,'exhibition':.1,'weather':.05}
    assert final['legacy_control']['model_version']==A.MAIN_WAKE_MODEL
    assert final['legacy_control']['frozen_at_utc']==final['frozen_at_utc']
    assert sum(b['virtual_yen'] for b in final['bets'])==50000
    assert ui['forecast_races'][0]['four_factor']==final['four_factor']
    before=copy.deepcopy(ledger['race_records']['18-1']['versions'])
    repeated,_,_=A.build(ledger,src,datetime.fromisoformat('2026-10-27T10:30:00+09:00'),'fixture')
    assert repeated['race_records']['18-1']['versions']==before

def test_past_v09_identity_and_future_cutoff_guard():
    old=A.prediction(race('2026-10-26'),'徳山',1,'exhibition',datetime.fromisoformat('2026-10-26T08:30:00+09:00'),'fixture')
    assert old['model_version']==A.MAIN_WAKE_MODEL
    assert 'four_factor' not in old
    src={'programs':{'stadiums':{'18':{'races':{'1':race()}}}}}
    ledger,ui,_=A.build(None,src,datetime.fromisoformat('2026-10-27T10:01:00+09:00'),'fixture')
    assert not ledger['race_records']['18-1']['versions']
    assert not ui['forecast_races']

def test_registered_context_reaches_factor_score_without_outcomes():
    stamp='2026-10-27T08:20:00+09:00'
    def meta(name):return {'state':'available','sha256':'a'*64,'fetched_at_utc':stamp,'url':f'https://boatracecsv.github.io/data/programs/{name}/2026/10/27.csv'}
    contexts={'202610271801':{i:{'racer_id':4000+i,'lane':i,'values':{'national_top3':50,'frame_win':6,'frame_st':.13,'local_win':5,'motor_top3':45},'sources':{'race_cards':meta('race_cards'),'waku10':meta('waku10')}} for i in range(1,7)}}
    r=race();r['result']={'finish':'6-5-4'}
    src={'programs':{'stadiums':{'18':{'races':{'1':r}}}}}
    ledger,_,_=A.build(None,src,NOW,'fixture',racer_context_rows=contexts)
    final=ledger['race_records']['18-1']['versions'][-1]
    assert all(x['available']['frame'] for x in final['four_factor']['rows'])
    assert final['racers'][0]['racer_context']['racer_id']==4001
    assert final['racers'][0]['racer_id']==4001
    assert 'result' not in final['racers'][0]['racer_context']


def test_newly_available_context_upgrades_provisional_once_without_rewriting():
    r=race(preview=False);src={'programs':{'stadiums':{'18':{'races':{'1':r}}}}}
    ledger,_,_=A.build(None,src,NOW,'fixture')
    original=copy.deepcopy(ledger['race_records']['18-1']['versions'][0])
    stamp='2026-10-27T08:50:00+09:00'
    def meta(name):return {'state':'available','sha256':'b'*64,'fetched_at_utc':stamp,'url':f'https://boatracecsv.github.io/data/programs/{name}/2026/10/27.csv'}
    contexts={'202610271801':{i:{'racer_id':4000+i,'lane':i,'values':{'national_top3':50,'frame_win':6,'frame_st':.13},'sources':{'race_cards':meta('race_cards'),'waku10':meta('waku10')}} for i in range(1,7)}}
    now=datetime.fromisoformat('2026-10-27T09:00:00+09:00')
    upgraded,_,_=A.build(ledger,src,now,'fixture',racer_context_rows=contexts)
    versions=upgraded['race_records']['18-1']['versions']
    assert len(versions)==2 and versions[0]==original
    assert versions[-1]['racer_context_upgrade']['new_quality']==18
    again,_,_=A.build(upgraded,src,now,'fixture',racer_context_rows=contexts)
    assert len(again['race_records']['18-1']['versions'])==2
