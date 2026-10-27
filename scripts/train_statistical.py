"""Retrospective chronological evaluation, then a forward-only research artifact.

The temporal tests are reconstructed now, not forecasts actually made in the past.
Nothing in this script changes production predictions or historical frozen hashes.
"""
from __future__ import annotations
import argparse
import json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from boat_ai.statistical import SCHEMA,FEATURES,JST,allocate,dataset,digest,distributions,features,prepare

L2=.03  # Fixed before evaluating the dates. Not tuned on holdout outcomes.


def objective(w,x,y,l2=L2):
    import numpy as np
    from scipy.special import logsumexp
    scores=x@w
    loss=float(np.mean(logsumexp(scores,axis=1)-scores[np.arange(len(y)),y])+.5*l2*np.dot(w,w))
    p=np.exp(scores-logsumexp(scores,axis=1)[:,None]);p[np.arange(len(y)),y]-=1
    grad=np.einsum('nk,nkf->f',p,x)/len(y)+l2*w
    return loss,grad


def fit(rows):
    import numpy as np
    from scipy.optimize import minimize
    if not rows:raise ValueError('No training data')
    weights=[];optimization=[]
    for stage in range(3):
        xs=[];ys=[]
        for row in rows:
            p=prepare(row['snapshot']);h=row['label'][0] if stage>0 else None;s=row['label'][1] if stage>1 else None
            ids=[c for c in range(6) if c not in (h,s)]
            xs.append([features(p,c,h,s) for c in ids]);ys.append(ids.index(row['label'][stage]))
        x=np.asarray(xs);y=np.asarray(ys)
        result=minimize(objective,np.zeros(len(FEATURES)),args=(x,y),jac=True,method='L-BFGS-B',options={'maxiter':250,'gtol':1e-7,'ftol':1e-11})
        if not result.success:raise RuntimeError('Optimizer did not converge: '+str(result.message))
        weights.append(result.x.tolist());optimization.append({'success':True,'iterations':int(result.nit),'penalized_loss':float(result.fun)})
    return {'schema':SCHEMA,'features':FEATURES,'weights':weights,'l2':L2,'optimization':optimization}


def metrics(rows):
    n=len(rows);stake=sum(r['stake'] for r in rows);payout=sum(r['payout'] for r in rows)
    return {'n':n,'hits':sum(r['hit'] for r in rows),'hit_rate':sum(r['hit'] for r in rows)/n if n else None,
            'head_miss':sum(r['stage']=='head_miss' for r in rows),'second_miss':sum(r['stage']=='second_miss' for r in rows),
            'third_miss':sum(r['stage']=='third_miss' for r in rows),'virtual_stake_yen':stake,'virtual_payout_yen':payout,
            'return_rate':payout/stake if stake else None,'mean_nll':sum(r['nll'] for r in rows)/n if n else None}


def score_bets(bets,label,payout,probability=None):
    import math
    finish='-'.join(str(x+1) for x in label);heads=[b['combination'].split('-')[0] for b in bets]
    pair='-'.join(finish.split('-')[:2]);pairs=['-'.join(b['combination'].split('-')[:2]) for b in bets]
    winning=next((b for b in bets if b['combination']==finish),None)
    stage='hit' if winning else 'third_miss' if pair in pairs else 'second_miss' if finish[0] in heads else 'head_miss'
    return {'hit':bool(winning),'stage':stage,'stake':sum(b['virtual_yen'] for b in bets),
            'payout':winning['virtual_yen']//100*payout if winning else 0,
            'nll':-math.log(max(probability,1e-15)) if probability is not None else 0}


