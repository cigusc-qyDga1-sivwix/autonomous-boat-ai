/* BOAT LAB viewing-only portal.
 * Official BOATCAST top-page link, NO iframe/scrape/download/stream URL extraction.
 * Optional authorized local playback uses URL.createObjectURL; file is not uploaded.
 * No network fetches, betting, prediction features, or results.
 */
(function(root) {
'use strict';
const VENUES=['桐生','戸田','江戸川','平和島','多摩川','浜名湖','蒲郡','常滑','津','三国','びわこ','住之江','尼崎','鳴門','丸亀','児島','宮島','徳山','下関','若松','芦屋','福岡','唐津','大村'];
const MAX_BYTES=250*1024*1024;
const BOATCAST='https://boatcast.jp/';
const OFFICIAL_NATIONAL_RACE_INDEX='https://www.boatrace.jp/owpc/pc/race/index';
const JLC_OFFICIAL_REPLAY_BASE='https://livebb.jlc.ne.jp/bb_top/sp_bb/';
function validDay(day){
 if(typeof day!=='string'||!/^20\d{2}-\d{2}-\d{2}$/.test(day))return false;
 const d=new Date(day+'T00:00:00Z');
 return Number.isFinite(d.getTime())&&d.toISOString().slice(0,10)===day;
}
function route(day,venue,race){
 const idx=/^\d{1,2}$/.test(String(venue)) ? Number(venue)-1 : VENUES.indexOf(venue);
 const n=Number(race);
 if(!validDay(day)||idx<0||idx>=VENUES.length||!Number.isInteger(n)||n<1||n>12)return null;
 const code=String(idx+1).padStart(2,'0');
 const encoded=day.replaceAll('-','');
 return {
  day,venue:VENUES[idx],venueCode:code,race:n,
  heading:day+'｜'+VENUES[idx]+' '+n+'R',
  boatcast:BOATCAST,
  raceIndex:OFFICIAL_NATIONAL_RACE_INDEX+'?hd='+encoded,
  jlcExhibition:JLC_OFFICIAL_REPLAY_BASE+'tvod_'+code+'.php',
  beforeinfo:'https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno='+n+'&jcd='+code+'&hd='+encoded,
  racelist:'https://www.boatrace.jp/owpc/pc/race/racelist?rno='+n+'&jcd='+code+'&hd='+encoded,
  records:'./exhibition.html?date='+encoded.slice(0,4)+'-'+encoded.slice(4,6)+'-'+encoded.slice(6,8)
 };
}
function jstDate(now=new Date()){
 const parts=new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(now);
 const v=Object.fromEntries(parts.map(x=>[x.type,x.value]));
 return [v.year,v.month,v.day].join('-');
}
function initial(search,today=jstDate()){
 const q=new URLSearchParams(search||'');
 const day=validDay(q.get('date'))?q.get('date'):today;
 const venue=VENUES.includes(q.get('venue'))?q.get('venue'):(/^\d{1,2}$/.test(q.get('venue')||'')&&Number(q.get('venue'))>=1&&Number(q.get('venue'))<=24?VENUES[Number(q.get('venue'))-1]:'大村');
 const race=Number(q.get('race'));
 return {day,venue,race:Number.isInteger(race)&&race>=1&&race<=12?race:1};
}
function mount(doc,loc,api){
 const el=id=>doc.getElementById(id);
 const day=el('watch-date'),venue=el('watch-venue'),race=el('watch-race');
 const selected=el('selected-race'),link=el('watch-boatcast'),before=el('watch-beforeinfo'),
   list=el('watch-racelist'),records=el('watch-records'),bridge=el('watch-local-bridge'),
   exhibitionReplay=el('watch-jlc-exhibition'),nationalIndex=el('watch-national-index');
 const permission=el('watch-permission'),file=el('watch-file'),player=el('watch-player'),status=el('watch-status');
 if(!day||!venue||!race||!permission||!file||!player)return false;
 const init=initial(loc.search);
 day.value=init.day;
 for(const name of VENUES){const o=doc.createElement('option');o.value=name;o.textContent=name;venue.append(o);}
 for(let n=1;n<=12;n++){const o=doc.createElement('option');o.value=String(n);o.textContent=n+'R';race.append(o);}
 venue.value=init.venue;race.value=String(init.race);
 const refresh=()=>{
  const state=route(day.value,venue.value,race.value);
  selected.textContent=state?state.heading:'有効な開催日・場・Rを選んでください';
  if(!state)return;
  link.href=state.boatcast;before.href=state.beforeinfo;list.href=state.racelist;records.href=state.records;
  if(exhibitionReplay)exhibitionReplay.href=state.jlcExhibition;
  if(nationalIndex)nationalIndex.href=state.raceIndex;
  if(bridge)bridge.href='./local-video-bridge.html?date='+encodeURIComponent(state.day)+'&venue='+encodeURIComponent(state.venue)+'&race='+state.race;
 };
 for(const elem of [day,venue,race])elem.addEventListener('change',refresh);
 refresh();
 let objectUrl=null;
 const release=()=>{
  player.pause();
  player.removeAttribute('src');
  player.load();
  player.hidden=true;
  if(objectUrl){api.revokeObjectURL(objectUrl);objectUrl=null;}
 };
 permission.addEventListener('change',()=>{
  file.disabled=!permission.checked;
  if(!permission.checked){release();file.value='';status.textContent='利用権限を確認すると動画を選べます。';}
  else status.textContent='権限を確認した動画ファイルを選んでください。';
 });
 file.addEventListener('change',()=>{
  release();
  const f=file.files&&file.files[0];
  if(!f)return;
  if(!permission.checked){status.textContent='利用権限の確認が必要です';return;}
  if(!f.size||f.size>MAX_BYTES){
   status.textContent='動画は250MB以下のファイルを選んでください。';status.classList.add('error');return;
  }
  const extension=(f.name||'').split('.').pop().toLowerCase();
  if(!['mp4','m4v','mov','avi','webm'].includes(extension)){
   status.textContent='動画形式を確認してください（MP4推奨）。';status.classList.add('error');return;
  }
  status.classList.remove('error');
  try {
   objectUrl=api.createObjectURL(f);
   player.src=objectUrl;player.hidden=false;
   status.textContent='端末内の動画を表示しています。サーバーへのアップロードなし。';
  }catch(err){status.textContent='動画を開けませんでした：'+(err?.message||'不明');status.classList.add('error');}
 });
 root.addEventListener?.('pagehide',release);
 return true;
}
const exported={VENUES,BOATCAST,OFFICIAL_NATIONAL_RACE_INDEX,JLC_OFFICIAL_REPLAY_BASE,MAX_BYTES,validDay,route,initial,jstDate,mount};
root.BoatExhibitionWatch=exported;
if(typeof module==='object'&&module.exports)module.exports=exported;
if(root.document)mount(root.document,root.location||{search:''},root.URL);
})(typeof window!=='undefined'?window:globalThis);
