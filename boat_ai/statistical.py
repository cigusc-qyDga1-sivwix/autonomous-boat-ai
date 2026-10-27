"""Learned conditional choice ranking. Inference has no numerical dependencies.

Inputs are allowlisted pre-race fields only; outcomes are separate training labels.
No named maneuvers, forced neighboring followers or ticket rescue templates.
"""
from __future__ import annotations
import hashlib
import json
import math
from datetime import datetime, timedelta
from itertools import permutations
from zoneinfo import ZoneInfo

SCHEMA = 'conditional-choice-v1'
JST = ZoneInfo('Asia/Tokyo')
BASE_NAMES = ['win_relative','motor_relative','st_relative','exhibition_relative','legal_exhibition_st_relative',
              'win_missing','motor_missing','st_missing','exhibition_missing','legal_st_missing']
FEATURES = BASE_NAMES + [f'course_{i}' for i in range(1,7)] + [
    'skill_x_course','motor_x_course','st_x_course','wind_x_course','wave_x_course',
    'motor_x_wave','skill_x_wind','st_x_inner_gap','entry_change','entry_unconfirmed',
    'head_distance','second_distance','head_skill_x_own','head_motor_x_own','second_skill_x_own',
    'head_is_inside_own','second_is_inside_own']


def digest(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def number(x, lo, hi):
    if x is None or x == '' or isinstance(x,bool): return None
    try: x=float(x)
    except (TypeError,ValueError): return None
    return x if math.isfinite(x) and lo<=x<=hi else None


def prepare(snapshot):
    rows=snapshot.get('racers')
    if not isinstance(rows,list) or len(rows)!=6: raise ValueError('Six racers required')
    rows=sorted(rows,key=lambda x:x['lane'])
    if [r.get('lane') for r in rows]!=list(range(1,7)): raise ValueError('Invalid lanes')
    exhibition=snapshot.get('phase')=='exhibition'
    courses=[r.get('course') for r in rows]
    if sorted(c for c in courses if isinstance(c,int) and not isinstance(c,bool))!=list(range(1,7)):
        raise ValueError('Six distinct saved entry courses required')
    raw=[]
    for r in rows:
        raw.append([number(r.get('national_win_rate'),0,10),number(r.get('motor_top_2_percent'),0,100),
                    None if r.get('average_start_timing_imputed') else number(r.get('average_start_timing'),.01,.4),
                    number(r.get('exhibition_time'),5,10) if exhibition else None,
                    number(r.get('exhibition_st'),0,.5) if exhibition else None])
    # Every transform is within the current race, never fitted on a test day.
    scales=[2,25,.06,.2,.10];signs=[1,1,-1,-1,-1]
    means=[sum(x[j] for x in raw if x[j] is not None)/max(1,sum(x[j] is not None for x in raw)) for j in range(5)]
    values=[[max(-3,min(3,signs[j]*(x[j]-means[j])/scales[j])) if x[j] is not None else 0 for j in range(5)] for x in raw]
    weather=snapshot.get('weather_used') or {}
    wind=(number(weather.get('wind_speed'),0,40) or 0)/8
    wave=(number(weather.get('wave_height'),0,100) or 0)/10
    return {'values':values,'raw':raw,'courses':courses,'wind':min(wind,3),'wave':min(wave,3),'exhibition':exhibition}


def features(p,c,h=None,s=None):
    """Indices are lane-1; stage context contains hypothetical predecessors."""
    own=p['values'][c];course=p['courses'][c];z=(course-3.5)/2.5
    inner=next((i for i,k in enumerate(p['courses']) if k==course-1),None)
    inner_gap=own[2]-p['values'][inner][2] if inner is not None else 0
    hc=p['courses'][h] if h is not None else course
    sc=p['courses'][s] if s is not None else course
    hv=p['values'][h] if h is not None else [0]*5
    sv=p['values'][s] if s is not None else [0]*5
    return own+[float(v is None) for v in p['raw'][c]]+[float(course==k) for k in range(1,7)]+[
        own[0]*z,own[1]*z,own[2]*z,p['wind']*z,p['wave']*z,
        own[1]*p['wave'],own[0]*p['wind'],own[2]*inner_gap,float(course!=c+1),float(not p['exhibition']),
        (course-hc)/5,(course-sc)/5,own[0]*hv[0],own[1]*hv[1],own[0]*sv[0],
        float(h is not None and hc<course),float(s is not None and sc<course)]


def softmax(scores):
    maximum=max(scores);e=[math.exp(x-maximum) for x in scores];t=sum(e)
    return [x/t for x in e]


def distributions(snapshot, model):
    if model.get('schema')!=SCHEMA or model.get('features')!=FEATURES:raise ValueError('Wrong feature schema')
    weights=model.get('weights',[])
    if len(weights)!=3 or any(len(w)!=len(FEATURES) or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in w) for w in weights):raise ValueError('Invalid learned weights')
    p=prepare(snapshot)
    def stage(stage,h=None,s=None):
        ids=[c for c in range(6) if c not in (h,s)]
        return dict(zip(ids,softmax([sum(a*b for a,b in zip(features(p,c,h,s),weights[stage])) for c in ids])))
    first=stage(0);all_rows=[]
    for h in range(6):
        second=stage(1,h)
        for s in second:
            third=stage(2,h,s)
            for t in third:all_rows.append({'combination':f'{h+1}-{s+1}-{t+1}','score':first[h]*second[s]*third[t]})
    return sorted(all_rows,key=lambda x:(-x['score'],x['combination']))


