import copy
import json
from datetime import datetime,timezone
import pytest
from boat_ai.statistical import *
from scripts.train_statistical import fit,objective,evaluate
from scripts.freeze_statistical_shadow import freeze


def snapshot(day='2026-10-26'):
    v={'venue':'徳山','race':1,'phase':'baseline','cutoff_jst':'10:00','cutoff_iso_jst':day+'T10:00:00+09:00',
       'frozen_at_utc':day+'T08:00:00+09:00',
       'racers':[{'lane':i,'course':i,'national_win_rate':5,'average_start_timing':.17,'motor_top_2_percent':30} for i in range(1,7)],
       'bets':[{'combination':s,'virtual_yen':12500} for s in ['1-2-3','1-3-2','2-1-3','2-3-1']]}
    v['sha256']=digest(v);return v


def zero_model(now='2026-10-27T00:00:00+09:00'):
    m={'schema':SCHEMA,'features':FEATURES,'weights':[[0]*len(FEATURES) for _ in range(3)],'created_at_utc':now,'trained_through':'2026-10-26'}
    m['model_sha256']=digest(m);return m


def test_all120_and_allowlisted_features_and_allocation():
    r=snapshot();m=zero_model();a=distributions(r,m)
    assert len(a)==len({x['combination'] for x in a})==120
    assert sum(x['score'] for x in a)==pytest.approx(1)
    mutated=copy.deepcopy(r);mutated.update(result={'finish':'6-5-4'},odds=999,payout=999999)
    mutated['racers'][0].update(result=1,actual_st=.01)
    assert distributions(mutated,m)==a
    for n in range(4,13):
        bets=allocate(a,n);assert len(bets)==n and sum(x['virtual_yen'] for x in bets)==50000
        assert all(x['virtual_yen']>=1000 and x['virtual_yen']%1000==0 for x in bets)


def test_baseline_exhibition_and_f_no_fast_bonus():
    r=snapshot();p=prepare(r);changed=copy.deepcopy(r);changed['racers'][0].update(exhibition_st=0,exhibition_time=5)
    assert prepare(changed)==p
    changed['phase']='exhibition';changed['racers'][0]['exhibition_st']=-.2
    p=prepare(changed);assert p['raw'][0][4] is None
    assert all(len(features(p,c))==len(FEATURES) for c in range(6))
    changed['racers'][0]['course']=6
    with pytest.raises(ValueError):prepare(changed)


def test_integrity_cutoff_dedup_and_future_exclusion(tmp_path):
    v=snapshot();assert valid_snapshot(v,'2026-10-26')
    broken=copy.deepcopy(v);broken['racers'][0]['national_win_rate']=9
    assert not valid_snapshot(broken,'2026-10-26')
    late=copy.deepcopy(v);late['frozen_at_utc']='2026-10-26T09:59:00+09:00';late['sha256']=digest({k:x for k,x in late.items() if k!='sha256'})
    assert not valid_snapshot(late,'2026-10-26')
    pay={'verified':True,'source':'boatrace_official_pay','source_url':'https://www.boatrace.jp/owpc/pc/race/pay?hd=20261026','finish':'2-6-1','payout_per_100':1100}
    doc={'event_date':'2026-10-26','race_records':{'18-1':{'versions':[v,broken,late],'official_pay':pay}}}
    path=tmp_path/'one.json';path.write_text(json.dumps(doc))
    rows,audit=dataset([path,path],'2026-10-27')
    assert len(rows)==1 and rows[0]['snapshot']==v and audit['duplicate_race']==1
    assert dataset([path],'2026-10-26')[0]==[]
    doc['race_records']['18-1']['official_pay']['verified']=False;path.write_text(json.dumps(doc));assert not dataset([path],'2026-10-27')[0]


