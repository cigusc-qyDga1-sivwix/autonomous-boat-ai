"""Actual entry is a physical relationship, independent of boat-number labels."""
from copy import deepcopy
from datetime import datetime
from itertools import permutations
from zoneinfo import ZoneInfo
import pytest
from scripts.interaction_scenarios import evaluate, ENTRY_VERSION
from scripts.autonomous_daily import prediction, build, INTERACTION_ENTRY_MODEL

CAPTURE='2026-11-04T15:10:00+00:00'
CUTOFF='2026-11-05T01:00:00+00:00'

def rows():
    return [{'lane':i,'course':i,'strength':10+i,'start_mean':.16,
             'exhibition_time':6.8} for i in range(1,7)]

def run(rs):
    return evaluate(rs,captured_at_utc=CAPTURE,cutoff_at_utc=CUTOFF,entry_aware=True)

def test_attack_defense_follow_use_real_courses():
    rs=rows()
    # Boat 4 is now course 2; its strength cannot nominate an outer attack.
    rs[1]['course'],rs[3]['course']=4,2
    rs[3]['strength']=90
    rs[4]['strength']=80
    result=run(rs)
    assert result['version']==ENTRY_VERSION
    for path in result['scenario_assumptions']:
        assert path['attack_lane']==5
        assert path['attack_course']==5
        assert path['defender_lane']==2  # boat 2 occupies course 4
        assert path['follower_lane']==6
        assert path['follower_course']==6


def test_outermost_attacker_has_no_outer_follower():
    result=run(rows())
    for path in result['scenario_assumptions']:
        assert path['attack_course']==6
        assert path['defender_lane']==5
        assert path['follower_lane'] is None
        assert path['follower_course'] is None


def test_course_one_metrics_follow_occupant_not_number_one():
    rs=rows();rs[0]['course'],rs[5]['course']=6,1
    result=run(rs)
    assert result['inside_lane']==6
    mass=sum(t['relative_score'] for t in result['top_combinations']
             if '6' not in t['combination'].split('-'))
    assert result['course1_outside_top3_relative_mass']==pytest.approx(mass,abs=1e-6)


def test_renaming_boats_cannot_change_physical_scenario_scores():
    original=run(rows())
    remap={1:6,2:4,3:2,4:1,5:3,6:5}
    renamed=rows()
    for r in renamed:r['lane']=remap[r['lane']]
    changed=run(renamed)
    weights={t['combination']:t['relative_score'] for t in changed['top_combinations']}
    for ticket in original['top_combinations']:
        renamed_combo='-'.join(str(remap[int(x)]) for x in ticket['combination'].split('-'))
        assert weights[renamed_combo]==pytest.approx(ticket['relative_score'],abs=1e-8)
    assert changed['course1_outside_top3_relative_mass']==original['course1_outside_top3_relative_mass']


def test_missing_partial_or_duplicate_entry_fails_closed():
    for mutate in (lambda rs:rs[0].pop('course'),lambda rs:rs[0].update(course=2),
                   lambda rs:rs[0].update(course=True)):
        rs=rows();mutate(rs)
        with pytest.raises(ValueError):run(rs)


def race():
    return {'closed_at':'2026-11-05 10:00:00','racers':{
        str(i):{'name':f'R{i}','national_win_rate':5+i*.1,
                'motor_top_2_percent':30+i,'average_start_timing':.15+i*.001}
        for i in range(1,7)}}


def test_next_day_primary_and_append_only_upgrade():
    now=datetime(2026,11,5,1,0,tzinfo=ZoneInfo('Asia/Tokyo'))
    predicted=prediction(race(),'徳山',1,'baseline',now,'fixture')
    assert predicted['model_version']==INTERACTION_ENTRY_MODEL
    assert predicted['interaction_primary']['entry_aware'] is True
    assert len(predicted['bets'])<=8
    assert sum(b['virtual_yen'] for b in predicted['bets'])==50000
    assert 'v2.1' in predicted['point_reason']
    old=deepcopy(predicted);old['model_version']='four-factor-v2.0-justified-points-primary-untrained'
    old['sha256']='archived-version-kept-verbatim'
    ledger={'event_date':'2026-11-05','race_records':{'18-1':{
        'venue':'徳山','venue_code':'18','race':1,'cutoff_jst':'10:00','versions':[old],'payouts':[]}}}
    payload={'programs':{'stadiums':{'18':{'races':{'1':race()}}}}}
    refreshed,_,_=build(ledger,payload,now,'fixture')
    versions=refreshed['race_records']['18-1']['versions']
    assert versions[0]==old
    assert versions[-1]['model_version']==INTERACTION_ENTRY_MODEL
