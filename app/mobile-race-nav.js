/* BOAT LAB mobile navigation: 1–12R picker and safe left-swipe back.
 * Read-only navigation; never edits frozen predictions, bets or settlements.
 */
(function(global){
'use strict';
const MIN_X=90,MAX_Y=75,MAX_MS=750;
const EXCLUDE='button,a,input,textarea,select,summary,[contenteditable="true"],[role="slider"],[data-no-back-swipe],.tablewrap,.boat-entry-overflow,.race-sim,.boat-sim,.race-timeline,.recalc-form-scroll,.carousel,.horizontal-scroll,.venue-race-picker';
const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function racePicker(venue,current,forecasts,missing=[]){
 const available=new Map((forecasts||[]).filter(r=>r?.venue===venue&&
  Number.isInteger(Number(r.race))&&Number(r.race)>=1&&Number(r.race)<=12).map(r=>[Number(r.race),r]));
 const absent=new Set((missing||[]).filter(r=>r?.venue===venue).map(r=>Number(r.race)));
 const buttons=[];
 for(let n=1;n<=12;n++){
  const exists=available.has(n),selected=current===n;
  const title=exists?n+'Rの予想を見る':
    absent.has(n)?n+'Rの予想は発走前に固定できませんでした':n+'Rの予想データは未取得です';
  buttons.push('<button type="button" class="venue-race-choice'+(selected?' is-active':'')+
   (exists?'':' is-unavailable')+'" data-select-race="'+escape(venue)+'|'+n+'"'+
   (exists?'':' disabled')+(selected?' aria-current="true"':'')+
   ' aria-label="'+escape(title)+'" title="'+escape(title)+'">'+n+
   '<span>R</span>'+(exists?'':'<small>未固定</small>')+'</button>');
 }
 return '<nav class="venue-race-picker" aria-label="'+escape(venue)+' 1Rから12Rを選択">'+
  '<div class="venue-race-picker-title"><strong>🎯 '+escape(venue)+'のレースを選択</strong>'+
  '<span>1〜12R ／ 灰色は予想未固定</span></div>'+
  '<div class="venue-race-picker-grid">'+buttons.join('')+'</div></nav>';
}
function shouldIgnore(target){
 if(!target||typeof target.closest!=='function')return true;
 if(target.closest(EXCLUDE))return true;
 // Preserve horizontal scrolling on other wide components as well.
 let item=target;
 for(let i=0;i<9&&item;i++,item=item.parentElement){
  if(typeof item.scrollWidth==='number'&&typeof item.clientWidth==='number'&&
    item.clientWidth>0&&item.scrollWidth>item.clientWidth+8)return true;
 }
 return false;
}
function decideSwipe(start,end){
 if(!start||!end||start.fingers!==1||end.fingers>1||
    start.exclude||end.exclude)return false;
 const dx=end.x-start.x,dy=end.y-start.y,elapsed=end.time-start.time;
 return elapsed>=0&&elapsed<=MAX_MS&&dx<=-MIN_X&&Math.abs(dy)<=MAX_Y&&
   Math.abs(dx)>Math.abs(dy)*1.65;
}
function installSwipe(element,onBack,opts={}){
 if(!element||typeof element.addEventListener!=='function'||typeof onBack!=='function')
  return ()=>{};
 let begin=null,done=false;
 const clock=opts.now||(()=>Date.now());
 const getPoint=e=>{
  const t=e?.changedTouches?.[0]||e?.touches?.[0];
  return t&&Number.isFinite(t.clientX)&&Number.isFinite(t.clientY)?
   {x:t.clientX,y:t.clientY,time:clock(),fingers:e.touches?.length||e.changedTouches?.length||1}:null;
 };
 const start=e=>{
  const p=getPoint(e);
  begin=p?{...p,exclude:shouldIgnore(e.target)||p.fingers!==1}:null;
  done=false;
 };
 const end=e=>{
  if(!begin||done)return;
  const p=getPoint(e);
  if(p){p.exclude=shouldIgnore(e.target);p.fingers=e.touches?.length>1?2:1;}
  const valid=decideSwipe(begin,p);
  begin=null;
  if(valid){done=true;onBack();}
 };
 const cancel=()=>{begin=null;done=false;};
 element.addEventListener('touchstart',start,{passive:true});
 element.addEventListener('touchend',end,{passive:true});
 element.addEventListener('touchcancel',cancel,{passive:true});
 return ()=>{
  element.removeEventListener?.('touchstart',start);
  element.removeEventListener?.('touchend',end);
  element.removeEventListener?.('touchcancel',cancel);
 };
}
global.BoatMobileRaceNav={racePicker,shouldIgnore,decideSwipe,installSwipe};
})(typeof window!=='undefined'?window:globalThis);