def allocate(ranked,count,*,point_free=False):
    if isinstance(count,bool) or not isinstance(count,int) or not (1<=count<=120 if point_free else 4<=count<=12):raise ValueError('Invalid point count')
    budget_units=500 if point_free else 50;stake_unit=100 if point_free else 1000
    selected=ranked[:count];total=sum(x['score'] for x in selected)
    target=[(budget_units-count)*x['score']/total for x in selected]
    units=[math.floor(x)+1 for x in target]
    for i in sorted(range(count),key=lambda i:(-(target[i]-math.floor(target[i])),i))[:budget_units-sum(units)]:units[i]+=1
    return [{'combination':r['combination'],'virtual_yen':units[i]*stake_unit,'relative_score':r['score']} for i,r in enumerate(selected)]


def valid_snapshot(v,day):
    try:
        if v.get('sha256')!=digest({k:x for k,x in v.items() if k!='sha256'}):return False
        freeze=datetime.fromisoformat(v['frozen_at_utc']);cutoff=datetime.fromisoformat(day+'T'+v['cutoff_jst']+':00+09:00')
        if freeze.tzinfo is None or freeze>cutoff-timedelta(seconds=120):return False
        if v.get('cutoff_iso_jst') and datetime.fromisoformat(v['cutoff_iso_jst'])!=cutoff:return False
        prepare(v)
        if v.get('phase')=='exhibition' and any(number(r.get('exhibition_time'),5,10) is None or number(r.get('exhibition_st'),-.5,1) is None for r in v['racers']):return False
        return v.get('phase') in ('baseline','exhibition')
    except (ValueError,TypeError,KeyError,OverflowError):return False


def dataset(paths,before_day):
    """One latest eligible original snapshot per race; no enrichment/backfill."""
    records=[];audit={};seen=set()
    def skip(reason):audit[reason]=audit.get(reason,0)+1
    for path in sorted(paths):
        doc=json.loads(path.read_text());day=doc.get('event_date','')
        if not day or day>=before_day:continue
        for key,r in sorted(doc.get('race_records',{}).items()):
            identity=(day,key)
            if identity in seen:skip('duplicate_race');continue
            seen.add(identity)
            pay=r.get('official_pay') or {};finish=pay.get('finish','')
            if pay.get('verified') is not True or pay.get('source')!='boatrace_official_pay':skip('unverified');continue
            expected_url='https://www.boatrace.jp/owpc/pc/race/pay?hd='+day.replace('-','')
            if pay.get('source_url')!=expected_url:skip('wrong_official_date');continue
            if not isinstance(finish,str) or len(finish)!=5 or len(set(finish.split('-')))!=3 or any(x not in '123456' or len(x)!=1 for x in finish.split('-')):skip('non_unique_finish');continue
            payout=pay.get('payout_per_100')
            if isinstance(payout,bool) or not isinstance(payout,int) or payout<100:skip('invalid_payout');continue
            versions=[v for v in r.get('versions',[]) if valid_snapshot(v,day)]
            if not versions:skip('no_safe_original_snapshot');continue
            v=max(versions,key=lambda v:datetime.fromisoformat(v['frozen_at_utc']))
            records.append({'day':day,'race_key':key,'snapshot':v,'label':[int(x)-1 for x in finish.split('-')],
                            'payout':payout,'official':pay})
    return records,audit
