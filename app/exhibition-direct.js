/* BOAT LAB: just-in-time ORIGINAL exhibition CSV preview. No payout, result or odds.
 * Reads public BoatraceCSV per-source direct snapshots for display-only reanalysis.
 * Cross-origin reads may fail; always retain the archived research fallback.
 */
(function(root){
'use strict';
const VENUES=['桐生','戸田','江戸川','平和島','多摩川','浜名湖','蒲郡','常滑','津','三国','びわこ','住之江','尼崎','鳴門','丸亀','児島','宮島','徳山','下関','若松','芦屋','福岡','唐津','大村'];
const ACCEPT={'一周':['lap_time',30,50],'1周':['lap_time',30,50],
              'まわり足':['turn_time',4,15],'回り足':['turn_time',4,15],
              '直線':['straight_time',5,12]};
const CACHE_INTERVAL_MS=18000;
const MAX_SIZE=2500000;
const entries=new Map();
function parseCsv(raw){
 if(typeof raw!=='string'||raw.length>MAX_SIZE)throw Error('CSVサイズが不正です');
 raw=raw.replace(/^\uFEFF/,'');
 const rows=[];let cells=[],val='',quoted=false;
 for(let i=0;i<raw.length;i++){
  const c=raw[i];
  if(quoted){
   if(c==='"'&&raw[i+1]==='"'){val+='"';i++}
   else if(c==='"')quoted=false;
   else val+=c;
  }else{
   if(c==='"'&&val==='')quoted=true;
   else if(c===','){cells.push(val);val=''}
   else if(c==='\n'){cells.push(val.replace(/\r$/,''));val='';if(cells.some(x=>x!==''))rows.push(cells);cells=[];}
   else val+=c;
  }
 }
 if(quoted)throw Error('CSV引用符が閉じていません');
 cells.push(val.replace(/\r$/,''));if(cells.some(x=>x!==''))rows.push(cells);
 if(!rows.length||rows.length>700)throw Error('展示CSVに有効な行がありません');
 const header=rows.shift();
 if(!header.includes('レースコード')||!header.includes('取得日時')||!header.includes('計測項目1'))
  throw Error('展示CSVの形式が違います');
 return rows.map(row=>Object.fromEntries(header.map((key,i)=>[key,row[i]??''])));
}
function raceId(r,day){
 const n=VENUES.indexOf(r?.venue)+1,number=Number(r?.race);
 if(!/^\d{4}-\d{2}-\d{2}$/.test(day)||n<1||!Number.isInteger(number)||number<1||number>12)return null;
 return day.replaceAll('-','')+String(n).padStart(2,'0')+String(number).padStart(2,'0');
}
function cutoffMs(r,day){
 if(!/^\d{2}:\d{2}$/.test(r?.cutoff_jst||''))return NaN;
 return Date.parse(day+'T'+r.cutoff_jst+':00+09:00');
}
function extract(raw,r,day,nowMs=Date.now()){
 const code=raceId(r,day),cutoff=cutoffMs(r,day);
 if(!code||!Number.isFinite(cutoff))throw Error('レース識別情報が不足しています');
 const rows=parseCsv(raw);
 const rowsForRace=rows.filter(x=>x['レースコード']===code);
 if(!rowsForRace.length)return null;
 const eligible=rowsForRace.filter(x=>{
  if(x['レース日']&&x['レース日']!==day)return false;
  if(x['締切時刻']&&x['締切時刻']!==r.cutoff_jst)return false;
  const observed=Date.parse(x['取得日時']||'');
  return Number.isFinite(observed)&&observed<cutoff&&observed<=nowMs+30000&&observed>cutoff-60*60000;
 }).sort((a,b)=>Date.parse(b['取得日時'])-Date.parse(a['取得日時']));
 if(!eligible.length)return null;
 const row=eligible[0],values={};
 let count=0;
 for(let lane=1;lane<=6;lane++){
  values[lane]={};
  for(let k=1;k<=3;k++){
   const item=ACCEPT[(row['計測項目'+k]||'').trim()];
   const rawValue=row['艇'+lane+'_値'+k];
   if(!item||rawValue==null||rawValue==='')continue;
   const value=Number(rawValue);
   if(Number.isFinite(value)&&value>=item[1]&&value<=item[2]){
    values[lane][item[0]]=value;count++;
   }
  }
 }
 if(!count)return null;
 return {date:day,values,count,source:'BoatraceCSV original_exhibition direct CSV',
  source_observed_jst:row['取得日時'],
  certification:'direct_read_not_immutable_pre_cutoff',source_kind:'direct_preview'};
}
function status(r,day){
 const id=raceId(r,day);return id?entries.get(id)||{state:'idle',count:0}: {state:'invalid',message:'開催場と日付を確認できません'};
}
function get(r,day){
 const x=status(r,day);
 return x.state==='ready'?x.data:null;
}
function refresh(r,day,opts={}){
 const id=raceId(r,day),cutoff=cutoffMs(r,day),now=typeof opts.nowMs==='number'?opts.nowMs:Date.now();
 if(!id||!Number.isFinite(cutoff))return Promise.resolve({state:'invalid',message:'開催場と締切を確認できません'});
 const previous=status(r,day);
 if(now>=cutoff){
  if(previous.state==='ready')return Promise.resolve({...previous,after_cutoff:true});
  const over={state:'cutoff',message:'締切後のため直前データの新規取得を停止しました',count:0};
  entries.set(id,over);return Promise.resolve(over);
 }
 if(previous.promise)return previous.promise;
 if(!opts.force&&previous.checked_at&&now-previous.checked_at<CACHE_INTERVAL_MS)return Promise.resolve(previous);
 const running={...previous,state:previous.state==='ready'?'ready':'loading',checked_at:now,message:'展示CSVを直接確認しています'};
 const promise=(async()=>{
  try{
   const fetcher=opts.fetcher||root.fetch?.bind(root);
   if(typeof fetcher!=='function')throw Error('ネットワーク取得を利用できません');
   const url='https://boatracecsv.github.io/data/previews/original_exhibition/'+day.replaceAll('-','/')+'.csv?at='+now;
   const response=await fetcher(url,{cache:'no-store'});
   if(!response?.ok)throw Error('HTTP '+(response?.status||'接続失敗'));
   const raw=await response.text();
   const data=extract(raw,r,day,now);
   const answer=data?{state:'ready',data,count:data.count,message:'直前CSVから '+data.count+'/18項目を取得',checked_at:now}:
     {state:'unpublished',count:0,message:'直前CSVにこのレースの計測値はまだありません',checked_at:now};
   entries.set(id,answer);return answer;
  }catch(err){
   // An earlier valid snapshot is not erased by transient CORS/network errors.
   const message='直接取得失敗（通信・CORS・公開遅延など）：'+(err?.message||'原因未確認');
   const answer=previous.state==='ready'?{...previous,message,checked_at:now}:
     {state:'error',count:0,message,checked_at:now};
   entries.set(id,answer);return answer;
  }
 })();
 entries.set(id,{...running,promise});
 return promise;
}
root.BoatOriginalExhibitionDirect={parseCsv,raceId,extract,refresh,get,status,CACHE_INTERVAL_MS};
})(typeof window!=='undefined'?window:globalThis);
