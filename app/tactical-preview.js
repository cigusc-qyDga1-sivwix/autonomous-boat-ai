/* BOAT LAB tactical preview, experimental visualisation ONLY.
 * Edits are device-local. Neither bets, forecast hashes nor settlements change.
 * This is a geometric hypothesis, NOT measured speed, win probability or video analysis.
 */
(function () {
'use strict';
if (!window.BoatRaceVisual) return;
const api=window.BoatRaceVisual;
const priorDispose=api.dispose;
let mounted=null;
const color=['#ffffff','#17212e','#ea4552','#4089ed','#efce42','#28b875'];
const font=['#15253c','#ffffff','#ffffff','#ffffff','#263240','#ffffff'];
const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
const n=v=>(v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v)))?Number(v):null;
const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
const kinds=[['escape','逃げ・先マイ'],['sashi','差し'],['makuri','まくり'],['makuri-zashi','まくり差し'],['follow','追走・残り']];
function list(r){return [...(r&&Array.isArray(r.racers)?r.racers:[])].sort((a,b)=>Number(a.lane)-Number(b.lane));}
function courseAverage(x,c){
 const table=x.course_average_st_by_course||x.course_st_by_course||x.course_avg_st_by_course;
 const v=Array.isArray(table)?table[c-1]:(table&&(table[c]??table[String(c)]));
 return validST(v)?Number(v):null;
}
function validST(v){const x=n(v);return x!==null&&x>=.01&&x<=.40;}
function courseSTCount(x,c){
 const tab=x.course_st_samples_by_course||x.course_start_count_by_course||x.course_st_count_by_course;
 const raw=Array.isArray(tab)?tab[c-1]:(tab&&(tab[c]??tab[String(c)]));const v=n(raw);
 return v!==null&&Number.isInteger(v)&&v>=0&&v<=10000?v:null;
}
function defaults(r){
 const racers=list(r);
 const courses=racers.map((x,i)=>Number(x.course??x.entry_course??i+1));
 const permutation=new Set(courses).size===6&&courses.every(x=>Number.isInteger(x)&&x>=1&&x<=6);
 const wind=r.weather_used||r.weather_observed||{};
 const venue=window.BoatVenueGeometry?.get(r.venue);
 return {
  boats:racers.map((x,i)=>{
   const c=permutation?courses[i]:i+1;
   return {lane:i+1,course:c,group:c<=3?'slow':'dash',
    kind:c===1?'escape':c===2?'sashi':c>=5?'makuri':'makuri-zashi',
    st:courseAverage(x,c),stSamples:courseSTCount(x,c)};
  }),
  wind:n(wind.wind_speed),wave:n(wind.wave_height),relativeWind:'unknown',
  startWidthM:venue?.startWidthM??null,turn1WidthM:venue?.turn1WidthM??null,
  source:permutation&&r.phase==='exhibition'?'展示時の進入':'枠番または取得済み進入'
 };
}
function validWidth(value){const v=n(value);return v!==null&&v>=20&&v<=100;}
function normalise(cfg){
 if(!cfg||!Array.isArray(cfg.boats)||cfg.boats.length!==6)return null;
 const courses=cfg.boats.map(b=>Number(b.course));
 if(new Set(courses).size!==6||courses.some(c=>!Number.isInteger(c)||c<1||c>6))return null;
 return {boats:cfg.boats.map((b,i)=>({lane:i+1,course:Number(b.course),
  group:b.group==='dash'?'dash':'slow',
  kind:kinds.some(k=>k[0]===b.kind)?b.kind:'follow',
  st:validST(b.st)?Number(b.st):null,
  stSamples:Number.isInteger(b.stSamples)&&b.stSamples>=0&&b.stSamples<=10000?b.stSamples:null})),
  wind:n(cfg.wind),wave:n(cfg.wave),
  startWidthM:validWidth(cfg.startWidthM)?Number(cfg.startWidthM):null,
  turn1WidthM:validWidth(cfg.turn1WidthM)?Number(cfg.turn1WidthM):null,
  relativeWind:['unknown','head','tail','cross'].includes(cfg.relativeWind)?cfg.relativeWind:'unknown',
  source:String(cfg.source||'手動設定').slice(0,60)};
}
// Small, explicitly UNCALIBRATED scenario nudges derived from official qualitative
// headwind/turn and tailwind/sashi explanations. No real win probabilities.
function directionalHypothesis(cfg,b){
 const wind=clamp(n(cfg.wind)??0,0,30);
 if(wind<3||cfg.relativeWind==='unknown'||cfg.relativeWind==='cross')
   return {delta:0,reason:'風向補正なし'};
 const factor=clamp((wind-2)/4,0,1);
 let delta=0,reason='中立';
 if(cfg.relativeWind==='head'){
   if(b.group==='slow'){delta-=.020*factor;reason='スロー勢の立ち上がりリスク';}
   if(b.course>=2&&b.course<=5&&b.kind==='makuri'){
     delta+=.055*factor;reason='向かい風でのまくり仮説';
   }else if(b.course>=2&&b.course<=5&&b.kind==='makuri-zashi'){
     delta+=.035*factor;reason='向かい風でのまくり差し仮説';
   }
 }else if(cfg.relativeWind==='tail'){
   if(b.course>=2&&b.course<=4&&b.kind==='sashi'){
     delta+=.055*factor;reason='追い風による差し余地仮説';
   }else if(b.kind==='makuri'){
     delta-=.025*factor;reason='追い風時の握った旋回の流れリスク';
   }else if(b.course===1&&b.kind==='escape'&&wind<=5){
     delta+=.015*factor;reason='比較的弱い追い風での逃げ残存仮説';
   }
 }
 return {delta,reason};
}
function windExplanation(cfg){
 const v=n(cfg.wind),w=cfg.relativeWind;
 if(v==null||w==='unknown')return '水面に対する風向が未判定。勝ち筋への方向補正なし。';
 if(v<3)return '風速3m/s未満は方向による順位補正なし（試験基準）。';
 if(w==='head')return '向かい風 '+v+'m/s：スロー勢の立ち上がりとセンター勢のまくり・まくり差しを検討。';
 if(w==='tail')return '追い風 '+v+'m/s：1マークの外への流れと2・3コース差しを検討。強い追い風では逃げ確定とみなさない。';
 return '横風 '+v+'m/s：水面に対する左右方向が未判定のため、有利艇を自動決定しない。';
}
function analyze(r,config){
 const racers=list(r);const cfg=normalise(config)||defaults(r);
 const boats=cfg.boats.map(b=>{
  const src=racers[b.lane-1]||{};
  const ref=validST(src.average_start_timing)?Number(src.average_start_timing):null;
  const st=validST(b.st)?b.st:(ref??.17);
  const sample=b.stSamples;
  const origin=b.st!=null?'進入コース別'+(sample!=null?' '+sample+'走'+(sample<10?'・小標本':''):'（任意入力または標本不明）'):
    ref!=null?'全国平均STを参考':'ST未取得・中立値';
  const exhib=n(src.exhibition_st);
  // Exhibition F is not fast ST; do not treat exhibition as a course average.
  const front=cfg.boats.filter(q=>q.course<b.course).map(q=>{
   const x=racers[q.lane-1]||{};return validST(q.st)?q.st:validST(x.average_start_timing)?Number(x.average_start_timing):.17;
  });
  const slowInside=front.length?front.reduce((a,c)=>a+c,0)/front.length-st:0;
  const attack=(b.kind==='makuri'||b.kind==='makuri-zashi')?
       clamp(slowInside*3.8,-.20,.36):b.kind==='sashi'?.12:b.kind==='escape'?.18:0;
  const extra=exhib!==null&&exhib>=0&&exhib<=.40?clamp((.17-exhib)*.38,-.04,.04):0;
  const baseScore=1.42-(b.course-1)*.14+(.17-st)*6.2+attack+extra+
    (b.group==='dash'?.02:0);
  const windBias=directionalHypothesis(cfg,b);
  return {...b,st,origin,exhibition_st:exhib,score:baseScore+windBias.delta,baseScore,windBias,attack};
 });
 const sorted=[...boats].sort((a,b)=>b.score-a.score||a.course-b.course);
 const rank={};sorted.forEach((b,i)=>{rank[b.lane]=i+1;});
 const wind=clamp(cfg.wind??0,0,30),wave=clamp(cfg.wave??0,0,50);
 const uncertainty=clamp((wind/7+wave/14)/2,0,1);
 const geometry=window.BoatVenueGeometry?.layout({venue:r.venue,startWidthM:cfg.startWidthM,turn1WidthM:cfg.turn1WidthM})||
   {available:false,markY:182,narrowingPx:0,quality:'unavailable',note:'水面形状未取得'};
 return {cfg,boats,rank,order:sorted.map(b=>b.lane),geometry,
   uncertainty,wind,wave,
   summary:'試算バック隊形 '+sorted.slice(0,3).map(b=>b.lane).join('-')+
      ' ／ スタート先行想定 '+[...boats].sort((a,b)=>a.st-b.st)[0].lane+'号艇',
   note:windExplanation(cfg)+' 風による評価の変化は最大でも小さな試験値で、実測確率ではない。会場別の旋回モデルも未校正。'
 };
}
function trajectory(b,rank,plan){
 const c=b.course;
 const startX=b.group==='dash'?60:113;
 const startY=147+c*18;
 const outer=(b.kind==='makuri'?45:b.kind==='makuri-zashi'?24:b.kind==='sashi'?-20:b.kind==='escape'?-31:0);
 const directional=plan.cfg.relativeWind==='cross'?plan.wind*.9:plan.cfg.relativeWind==='tail'?plan.wind*.4:plan.cfg.relativeWind==='head'?-plan.wind*.4:0;
 const narrowed=plan.geometry?.narrowingPx||0;
 const xTurn=542+outer+plan.uncertainty*12+directional+narrowed*.18;
 const yTurn=(plan.geometry?.markY??182)-12+outer*.3+plan.uncertainty*20+
   (plan.cfg.relativeWind==='cross'?plan.wind*.4:0);
 const leadX=435+clamp((.17-b.st)*380,-30,30);
 const backY=36+rank*24;
 const exitX=210+rank*11;
 return 'M'+startX+' '+startY+
 ' C'+(startX+110)+' '+(startY-5)+' '+leadX+' '+(startY-2)+' 470 '+(177+c*9+narrowed*.38)+
 ' C525 '+(175+c*8+narrowed*.38)+' '+(xTurn+6)+' '+(yTurn+30)+' '+xTurn+' '+yTurn+
 ' C'+(xTurn-16)+' '+(yTurn-63)+' 463 '+(backY+12)+' 426 '+backY+
 ' C357 '+backY+' 280 '+backY+' '+exitX+' '+backY;
}
function drawControls(r,plan){
 const racers=list(r);
 const input=(name,label,v,min,max,step)=>'<label>'+label+'<input type="number" data-plan-env="'+name+'" min="'+min+'" max="'+max+'" step="'+step+'" value="'+(v==null?'':v)+'" placeholder="未取得"></label>';
 let html='<div class="plan-editor-intro">進入隊形（コース1→6）を変更可能。重複コースを選ぶと自動で入れ替えます。<strong>保存済み予想は不変</strong>。</div><div class="plan-rows">';
 for(const b of [...plan.cfg.boats].sort((a,b)=>a.course-b.course)){
  const x=racers[b.lane-1]||{},ref=validST(x.average_start_timing)?Number(x.average_start_timing).toFixed(2):'—';
  html+='<div class="plan-row"><div class="plan-player"><b class="plan-lane plan-lane-'+b.lane+'">'+b.lane+'</b><span>'+esc(x.name||'選手未取得')+'<small>全国平均ST '+ref+'</small></span></div>'+
   '<label>進入<select data-plan-course="'+b.lane+'">'+[1,2,3,4,5,6].map(v=>'<option value="'+v+'"'+(v===b.course?' selected':'')+'>'+v+'コース</option>').join('')+'</select></label>'+
   '<label>隊形<select data-plan-group="'+b.lane+'"><option value="slow"'+(b.group==='slow'?' selected':'')+'>スロー</option><option value="dash"'+(b.group==='dash'?' selected':'')+'>ダッシュ</option></select></label>'+
   '<label>進入別ST'+(b.stSamples!=null?'（'+b.stSamples+'走）':'（標本不明）')+'<input data-plan-st="'+b.lane+'" inputmode="decimal" type="number" min=".01" max=".40" step=".01" value="'+(b.st===null?'':b.st.toFixed(2))+'" placeholder="未取得"></label>'+
   '<label>攻め方<select data-plan-kind="'+b.lane+'">'+kinds.map(k=>'<option value="'+k[0]+'"'+(k[0]===b.kind?' selected':'')+'>'+k[1]+'</option>').join('')+'</select></label></div>';
 }
 html+='</div><div class="plan-venue-header">🌊 '+esc(r.venue||'会場未取得')+'の1マーク水面幅：'+esc(plan.geometry.available?'自動参考配置':'未取得')+
  ' <small>'+(plan.geometry.quality==='official_text_crosschecked'?'公式テキスト照合':'暫定値・要公式確認')+'</small></div>'+
  '<div class="plan-environment">'+input('startWidthM','スタート地点のスタンド側幅（m）',plan.cfg.startWidthM,20,100,.1)+
  input('turn1WidthM','1マークのスタンド側幅（m）',plan.cfg.turn1WidthM,20,100,.1)+
  input('wind','風速（m/s）',plan.cfg.wind,0,30,.1)+input('wave','波高（cm）',plan.cfg.wave,0,50,1)+
 '<label>水面に対する風<select data-plan-env="relativeWind">'+[
 ['unknown','向き未判定'],['head','向かい風'],['tail','追い風'],['cross','横風']
 ].map(a=>'<option value="'+a[0]+'"'+(plan.cfg.relativeWind===a[0]?' selected':'')+'>'+a[1]+'</option>').join('')+'</select></label></div>';
 return html;
}
function svgHTML(r,plan){
 let s='<svg viewBox="0 0 680 315" role="img" aria-label="スタートから第一マーク、バックへの六艇の試験的航跡図" preserveAspectRatio="xMidYMid meet">'+
 '<rect width="680" height="315" fill="#09384e" rx="13"/>'+
 '<path d="M125 139V275" stroke="#c5eaf0" stroke-width="2" stroke-dasharray="6 6"/>'+
 '<text x="83" y="295" fill="#c4ebf2" font-size="12">START</text>'+
 '<path d="M175 30H454" stroke="#7abed0" stroke-dasharray="9 5" fill="none"/>'+
 '<text x="290" y="20" fill="#bdeaf4" font-size="13">← BACK</text>'+
 '<circle cx="560" cy="'+plan.geometry.markY+'" r="10" fill="#ffae37" stroke="#fff2b8" stroke-width="2" data-plan-mark="1"/>'+
 '<text x="585" y="'+(plan.geometry.markY-3)+'" fill="#ffc77d" font-size="13" data-plan-mark-label="1">1M</text>'+
 '<text x="16" y="30" fill="#bdeaf4" font-size="10">TACTICAL VIEW / EXPERIMENT</text>';
 for(const b of plan.boats)s+='<path data-plan-path="'+b.lane+'" d="'+trajectory(b,plan.rank[b.lane],plan)+'" fill="none" stroke="transparent"/>';
 for(const b of plan.boats)s+='<g data-plan-boat="'+b.lane+'"><path d="M-21 -5 L-32 0 L-21 5" stroke="'+color[b.lane-1]+'" stroke-width="2" fill="none"/>'+
 '<path d="M-14 -9 Q -2 -12 14 0 Q -2 12 -14 9Z" fill="'+color[b.lane-1]+'" stroke="#071e2b" stroke-width="1"/>'+
 '<text x="-3" y="4" fill="'+font[b.lane-1]+'" font-size="11" font-weight="900" text-anchor="middle">'+b.lane+'</text></g>';
 return s+'</svg>';
}
function animationHTML(r){
 if(list(r).length!==6||api.options(r).length===0)return '<section class="card card-pad">展開試算に必要な出走データ・買い目がありません。</section>';
 const p=analyze(r,defaults(r));const sample=api.options(r)[0];
 return '<section class="card card-pad boat-sim tactical-preview" data-boat-tactics>'+
 '<div class="section-head"><div><h2 class="section-title">🎬 展開予想・進入編集</h2><p class="boat-sim-mini">進入 → ST → 1マークの攻防 → バック</p></div><span class="boat-sim-tag">試験モデル</span></div>'+
 '<p class="boat-sim-disclaimer">進入変更・スロー／ダッシュ・進入別ST・風波・6艇の攻め方を編集できる。保存済み買い目（例 '+esc(sample)+'）とは別の試算で、実測映像ではありません。</p>'+
 '<div class="tactic-configuration" data-plan-edit>'+drawControls(r,p)+'</div>'+
 '<div class="plan-actions"><button type="button" data-plan-action="reset">↻ 展示・初期隊形に戻す</button><span data-plan-status>端末内の試算／正式予想とは別</span></div>'+
 '<div class="tactic-formation" data-plan-formation></div>'+
 '<div class="boat-sim-water">'+svgHTML(r,p)+'<div class="boat-sim-stage" data-plan-stage>進入 / スタート想定</div></div>'+
 '<div class="boat-sim-phase"><button type="button" data-plan-jump="start">01 進入・スタート</button><button type="button" data-plan-jump="turn">02 1マーク</button><button type="button" data-plan-jump="back">03 バック</button></div>'+
 '<div class="boat-sim-timeline"><input type="range" data-plan-slider min="0" max="1000" value="0" aria-label="航跡アニメ再生位置"/></div>'+
 '<div class="boat-sim-controls"><div class="boat-sim-buttons"><button data-plan-control="play">▶ 再生</button><button data-plan-control="pause">Ⅱ 停止</button><button data-plan-control="reset-play">↺ 最初から</button></div></div>'+
 '<div class="boat-sim-outcome"><strong data-plan-result>'+esc(p.summary)+'</strong></div>'+
 '<p data-plan-story class="boat-sim-story">スタート前の隊形を表示しています。</p>'+
 '<p class="boat-sim-disclaimer">※コース別STは利用可能な独立データ/任意入力のみ。10走未満は小標本扱い。未取得の場合は全国平均ST、どちらも無ければ中立値0.17を使用。展示STのFは加点しません。風と波の影響は未校正の仮説で、予測的中率の保証はありません。変更はこの端末内だけで正式な固定記録・結果照合・収支を変更しません。</p></section>';
}
function dispose(){
 if(mounted&&mounted.raf!=null&&typeof cancelAnimationFrame==='function')cancelAnimationFrame(mounted.raf);
 mounted=null;
 priorDispose();
}
function mount(root,r){
 dispose();
 if(!root||typeof root.querySelector!=='function')return;
 const card=root.querySelector('[data-boat-tactics]');if(!card)return;
 const svg=card.querySelector('svg'),slider=card.querySelector('[data-plan-slider]');
 if(!svg||!slider)return;
 const id='boatlab-tactics|'+(r.sha256||'unfrozen')+'|'+(r.venue||'')+'|'+(r.race||'');
 let cfg=defaults(r);
 try{const saved=JSON.parse(localStorage.getItem(id));if(normalise(saved))cfg=normalise(saved);}catch(_){}
 const paths={},boats={};
 for(let i=1;i<=6;i++){paths[i]=svg.querySelector('[data-plan-path="'+i+'"]');boats[i]=svg.querySelector('[data-plan-boat="'+i+'"]');}
 if(Object.values(paths).some(v=>!v||typeof v.getTotalLength!=='function')||Object.values(boats).some(v=>!v))return;
 const state={cfg,position:0,playing:false,raf:null,last:null};mounted=state;
 function persist(){try{localStorage.setItem(id,JSON.stringify(state.cfg));}catch(_){}
 }
 function repaint(){
  const plan=analyze(r,state.cfg);
  card.querySelector('[data-plan-edit]').innerHTML=drawControls(r,plan);
  const slow=[...plan.boats].filter(b=>b.group==='slow').sort((a,b)=>a.course-b.course).map(b=>b.lane).join('-')||'なし';
  const dash=[...plan.boats].filter(b=>b.group==='dash').sort((a,b)=>a.course-b.course).map(b=>b.lane).join('-')||'なし';
  card.querySelector('[data-plan-formation]').textContent='スロー：'+slow+'　／　ダッシュ：'+dash+'（数字は艇番、進入順）';
  card.querySelector('[data-plan-result]').textContent=plan.summary;
  card.querySelector('[data-plan-story]').textContent=plan.note+' ST：'+plan.boats.map(b=>b.lane+'号艇 '+b.st.toFixed(2)+' ['+b.origin+']').join(' / ');
  plan.boats.forEach(b=>paths[b.lane].setAttribute('d',trajectory(b,plan.rank[b.lane],plan)));
  const mark=svg.querySelector('[data-plan-mark="1"]'),label=svg.querySelector('[data-plan-mark-label="1"]');
  if(mark)mark.setAttribute('cy',String(plan.geometry.markY));
  if(label)label.setAttribute('y',String(plan.geometry.markY-3));
  paint();
 }
 function paint(){
  const t=clamp(state.position,0,1);
  for(let i=1;i<=6;i++){
   const p=paths[i],len=p.getTotalLength(),pos=p.getPointAtLength(t*len);
   const a=p.getPointAtLength(Math.max(0,t*len-1)),z=p.getPointAtLength(Math.min(len,t*len+1));
   const d=Math.atan2(z.y-a.y,z.x-a.x)*180/Math.PI;
   boats[i].setAttribute('transform','translate('+pos.x.toFixed(2)+' '+pos.y.toFixed(2)+') rotate('+d.toFixed(1)+')');
  }
  slider.value=String(Math.round(t*1000));
  card.querySelector('[data-plan-stage]').textContent=t<.40?'START / 進入・スタート':t<.75?'1M / 差し・まくり・まくり差し':'BACK / 試算隊形';
 }
 function pause(){
  state.playing=false;state.last=null;
  if(state.raf!=null&&typeof cancelAnimationFrame==='function')cancelAnimationFrame(state.raf);
  state.raf=null;
 }
 function tick(time){
  if(state!==mounted||!state.playing)return;
  if(state.last!=null)state.position=clamp(state.position+(time-state.last)/8500,0,1);
  state.last=time;paint();
  if(state.position===1){pause();return;}
  state.raf=requestAnimationFrame(tick);
 }
 function play(){if(state.playing)return;if(state.position>=1)state.position=0;state.playing=true;state.last=null;state.raf=requestAnimationFrame(tick);}
 function edit(node){
  const which=node.dataset.planCourse||node.dataset.planGroup||node.dataset.planKind||node.dataset.planSt;
  const env=node.dataset.planEnv;
  if(env){
   if(env==='relativeWind')state.cfg.relativeWind=node.value;
   else{
    const v=n(node.value),limit=env==='wind'?30:env==='wave'?50:100;
    const minimum=(env==='startWidthM'||env==='turn1WidthM')?20:0;
    if(v!==null&&(v<minimum||v>limit))return;
    state.cfg[env]=v;
   }
  }else if(which){
   const b=state.cfg.boats[Number(which)-1];
   if(!b)return;
   if(node.dataset.planCourse){
    const dest=Number(node.value);if(!Number.isInteger(dest)||dest<1||dest>6)return;
    const other=state.cfg.boats.find(x=>x.course===dest);
    if(other&&other!==b)other.course=b.course;
    b.course=dest;
    // A manually-entered course ST does not silently travel to the new course.
    b.st=courseAverage(list(r)[b.lane-1]||{},dest);
    b.stSamples=courseSTCount(list(r)[b.lane-1]||{},dest);
   }else if(node.dataset.planGroup)b.group=node.value==='dash'?'dash':'slow';
   else if(node.dataset.planKind){if(kinds.some(k=>k[0]===node.value))b.kind=node.value;}
   else if(node.dataset.planSt){
    if(node.value!==''&&!validST(node.value))return;
    b.st=node.value===''?null:Number(node.value);
    b.stSamples=null;
   }
  }
  persist();pause();state.position=0;repaint();
  card.querySelector('[data-plan-status]').textContent='編集内容をこの端末に保存（正式買い目は不変）';
 }
 card.addEventListener('change',e=>{
  const el=e.target;if(el&&el.dataset&&(el.dataset.planCourse||el.dataset.planGroup||el.dataset.planKind||el.dataset.planSt||el.dataset.planEnv))edit(el);
 });
 card.addEventListener('click',e=>{
  const el=e.target.closest('[data-plan-action],[data-plan-control],[data-plan-jump]');
  if(!el)return;
  if(el.dataset.planAction==='reset'){pause();state.position=0;state.cfg=defaults(r);try{localStorage.removeItem(id);}catch(_){}
   repaint();card.querySelector('[data-plan-status]').textContent='初期設定に戻しました';return;}
  if(el.dataset.planJump){pause();state.position={start:0,turn:.60,back:.96}[el.dataset.planJump]||0;paint();return;}
  if(el.dataset.planControl==='play')play();
  else if(el.dataset.planControl==='pause')pause();
  else if(el.dataset.planControl==='reset-play'){pause();state.position=0;paint();play();}
 });
 slider.addEventListener('input',()=>{pause();state.position=clamp(Number(slider.value)/1000,0,1);paint();});
 repaint();
}
Object.assign(api,{animationHTML,mount,dispose,tactics:{defaults,normalise,analyze,trajectory,drawControls,directionalHypothesis,windExplanation}});
})();