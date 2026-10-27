"""Settle only actually frozen statistical shadows with verified official results."""
from __future__ import annotations
import json
from datetime import datetime,timezone,timedelta
from pathlib import Path
from boat_ai.statistical import digest,valid_snapshot
from scripts.train_statistical import metrics,score_bets


def audit(data_dir=Path('app/data/live'),shadow_dir=Path('app/data/experiments')):
    learned=[];control=[];unresolved=0;rejected=0
    for path in sorted(shadow_dir.glob('statistical-????-??-??.json')):
        doc=json.loads(path.read_text());day=doc['event_date'];source=data_dir/f'{day}.json'
        if not source.exists():continue
        records=json.loads(source.read_text())['race_records']
        sources={v['sha256']:(v,row) for row in records.values() for v in row.get('versions',[])}
        for key,versions in doc.get('race_records',{}).items():
            if not versions:continue
            shadow=versions[-1];pair=sources.get(shadow['source_sha256'])
            if not pair:rejected+=1;continue
            original,record=pair
            try:
                cutoff=datetime.fromisoformat(day+'T'+original['cutoff_jst']+':00+09:00')
                frozen=datetime.fromisoformat(shadow['frozen_at_utc'])
                bets=shadow['bets']
                point_free=original.get('model_version')=='four-factor-v1.5-point-free-untrained'
                unit=100 if point_free else 1000
                valid=(shadow.get('sha256')==digest({k:v for k,v in shadow.items() if k!='sha256'})
                       and valid_snapshot(original,day) and shadow['trained_through']<day
                       and shadow['cutoff_jst']==original['cutoff_jst']
                       and datetime.fromisoformat(original['frozen_at_utc'])<=frozen<=cutoff-timedelta(seconds=120)
                       and (1<=len(bets)<=120 if point_free else 4<=len(bets)<=12)
                       and len(bets)==len(original['bets']) and len({b['combination'] for b in bets})==len(bets)
                       and all(len(b['combination'])==5 and len(set(b['combination'].split('-')))==3
                               and all(len(c)==1 and c in '123456' for c in b['combination'].split('-'))
                               and isinstance(b['virtual_yen'],int) and not isinstance(b['virtual_yen'],bool)
                               and b['virtual_yen']>=unit and b['virtual_yen']%unit==0 for b in bets)
                       and sum(b['virtual_yen'] for b in bets)==50000)
            except (ValueError,TypeError,KeyError):valid=False
            if not valid:rejected+=1;continue
            official=record.get('official_pay') or {}
            if official.get('verified') is not True or official.get('source')!='boatrace_official_pay':unresolved+=1;continue
            finish=official.get('finish','')
            if len(finish)!=5 or len(set(finish.split('-')))!=3 or any(len(c)!=1 or c not in '123456' for c in finish.split('-')):rejected+=1;continue
            if official.get('source_url')!='https://www.boatrace.jp/owpc/pc/race/pay?hd='+day.replace('-',''):rejected+=1;continue
            payout=official.get('payout_per_100')
            if not isinstance(payout,int) or isinstance(payout,bool) or payout<100:rejected+=1;continue
            label=[int(x)-1 for x in finish.split('-')]
            a=score_bets(shadow['bets'],label,payout);b=score_bets(original['bets'],label,payout)
            for item in (a,b):item.update(day=day,phase=shadow['phase'],model_sha256=shadow['model_sha256'])
            learned.append(a);control.append(b)
    clean=lambda rows:{k:v for k,v in metrics(rows).items() if k!='mean_nll'}
    return {'schema':'boatlabs.statistical-prospective-audit.v1','created_at_utc':datetime.now(timezone.utc).isoformat(),
            'selection':'Latest actually frozen pre-cutoff shadow per race; original source SHA-matched control',
            'learned':clean(learned),'control':clean(control),'unresolved':unresolved,'rejected':rejected,
            'by_phase':{p:{'learned':clean([x for x in learned if x['phase']==p]),'control':clean([x for x in control if x['phase']==p])} for p in ['baseline','exhibition']}}


def main():
    result=audit();path=Path('app/data/statistical/prospective-audit.json');path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'settled':result['learned']['n'],'unresolved':result['unresolved'],'rejected':result['rejected']}))
if __name__=='__main__':main()
