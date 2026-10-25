/* BOAT LAB: faster same-origin official pay snapshot check (post-race only).
 * Historical forecasts and bets are immutable. Server has already fetched
 * and verified BOATRACE official HTML. Browser never scrapes HTML or guesses.
 */
(function(root){
'use strict';
const VENUE_CODE={
 '桐生':'1','戸田':'2','江戸川':'3','平和島':'4','多摩川':'5','浜名湖':'6',
 '蒲郡':'7','常滑':'8','津':'9','三国':'10','びわこ':'11','住之江':'12',
 '尼崎':'13','鳴門':'14','丸亀':'15','児島':'16','宮島':'17','徳山':'18',
 '下関':'19','若松':'20','芦屋':'21','福岡':'22','唐津':'23','大村':'24'
};
function validCombination(x){
 return typeof x==='string'&&/^[1-6]-[1-6]-[1-6]$/.test(x)&&
  new Set(x.split('-')).size===3;
}
function merge(doc,day,races,existing={},currentAlerts={},now=new Date()){
 const outcome={results:{...existing},alerts:{...currentAlerts},added:0,
  available:false,retrieved_at_utc:null,verified_on_page:0,conflicts:0};
 if(!doc||doc.date!==day||
    doc.status!=='verified_by_server_fetch'||
    doc.evidence_type!=='official_boatrace_pay_snapshot'||
    doc.source_url!=='https://www.boatrace.jp/owpc/pc/race/pay?hd='+day.replace(/-/g,'')||
    !Number.isFinite(Date.parse(doc.retrieved_at_utc))||
    !doc.results||typeof doc.results!=='object'||Array.isArray(doc.results))
  throw Error('公開済みの公式データを検証できません');
 if(!Array.isArray(races)||races.length>288)throw Error('出走表が不正です');
 const officialKeys=Object.keys(doc.results);
 if(officialKeys.length>288)throw Error('公式結果の件数が不正です');
 outcome.available=true;outcome.retrieved_at_utc=doc.retrieved_at_utc;
 outcome.verified_on_page=officialKeys.length;
 const time=now instanceof Date?now.getTime():new Date(now).getTime();
 for(const r of races){
  const code=VENUE_CODE[r.venue];
  const id=code+'-'+r.race;
  const key=day+'|'+r.venue+'|'+r.race;
  if(!code||!Number.isInteger(r.race)||r.race<1||r.race>12||
     !/^[a-f0-9]{64}$/i.test(r.sha256||'')||
     !/^\d{2}:\d{2}$/.test(r.cutoff_jst||'')||
     !Number.isFinite(time)||time<Date.parse(day+'T'+r.cutoff_jst+':00+09:00'))
   continue;
  if(doc.reviews?.[id]||doc.cancellations?.[id]||doc.conflicts?.[id]){
   outcome.alerts[key]={status:'review',reason:'公式結果に返還・中止・矛盾などの確認事項があります'};
   continue;
  }
  if(outcome.alerts[key])continue;
  const p=doc.results[id];
  if(!p||!validCombination(p.finish)||
     !Number.isSafeInteger(p.payout_per_100)||
     p.payout_per_100<100||p.payout_per_100>10000000||
     p.payout_per_100%10!==0)continue;
  const before=outcome.results[key];
  if(before&&(before.finish!==p.finish||before.payout_per_100!==p.payout_per_100)){
   outcome.conflicts++;
   outcome.alerts[key]={status:'conflict',reason:'公式払戻の2種類の保存データが一致しません'};
   continue;
  }
  if(!before){
   outcome.results[key]={
    finish:p.finish,payout_per_100:p.payout_per_100,
    verified:true,source:'boatrace_official_pay',
    source_url:doc.source_url,snapshot_sha256:r.sha256,
    recorded_at:doc.retrieved_at_utc,
    imported_from:'server_verified_daily_pay_snapshot'
   };
   outcome.added++;
  }
 }
 return outcome;
}
async function refresh(day,races,existing,alerts={},fetcher=root.fetch?.bind(root),now=new Date()){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(day))throw Error('日付が不正です');
 if(typeof fetcher!=='function')throw Error('公式結果の取得機能がありません');
 const response=await fetcher('./data/live/official-pay/'+day+'.json?refresh='+Date.now(),{cache:'no-store'});
 if(!response?.ok)throw Error('公式払戻JSON: HTTP '+(response?.status||'取得失敗'));
 return merge(await response.json(),day,races,existing,alerts,now);
}
root.BoatOfficialDirect={refresh,merge,version:'20261025-official-direct-v1'};
})(typeof window==='undefined'?globalThis:window);
