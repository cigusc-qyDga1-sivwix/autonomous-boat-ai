"""Prospective statistical shadow snapshots; append only, stdlib inference only."""
from __future__ import annotations
import argparse
import copy
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from boat_ai.statistical import SCHEMA,JST,allocate,digest,distributions,valid_snapshot


def freeze(latest,model,previous,now):
    if now.tzinfo is None:raise ValueError('Timezone required')
    day=now.astimezone(JST).date().isoformat()
    if latest.get('event_date')!=day:raise ValueError('Current day only')
    if model.get('schema')!=SCHEMA or model.get('model_sha256')!=digest({k:v for k,v in model.items() if k!='model_sha256'}):raise ValueError('Model identity mismatch')
    created=datetime.fromisoformat(model['created_at_utc'])
    if created.tzinfo is None or created>now or model['trained_through']>=day:raise ValueError('Future model or training date')
    if previous and previous.get('event_date')!=day:raise ValueError('Ledger date mismatch')
    result=copy.deepcopy(previous) if previous else {'schema':'boatlabs.learned-shadow.v1','event_date':day,'race_records':{}}
    n=0
    for r in latest.get('forecast_races',[]):
        key=f"{r['venue']}-{r['race']}"
        # Latest is a derived view; strip only known presentation-only fields
        # by finding the immutable source externally, never guessing its hash.
        source=r.get('_immutable_source')
        if not source or not valid_snapshot(source,day) or source['sha256']!=r.get('sha256'):continue
        cutoff=datetime.fromisoformat(day+'T'+source['cutoff_jst']+':00+09:00')
        if not datetime.fromisoformat(source['frozen_at_utc'])<=now<cutoff-timedelta(seconds=180):continue
        versions=result['race_records'].setdefault(key,[])
        identity=(source['sha256'],model['model_sha256'])
        if any((v['source_sha256'],v['model_sha256'])==identity for v in versions):continue
        ranked=distributions(source,model)
        bets=allocate(ranked,len(source['bets']))
        body={'model_version':SCHEMA,'model_role':'research_shadow','classification':'WATCH','event_date':day,
              'venue':source['venue'],'race':source['race'],'phase':source['phase'],'frozen_at_utc':now.astimezone(timezone.utc).isoformat(),
              'cutoff_jst':source['cutoff_jst'],'source_sha256':source['sha256'],'model_sha256':model['model_sha256'],
              'trained_through':model['trained_through'],'training_n':model.get('training_n'),'bets':bets,'all_120':ranked,'uncalibrated':True,
              'point_policy':'Matched to original source point count; no ticket rescue or lane quota'}
        body['sha256']=digest(body);versions.append(body);n+=1
    return result,n


def run(data_dir,out_dir,model_path,now):
    latest=json.loads((data_dir/'latest.json').read_text());day=latest['event_date']
    ledger=json.loads((data_dir/f'{day}.json').read_text())
    by_hash={v['sha256']:v for row in ledger.get('race_records',{}).values() for v in row.get('versions',[])}
    for r in latest.get('forecast_races',[]):r['_immutable_source']=by_hash.get(r.get('sha256'))
    model=json.loads(model_path.read_text());path=out_dir/f'statistical-{day}.json'
    previous=json.loads(path.read_text()) if path.exists() else None
    result,n=freeze(latest,model,previous,now)
    if n:
        out_dir.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    slim={'event_date':day,'model_role':'research_shadow','races':{k:{a:b for a,b in v[-1].items() if a!='all_120'} for k,v in result['race_records'].items() if v}}
    slim_path=out_dir/'statistical-latest.json'
    if not slim_path.exists() or json.loads(slim_path.read_text())!=slim:
        out_dir.mkdir(parents=True,exist_ok=True);slim_path.write_text(json.dumps(slim,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    return n


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--data-dir',type=Path,default=Path('app/data/live'));ap.add_argument('--out-dir',type=Path,default=Path('app/data/experiments'));ap.add_argument('--model',type=Path,default=Path('app/data/statistical/latest-model.json'));args=ap.parse_args()
    print(json.dumps({'new_statistical_shadow_snapshots':run(args.data_dir,args.out_dir,args.model,datetime.now(timezone.utc))}))
if __name__=='__main__':main()