def test_gradient_and_fit_use_labels_without_result_input():
    np=pytest.importorskip('numpy');pytest.importorskip('scipy')
    rng=np.random.default_rng(7);x=rng.normal(size=(9,4,len(FEATURES)));y=np.array([i%4 for i in range(9)]);w=rng.normal(size=len(FEATURES))*.1
    loss,grad=objective(w,x,y)
    for j in [0,8,16,len(FEATURES)-1]:
        d=np.zeros_like(w);d[j]=1e-5
        assert grad[j]==pytest.approx((objective(w+d,x,y)[0]-objective(w-d,x,y)[0])/2e-5,abs=1e-7)
    rows=[]
    for i in range(30):
        v=snapshot();winner=i%6;v['racers'][winner]['national_win_rate']=9
        rows.append({'snapshot':v,'label':[winner,(winner+1)%6,(winner+2)%6]})
    model=fit(rows)
    v=snapshot();v['racers'][5]['national_win_rate']=9
    dist=distributions(v,model)
    heads={str(i):sum(x['score'] for x in dist if x['combination'].startswith(str(i)+'-')) for i in range(1,7)}
    assert max(heads,key=heads.get)=='6'


def test_forward_shadow_no_backfill_no_rewrite_and_model_identity():
    now=datetime.fromisoformat('2026-10-27T08:30:00+09:00');s=snapshot('2026-10-27');m=zero_model()
    latest={'event_date':'2026-10-27','forecast_races':[{**s,'_immutable_source':s}]}
    out,n=freeze(latest,m,None,now);assert n==1
    before=copy.deepcopy(out);again,n=freeze(latest,m,out,now);assert n==0 and again==before
    closed,n=freeze(latest,m,None,datetime.fromisoformat('2026-10-27T10:01:00+09:00'));assert n==0
    m['trained_through']='2026-10-27';m['model_sha256']=digest({k:v for k,v in m.items() if k!='model_sha256'})
    with pytest.raises(ValueError):freeze(latest,m,None,now)
    m=zero_model();m['weights'][0][0]=2
    with pytest.raises(ValueError):freeze(latest,m,None,now)


def test_checked_in_temporal_folds_strictly_separate_days():
    path=__import__('pathlib').Path('app/data/statistical/evaluation-latest.json')
    if not path.exists():pytest.skip('artifact absent')
    report=json.loads(path.read_text())
    assert report['folds']
    for fold in report['folds']:
        assert max(fold['train_days'])<fold['test_day']
        assert len({x['source_sha256'] for x in fold['races']})==fold['learned']['n']
    assert report['status'].startswith('retrospective')


def test_prospective_audit_unresolved_not_a_loss_and_source_integrity(tmp_path):
    from scripts.audit_statistical_shadow import audit
    day='2026-10-27';v=snapshot(day);m=zero_model();now=datetime.fromisoformat(day+'T08:30:00+09:00')
    latest={'event_date':day,'forecast_races':[{**v,'_immutable_source':v}]}
    shadow,_=freeze(latest,m,None,now)
    source={'race_records':{'18-1':{'versions':[v]}}}
    data=tmp_path/'live';data.mkdir();exp=tmp_path/'exp';exp.mkdir()
    dp=data/(day+'.json');sp=exp/('statistical-'+day+'.json')
    dp.write_text(json.dumps(source));sp.write_text(json.dumps(shadow))
    result=audit(data,exp);assert result['unresolved']==1 and result['learned']['n']==0
    source['race_records']['18-1']['official_pay']={'verified':True,'source':'boatrace_official_pay',
        'source_url':'https://www.boatrace.jp/owpc/pc/race/pay?hd=20261027','finish':'1-2-3','payout_per_100':1000}
    dp.write_text(json.dumps(source));result=audit(data,exp)
    assert result['learned']['n']==1 and result['control']['n']==1
    shadow['race_records']['徳山-1'][0]['bets'][0]['virtual_yen']+=1000
    sp.write_text(json.dumps(shadow));result=audit(data,exp)
    assert result['rejected']==1 and result['learned']['n']==0
