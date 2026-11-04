"""Forward-only canonical linkage: real prediction function, no result fitting."""
from copy import deepcopy
from datetime import datetime
from unittest.mock import patch
import pytest
from scripts import autonomous_daily as A
from tests.test_four_factor_main import race

NOW=datetime.fromisoformat('2026-11-05T09:40:00+09:00')

def source():
    r=race('2026-11-05')
    r['_racer_context']={str(i):{'values':{'national_top3':50,'local_win':5,
        'motor_top3':45,'frame_win':6,'frame_st':.16}} for i in range(1,7)}
    return r

def predict(r=None):return A.prediction(source() if r is None else r,'徳山',1,'exhibition',NOW,'fixture')

def test_canonical_120_drives_all_marginals_and_tickets():
    r=predict();m=r['interaction_primary'];ranked=m['ranked_outcomes']
    assert r['model_version']==A.LINKED_MAIN_MODEL
    assert m['canonical_source']=='linked-four-factor-venue-st-wake-120'
    assert m['fixed_five_path_mixture_used'] is False
    assert len(ranked)==120 and len({x['combination'] for x in ranked})==120
    assert sum(x['relative_score'] for x in ranked)==pytest.approx(1)
    for lane in range(1,7):
        for i,role in enumerate(('first','second','third')):
            actual=sum(x['relative_score'] for x in ranked if x['combination'].split('-')[i]==str(lane))
            assert m['main_role_shares'][str(lane)][role]==pytest.approx(actual,abs=1e-8)
    assert r['role_coverage']==m['main_role_shares']
    assert set(m['point_policy']['ticket_reasons'])=={b['combination'] for b in r['bets']}
    assert 4<=len(r['bets'])<=12
    assert sum(b['virtual_yen'] for b in r['bets'])==50000
    assert r['wake_v09']['applied_to_chaser_scores']

@pytest.mark.parametrize('field,value',[('national_top3',95),('local_win',9),('motor_top3',95),('frame_win',9),('frame_st',.01)])
def test_previously_disconnected_context_reaches_final_ranking(field,value):
    base=predict();r=source();r['_racer_context']['4']['values'][field]=value
    changed=predict(r)
    assert changed['interaction_primary']['main_role_shares']!=base['interaction_primary']['main_role_shares']
    assert changed['interaction_primary']['ranked_outcomes']!=base['interaction_primary']['ranked_outcomes']
    # Rounding/ticket cutoffs need not change every issued bet on every small intervention.


def test_six_actual_head_conditions_including_course_two_and_no_phantom_follower():
    r=source();r['preview']['racers']['1']['course_number']=6;r['preview']['racers']['6']['course_number']=1
    p=predict(r);paths=p['interaction_primary']['scenario_assumptions']
    assert len(paths)==6
    assert sum(x['assumed_share'] for x in paths)==pytest.approx(1)
    assert next(x for x in paths if x['attack_course']==2)['attack_lane']==2
    assert next(x for x in paths if x['attack_course']==6)['follower_lane'] is None
    assert all(x['inside_lane']==6 for x in paths)
    assert sorted(x['assumed_share'] for x in paths)!=[.1,.15,.17,.28,.3]


def test_missing_full_ranking_fails_without_simplified_fallback():
    original=A.promoted_v09
    def broken(*args,**kwargs):
        r=original(*args,**kwargs);r.pop('ranked_outcomes',None);r.pop('ranked_source',None);return r
    with patch.object(A,'promoted_v09',broken),pytest.raises(ValueError,match='source missing'):
        predict()


def test_result_blind_and_pre_activation_version_retained():
    r=source();r['result']={'finish':'6-5-4','payout':999999}
    assert predict(r)['bets']==predict()['bets']
    old=A.prediction(source(),'徳山',1,'exhibition',datetime.fromisoformat('2026-11-05T07:00:00+09:00'),'fixture')
    assert old['model_version']==A.INTERACTION_ENTRY_MODEL
    assert 'canonical_source' not in old['interaction_primary']


def test_append_only_upgrade_and_exclusion_keeps_edogawa_archive():
    raw=source();raw.pop('_racer_context')
    src={'programs':{'stadiums':{code:{'races':{'1':deepcopy(raw)}} for code in ('18','3')}}}
    before=datetime.fromisoformat('2026-11-05T07:00:00+09:00')
    ledger,_,_=A.build(None,src,before,'fixture');original=deepcopy(ledger)
    upgraded,view,_=A.build(ledger,src,NOW,'fixture')
    for key,record in original['race_records'].items():
        assert upgraded['race_records'][key]['versions'][:len(record['versions'])]==record['versions']
    assert upgraded['race_records']['3-1']==original['race_records']['3-1']
    assert all(r['venue']!='江戸川' for r in view['forecast_races'])
    assert view['listed_races']==1 and view['venues_with_races']==1
    assert view['forecast_races'][0]['model_version']==A.LINKED_MAIN_MODEL
    after=deepcopy(upgraded)
    closed,_,_=A.build(upgraded,src,datetime.fromisoformat('2026-11-05T10:01:00+09:00'),'fixture')
    assert all(closed['race_records'][k]['versions']==v['versions'] for k,v in after['race_records'].items())
