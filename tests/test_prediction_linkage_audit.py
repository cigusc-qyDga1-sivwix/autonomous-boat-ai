"""The read-only auditor must detect corruption without changing predictions."""
from copy import deepcopy
from datetime import datetime
from scripts.autonomous_daily import prediction
from scripts.audit_prediction_linkage import audit_saved
from scripts.entry_exhibition_gate import summarize_gate


def fixture():
    race={'closed_at':'2026-11-05 10:00:00','racers':{
        str(i):{'name':f'TEST-{i}','number':4000+i,'national_win_rate':5+i*.2,
                'average_start_timing':.17,'motor_top_2_percent':30} for i in range(1,7)}}
    r=prediction(race,'徳山',1,'baseline',datetime.fromisoformat('2026-11-05T09:40:00+09:00'),'fixture')
    displayed={**deepcopy(r),'entry_exhibition_gate':summarize_gate(r,'2026-11-05'),'ticket_status':'provisional'}
    return {'event_date':'2026-11-05','forecast_races':[displayed]}, {'race_records':{'18-1':{'versions':[r]}}}


def test_consistent_saved_prediction_and_input_immutability():
    v,l=fixture();before=deepcopy((v,l))
    assert audit_saved(v,l)['errors']==[]
    assert (v,l)==before


def test_view_ticket_corruption_detected_even_with_original_hash():
    v,l=fixture();v['forecast_races'][0]['bets'][0]['virtual_yen']+=1000
    errors={x['check'] for x in audit_saved(v,l)['errors']}
    assert {'view_snapshot_content_differs','budget'}<=errors


def test_ledger_rewrite_and_false_formal_claim_detected():
    v,l=fixture();l['race_records']['18-1']['versions'][0]['classification']='BUY'
    v['forecast_races'][0]['ticket_status']='formal'
    errors={x['check'] for x in audit_saved(v,l)['errors']}
    assert {'snapshot_hash','view_snapshot_content_differs','formal_without_exhibition'}<=errors


def test_stale_marginal_count_and_postcutoff_are_detected():
    v,l=fixture();r=v['forecast_races'][0]
    r['head_course_shares'][0]['relative_share']=.99
    r['interaction_primary']['ticket_role_counts']['1']['first']=99
    r['frozen_at_utc']='2026-11-05T10:01:00+09:00'
    errors={x['check'] for x in audit_saved(v,l)['errors']}
    assert {'head_marginal','ticket_role_counts','cutoff'}<=errors
