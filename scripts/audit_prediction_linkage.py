"""Read-only BOAT LAB linkage audit. Does not generate or replace live forecasts.

Run from repository root with `python -m scripts.audit_prediction_linkage
--view VIEW --ledger LEDGER`. --probes uses explicitly synthetic pre-cutoff
inputs; their outputs are diagnostics, never forecast performance or recommendations.
"""
from __future__ import annotations
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
from . import autonomous_daily as A
from .entry_exhibition_gate import summarize_gate


def audit_saved(view, ledger):
    errors, notes = [], []
    versions = {}
    n_versions = 0
    for record in ledger.get('race_records', {}).values():
        for row in record.get('versions', []):
            n_versions += 1
            sha = row.get('sha256')
            if sha != A.stable_hash({k: v for k, v in row.items() if k != 'sha256'}):
                errors.append({'check': 'snapshot_hash', 'venue': row.get('venue'), 'race': row.get('race')})
            versions[sha] = row
    rows = view.get('forecast_races', [])
    stats = Counter()
    for row in rows:
        ident = {'venue': row.get('venue'), 'race': row.get('race')}
        def fail(check): errors.append({**ident, 'check': check})
        original = versions.get(row.get('sha256'))
        if original is None:
            fail('view_snapshot_missing')
        elif any(row[k] != original[k] for k in row.keys() & original.keys()):
            fail('view_snapshot_content_differs')
        bets = row.get('bets', [])
        if sum(b.get('virtual_yen', 0) for b in bets) != 50000:
            fail('budget')
        valid = {f'{a}-{b}-{c}' for a in range(1,7) for b in range(1,7)
                 for c in range(1,7) if len({a,b,c}) == 3}
        if len({b.get('combination') for b in bets}) != len(bets) or any(b.get('combination') not in valid for b in bets):
            fail('ticket_identity')
        if row.get('point_count') != len(bets): fail('point_count')
        try:
            cutoff = datetime.fromisoformat(view['event_date']+'T'+row['cutoff_jst']+':00+09:00')
            frozen = datetime.fromisoformat(row['frozen_at_utc'])
            if (cutoff.tzinfo is None or frozen.tzinfo is None or (cutoff-frozen).total_seconds() < 120): fail('cutoff')
        except (KeyError, ValueError, TypeError): fail('cutoff')
        gate = summarize_gate(row, view['event_date'])
        if gate['final_eligible'] != row.get('entry_exhibition_gate', {}).get('final_eligible'): fail('eligibility_gate')
        if row.get('ticket_status') == 'formal' and not gate['final_eligible']: fail('formal_without_exhibition')
        stats['exhibition_verified'] += gate['final_eligible']
        stats['edogawa_forecasts'] += row.get('venue') == '江戸川'
        stats['racers_with_context'] += sum(bool(r.get('racer_context')) for r in row.get('racers', []))
        meta = row.get('interaction_primary')
        if not meta: continue
        stats['interaction_rows'] += 1
        roles = meta.get('main_role_shares', {})
        if meta.get('role_evaluation_source') != 'same_final_ranked_120_as_primary_bets': fail('role_source')
        for key in ('first', 'second', 'third'):
            if abs(sum(roles.get(str(i), {}).get(key, 0) for i in range(1,7))-1)>1e-6: fail('role_sum_'+key)
        for head in row.get('head_course_shares', []):
            if abs(head['relative_share']-roles[str(head['lane'])]['first'])>.00011: fail('head_marginal')
        for lane in range(1,7):
            actual = {role: sum(b['combination'].split('-')[pos] == str(lane) for b in bets)
                      for pos, role in enumerate(('first','second','third'))}
            if meta.get('ticket_role_counts', {}).get(str(lane)) != actual: fail('ticket_role_counts')
        for conditional in meta.get('conditional_places_by_head', []):
            h = str(conditional['head_lane'])
            if abs(conditional['relative_head_share']-roles[h]['first'])>1e-7: fail('conditional_head')
            for key in ('second_given_head', 'third_given_head'):
                if abs(sum(conditional[key].values())-1)>1e-6 or conditional[key][h] != 0: fail('conditional_'+key)
        if len(bets)>24 or len(bets)<4 or any(type(b.get('virtual_yen')) is not int or b['virtual_yen']<1000 or b['virtual_yen']%1000 for b in bets): fail('v21_ticket_bounds')
        if set(meta.get('point_policy', {}).get('ticket_reasons', {})) != {b['combination'] for b in bets}: fail('selection_reason')
        if row.get('role_coverage') != roles: stats['legacy_role_coverage_present'] += 1
        stats['tactics_applied'] += bool(meta.get('racer_course_tactics', {}).get('applied'))
    if stats['legacy_role_coverage_present']: notes.append('Top-level role_coverage is older-model metadata; primary consumers must use interaction_primary.main_role_shares.')
    if stats['edogawa_forecasts']: notes.append('Edogawa is excluded from the new interaction model, but NOT from forecast ingestion/output.')
    return {'event_date': view['event_date'], 'data_updated_at_utc': view.get('updated_at_utc'),
            'view_rows': len(rows), 'ledger_versions': n_versions, 'stats': dict(stats),
            'models': dict(Counter(r['model_version'] for r in rows)), 'errors': errors,
            'notes': notes, 'scope': 'stored-data consistency only; not proof of all feature linkage or predictive quality'}