def evaluate(rows):
    days=sorted({r['day'] for r in rows});folds=[];all_learned=[];all_existing=[]
    for day in days:
        train=[r for r in rows if r['day']<day];test=[r for r in rows if r['day']==day]
        if len(train)<100:continue
        model=fit(train);learned=[];existing=[];details=[]
        for row in test:
            ranked=distributions(row['snapshot'],model)
            # Point count locked to the existing snapshot for a matched comparison.
            count=len(row['snapshot']['bets']);bets=allocate(ranked,count,point_free=row['snapshot'].get('model_version')=='four-factor-v1.5-point-free-untrained')
            finish='-'.join(str(x+1) for x in row['label']);p=next(x['score'] for x in ranked if x['combination']==finish)
            a=score_bets(bets,row['label'],row['payout'],p);b=score_bets(row['snapshot']['bets'],row['label'],row['payout'])
            a['day']=b['day']=day;a['phase']=b['phase']=row['snapshot']['phase']
            learned.append(a);existing.append(b)
            details.append({'race_key':row['race_key'],'source_sha256':row['snapshot']['sha256'],'phase':a['phase'],
                            'finish':finish,'learned_stage':a['stage'],'existing_stage':b['stage'],
                            'learned_bets':bets})
        folds.append({'test_day':day,'train_days':sorted({r['day'] for r in train}),'train_n':len(train),
                      'learned':metrics(learned),'existing':{k:v for k,v in metrics(existing).items() if k!='mean_nll'},'races':details})
        all_learned.extend(learned);all_existing.extend(existing)
    return {'folds':folds,'learned':metrics(all_learned),'existing':{k:v for k,v in metrics(all_existing).items() if k!='mean_nll'},
            'by_phase':{phase:{'learned':metrics([x for x in all_learned if x['phase']==phase]),
                                'existing':{k:v for k,v in metrics([x for x in all_existing if x['phase']==phase]).items() if k!='mean_nll'}} for phase in ['baseline','exhibition']},
            'status':'retrospective_chronological_reconstruction_not_prospective',
            'limits':['Only five archived dates at initial creation; repeated athletes and conditions are correlated.',
                      'Official labels are available now; their historic collection time is not simulated.',
                      'No hyperparameter search on these folds; design influenced by prior observed results.',
                      'Conditional rank scores are uncalibrated, not betting probabilities.',
                      'Point counts are matched to original forecasts, not optimized; payout never enters fitting.']}


def refresh(data_dir,out_dir,now):
    day=now.astimezone(JST).date().isoformat();rows,audit=dataset(sorted(data_dir.glob('????-??-??.json')),day)
    if len(rows)<100:raise ValueError('At least 100 unique labeled races required')
    manifest=[{'day':r['day'],'race_key':r['race_key'],'snapshot_sha256':r['snapshot']['sha256'],'official_label_sha256':digest(r['official'])} for r in rows]
    manifest_hash=digest(manifest);code_hash=digest([Path(__file__).read_text(),Path('boat_ai/statistical.py').read_text()])
    latest=out_dir/'latest-model.json'
    if latest.exists():
        old=json.loads(latest.read_text())
        if old.get('dataset_sha256')==manifest_hash and old.get('training_code_sha256')==code_hash:return old,None
    model=fit(rows);model.update({'created_at_utc':now.astimezone(timezone.utc).isoformat(),'trained_through':max(r['day'] for r in rows),
      'training_n':len(rows),'training_days':dict(sorted(Counter(r['day'] for r in rows).items())),
      'dataset_sha256':manifest_hash,'training_code_sha256':code_hash,'role':'research_shadow','calibrated':False,
      'promotion_status':'not_promoted_insufficient_prospective_evidence'})
    model['model_sha256']=digest(model)
    report=evaluate(rows);report.update({'schema':SCHEMA,'created_at_utc':model['created_at_utc'],'training_n':len(rows),'dataset_audit':audit,'training_days':model['training_days'],
                                       'input_coverage':{name:sum(prepare(r['snapshot'])['raw'][c][j] is not None for r in rows for c in range(6)) for j,name in enumerate(FEATURES[:5])},
                                       'unused_unavailable_inputs':['Athlete-specific course 1st/2nd/3rd rates','Per-athlete maneuver success','Race video trajectories','Odds','Post-race actual ST'],
                                       'model_sha256':model['model_sha256'],'manifest':manifest})
    out_dir.mkdir(parents=True,exist_ok=True);(out_dir/'models').mkdir(exist_ok=True)
    for path,obj in [(latest,model),(out_dir/'models'/f"{model['model_sha256']}.json",model),(out_dir/'evaluation-latest.json',report)]:
        path.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n')
    return model,report


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data-dir',type=Path,default=Path('app/data/live'));ap.add_argument('--out-dir',type=Path,default=Path('app/data/statistical'));args=ap.parse_args()
    model,report=refresh(args.data_dir,args.out_dir,datetime.now(timezone.utc))
    print(json.dumps({'training_n':model['training_n'],'trained_through':model['trained_through'],'model_sha256':model['model_sha256'],
                      'evaluation':{k:report[k] for k in ('learned','existing','by_phase')} if report else 'unchanged'},ensure_ascii=False))
if __name__=='__main__':main()
