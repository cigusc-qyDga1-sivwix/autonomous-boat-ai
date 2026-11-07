/* BOAT LAB canonical exhibition feed: read-only public GitHub HEAD.
 * GitHub Pages publishes static files asynchronously and can lag immutable
 * pre-cutoff predictions already saved on main. Use a small canonical sync
 * manifest to decide if a full raw latest.json fetch is justified.
 * No client prediction, no post-cutoff promotion, no writeback, no results
 * reconstruction. Failed CORS/network access is a normal, safe fallback.
 */
(function(root){
'use strict';
const BASE='https://raw.githubusercontent.com/cigusc-qyDga1-sivwix/autonomous-boat-ai/main/app/data/live/';
const SYNC=BASE+'forecast-sync-latest.json';
const LIVE=BASE+'latest.json';
const store={lastCheckedAt:'',lastSignal:'',lastStatus:'not_checked',lastError:''};
const eventDay=x=>typeof x==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(x);
const timestamp=x=>{
 const t=typeof x==='string'?Date.parse(x):NaN;
 return Number.isFinite(t)?t:NaN;
};
function validateManifest(meta){
 if(!meta||typeof meta!=='object'||!eventDay(meta.event_date)||
    meta.schema!=='boatlabs.forecast_capture.v1'||meta.status!=='completed'||
    !Number.isInteger(meta.forecast_races)||meta.forecast_races<0||meta.forecast_races>300||
    !Number.isInteger(meta.final_exhibition_verified_races)||
    meta.final_exhibition_verified_races<0||
    meta.final_exhibition_verified_races>meta.forecast_races||
    !Number.isFinite(timestamp(meta.captured_at_utc))||
    !Number.isFinite(timestamp(meta.completed_at_utc))||
    timestamp(meta.completed_at_utc)<timestamp(meta.captured_at_utc))return null;
 return meta;
}
function validatePreview(meta,value){
 if(!value||value.mode!=='auto-live'||value.event_date!==meta.event_date||
   !Array.isArray(value.forecast_races)||
   value.forecast_races.length!==meta.forecast_races||
   !Number.isFinite(timestamp(value.updated_at_utc))||
   timestamp(value.updated_at_utc)<timestamp(meta.captured_at_utc)-1000)return false;
 const exhibition=value.forecast_races.filter(r=>r?.phase==='exhibition').length;
 // The manifest is published with the immutable daily forecast. A CDN edge
 // can briefly serve older JSON; never adopt it as newly verified.
 return exhibition===meta.final_exhibition_verified_races;
}
async function fetchJSON(fetcher,url,clock){
 const join=url.includes('?')?'&':'?';
 const response=await fetcher(url+join+'t='+clock(),{cache:'no-store'});
 if(!response?.ok)throw Error('HTTP '+(response?.status||'取得失敗'));
 return response.json();
}
async function check(options={}){
 const fetcher=options.fetcher||root.fetch?.bind(root);
 const clock=options.clock||Date.now;
 const current=options.current||null;
 if(typeof fetcher!=='function')return {state:'unavailable',reason:'network_unavailable'};
 store.lastCheckedAt=new Date(clock()).toISOString();
 let manifest;
 try{
  manifest=validateManifest(await fetchJSON(fetcher,SYNC,clock));
  if(!manifest)throw Error('manifest_invalid');
 }catch(e){
  store.lastStatus='unavailable';store.lastError=String(e?.message||e);
  return {state:'unavailable',reason:store.lastError};
 }
 const heldDay=current?.event_date||'',heldTime=timestamp(current?.updated_at_utc);
 const stamp=timestamp(manifest.captured_at_utc);
 if((heldDay&&manifest.event_date<heldDay)||
    (heldDay===manifest.event_date&&Number.isFinite(heldTime)&&
     stamp<=heldTime)){
  store.lastStatus='same';store.lastSignal=manifest.completed_at_utc;
  store.lastError='';
  return {state:'same',manifest};
 }
 let candidate;
 try{
  candidate=await fetchJSON(fetcher,LIVE,clock);
  if(!validatePreview(manifest,candidate))throw Error('raw_latest_not_consistent_with_manifest');
 }catch(e){
  store.lastStatus='not_ready';store.lastError=String(e?.message||e);
  // Do NOT cache the signal as successful: retry when raw CDN catches up.
  return {state:'not_ready',manifest,reason:store.lastError};
 }
 if(current&&candidate.event_date===current.event_date&&
    Number.isFinite(heldTime)&&timestamp(candidate.updated_at_utc)<=heldTime){
  store.lastStatus='same';store.lastSignal=manifest.completed_at_utc;
  store.lastError='';
  return {state:'same',manifest};
 }
 store.lastStatus='newer';store.lastSignal=manifest.completed_at_utc;
 store.lastError='';
 return {state:'newer',manifest,payload:candidate};
}
root.BoatCanonicalExhibitionFeed={check,status:()=>({...store}),BASE,SYNC,LIVE};
if(typeof module==='object'&&module.exports)module.exports=root.BoatCanonicalExhibitionFeed;
})(typeof window==='undefined'?globalThis:window);