def synthetic_probes():
    """Single-variable interventions in the actual primary prediction function."""
    now = datetime.fromisoformat('2026-11-05T09:40:00+09:00')
    race = {'closed_at':'2026-11-05 10:00:00', 'racers': {
        str(i): {'name': f'SYNTHETIC-{i}', 'number': 4000+i, 'national_win_rate': 5+i*.2,
                 'average_start_timing': .17, 'motor_top_2_percent': 30} for i in range(1,7)},
        'preview': {'wind_speed':3, 'wave_height':1, 'racers': {
            str(i): {'course_number':i,'exhibition_time':6.8-i*.01,'start_timing':.15,'tilt_adjustment':0} for i in range(1,7)}},
        '_racer_context': {str(i): {'values': {'national_top3':50,'local_win':5,'motor_top3':45,'frame_win':6,'frame_st':.16,'frame_start_order':3}} for i in range(1,7)},
        '_exhibition_original': {k:{str(i):v+i*.01 for i in range(1,7)} for k,v in [('lap_time',37),('turn_time',6),('straight_time',7)]}}
    def calculate(r, venue='徳山'): return A.prediction(r,venue,1,'exhibition',now,'synthetic-linkage-audit')
    def signature(r): return [(b['combination'],b['virtual_yen']) for b in r['bets']]
    base = calculate(race)
    cases = [('national_win_rate',('racers','4','national_win_rate'),9.5),
        ('motor_top2',('racers','4','motor_top_2_percent'),90),
        ('average_st',('racers','4','average_start_timing'),.03),
        ('exhibition_time',('preview','racers','4','exhibition_time'),6.1),
        ('exhibition_st',('preview','racers','4','start_timing'),.01),
        ('lap',('_exhibition_original','lap_time','4'),32),
        ('turn',('_exhibition_original','turn_time','4'),4.5),
        ('straight',('_exhibition_original','straight_time','4'),5.5),
        ('wind_speed',('preview','wind_speed'),10),('wave_height',('preview','wave_height'),15),
        ('wind_direction',('preview','wind_direction_number'),16)]
    cases += [(k,('_racer_context','4','values',k),v) for k,v in
              [('national_top3',95),('local_win',9),('motor_top3',95),('frame_win',9),('frame_st',.01)]]
    cases += [('result',('result',),{'finish':'6-5-4','payout':999999})]
    output=[]
    def compare(name, r):
        m=r['interaction_primary']
        output.append({'field':name,
            'main_role_changed':m['main_role_shares']!=base['interaction_primary']['main_role_shares'],
            'tickets_changed':signature(r)!=signature(base),
            'legacy_four_factor_changed':r['four_factor']!=base['four_factor'],
            'scenario_shares':[x['assumed_share'] for x in m['scenario_assumptions']]})
    for name,path,value in cases:
        changed=deepcopy(race); target=changed
        for key in path[:-1]: target=target[key]
        target[path[-1]]=value
        compare(name,calculate(changed))
    changed=deepcopy(race)
    changed['preview']['racers']['1']['course_number']=4
    changed['preview']['racers']['4']['course_number']=1
    compare('actual_entry',calculate(changed))
    compare('venue_toda',calculate(race,'戸田'))
    # Remove older bridge's wake/role information and replace its tickets,
    # retaining a valid point count. The final v2.1 path should reveal whether
    # those earlier calculations are an actual input or just saved diagnostics.
    original=A.promoted_v09
    def altered(*args,**kwargs):
        r=deepcopy(original(*args,**kwargs))
        r['wake_v09']={'synthetic_disconnected_probe':True}
        r['role_coverage']={};r['four_factor']={'synthetic_disconnected_probe':True}
        r['bets']=[{'combination':b['combination'],'virtual_yen':1000} for b in reversed(r['bets'])]
        return r
    try:
        A.promoted_v09=altered
        compare('legacy_wake_roles_and_tickets_replaced',calculate(race))
    finally: A.promoted_v09=original
    return {'synthetic':True,'performance_claim':False,'model':base['model_version'],'probes':output}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--view',type=Path,required=True); p.add_argument('--ledger',type=Path,required=True)
    p.add_argument('--probes',action='store_true'); p.add_argument('--out',type=Path)
    args=p.parse_args()
    report=audit_saved(json.loads(args.view.read_text()),json.loads(args.ledger.read_text()))
    if args.probes: report['synthetic_linkage']=synthetic_probes()
    text=json.dumps(report,ensure_ascii=False,indent=2)
    if args.out: args.out.write_text(text+'\n',encoding='utf-8')
    else: print(text)
    return bool(report['errors'])

if __name__=='__main__': raise SystemExit(main())
