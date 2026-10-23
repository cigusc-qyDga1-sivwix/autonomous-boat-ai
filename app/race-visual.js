/* BOAT LAB race card and diagrammatic forecast animation.
 * Uses only frozen race information; does not replicate video or physical trajectories.
 * No changes to pre-cutoff tickets. Never interpret schematic movements as observed facts.
 */
(function(){
 'use strict';
 const colors=['#f9fbff','#19212e','#e53d48','#3b7ce7','#e9cc37','#2ab078'];
 const texts=['#183048','#fff','#fff','#fff','#193344','#fff'];
 let current=null;
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const num=v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v))?Number(v):null;
 const valid=v=>typeof v==='string'&&/^[1-6]-[1-6]-[1-6]$/.test(v)&&new Set(v.split('-')).size===3;
 const clamp=(v,a,b)=>Math.min(b,Math.max(a,v));
 function entryHTML(r){
   const racers=Array.isArray(r?.racers)?[...r.racers].sort((a,b)=>Number(a.lane)-Number(b.lane)):[];
   if(racers.length!==6||racers.some((x,i)=>Number(x.lane)!==i+1))
     return '<section class="card card-pad boat-entry"><h2>🚤 出走表</h2><p>出走データ未取得</p></section>';
   let html='<section class="card card-pad boat-entry" aria-label="出走表"><div class="section-head"><h2 class="section-title">🚤 出走表</h2><span>保存時点の情報</span></div><div class="boat-entry-overflow"><table class="boat-entry-table"><thead><tr><th>艇</th><th>選手</th><th>全国勝率</th><th>モーター<br>2連対率</th></tr></thead><tbody>';
   racers.forEach((x,i)=>{
     const win=num(x.national_win_rate),motor=num(x.motor_top_2_percent);
     html+='<tr><th><span class="boat-entry-lane boat-entry-'+(i+1)+'">'+(i+1)+'</span></th><td class="boat-entry-name">'+esc(x.name||'未取得')+'</td><td class="boat-entry-num">'+(win===null?'—':win.toFixed(2))+'</td><td class="boat-entry-num">'+(motor===null?'—':motor.toFixed(1)+'%')+'</td></tr>';
   });
   return html+'</tbody></table></div><p class="boat-sim-disclaimer">全国勝率は得点ベースの指標。モーターは1着率ではなく<strong>2連対率</strong>（1・2着に入った割合）です。</p></section>';
 }
 function options(r){
   const s=new Set(),out=[];
   for(const b of r?.bets||[]){
     if(valid(b.combination)&&!s.has(b.combination)){s.add(b.combination);out.push(b.combination);}
     if(out.length===3)break;
   }
   return out;
 }
 function ranks(combo){
   const top=valid(combo)?combo.split('-').map(Number):[1,2,3];
   const order=top.concat([1,2,3,4,5,6].filter(x=>!top.includes(x)));
   const rank={};order.forEach((x,i)=>rank[x]=i+1);return rank;
 }
 function tacticFor(combo){
   if(!valid(combo))return {id:'escape',label:'逃げ・先マイ'};
   const [head,second]=combo.split('-').map(Number);
   if(head===1)return {id:'escape',label:'逃げ・先マイ'};
   if(head===2)return {id:'sashi',label:'差し'};
   // A head from a centre/outside lane is NOT a proven race tactic.
   // These are selectable strategy hypotheses, not actual confirmed wins.
   if(head===3||head>=5)return {id:'makuri-zashi',label:'まくり差し'};
   if(head===4)return {id:'makuri',label:'まくり'};
   return {id:second<=2?'makuri-zashi':'makuri',label:second<=2?'まくり差し':'まくり'};
 }
 const ROLES={'escape':'先マイ・逃げ狙い','sashi':'差し','makuri':'まくり',
                'makuri-zashi':'まくり差し','follow':'展開待ち'};
 function courseOf(r,lane){
   const x=(r?.racers||[]).find(y=>Number(y.lane)===lane);
   const n=num(x?.course);
   return n!==null&&Number.isInteger(n)&&n>=1&&n<=6?n:lane;
 }
 function rolesFor(combo,r){
   const winner=valid(combo)?Number(combo[0]):1;
   const defaults={1:'escape',2:'sashi',3:'makuri-zashi',4:'makuri',
                   5:'makuri-zashi',6:'follow'};
   return Array.from({length:6},(_,i)=>{
     const lane=i+1,course=courseOf(r,lane);
     let role=defaults[course];
     if(lane===winner && course!==1){
       role=tacticFor(combo).id;
       if(role==='escape')role='sashi';
     }
     return {lane,course,role,label:ROLES[role]};
   });
 }

 // Wide 16:9 schematic. 1M buoy sits at (786,278). All courses turn on
 // the right/outside of the buoy, NOT straight through it. The first course
 // always attempts an inside first turn even if its projected finish is 3rd.
 const MARK={x:786,y:278};
 const SCENE={width:1080,height:608};
 function path(lane,rank,tactic='escape',leader=1,role=null,course=lane){
   const chosen=role||(lane===leader?tactic:
     ({1:'escape',2:'sashi',3:'makuri-zashi',4:'makuri',5:'makuri-zashi',6:'follow'}[course]||'follow'));
   const start=320+course*29;
   const approach=310+course*24;
   const offset=Math.max(0,course-3);
   let outsideX,outsideY,exitX,exitY;
   if(chosen==='escape'){
     // Tight first turn: near the buoy, but always outside its safety circle.
     outsideX=833;outsideY=314;exitX=744;exitY=192;
   }else if(chosen==='sashi'){
     // Arrive behind 1, turn outward then cross into the opening after 1M.
     outsideX=853+Math.max(0,course-2)*3;outsideY=333;
     exitX=729;exitY=186;
   }else if(chosen==='makuri-zashi'){
     outsideX=888+offset*8;outsideY=360+offset*6;
     exitX=748+offset*3;exitY=171;
   }else if(chosen==='makuri'){
     // The whole arc is outside 1M; do not send a makuri boat through buoy.
     outsideX=941+offset*7;outsideY=399+offset*7;
     exitX=776+offset*4;exitY=145;
   }else{
     outsideX=960+offset*8;outsideY=418+offset*9;
     exitX=805+offset*6;exitY=130;
   }
   const backY=70+rank*20;
   const farther=chosen==='makuri'||chosen==='follow';
   const startX=104,entryX=705+Math.min(0,course-1)*5;
   const bend=farther?32:21;
   return 'M'+startX+' '+start+
     ' C268 '+(start+2)+' 548 '+(approach+8)+' '+entryX+' '+approach+
     ' C766 '+approach+' '+(outsideX+27)+' '+(outsideY+31)+' '+outsideX+' '+outsideY+
     ' C'+(outsideX+bend)+' '+(outsideY-65)+' '+(exitX+48)+' '+(exitY+18)+' '+exitX+' '+exitY+
     ' C625 '+backY+' 377 '+backY+' '+(165+rank*14)+' '+backY;
 }
 function studyOptions(r){
   // Static counterfactuals for understanding alternative wins; NEVER added
   // to tickets and NEVER interpreted as evidence of an observed outcome.
   const byCourse={};
   for(let lane=1;lane<=6;lane++)byCourse[courseOf(r,lane)]=lane;
   const inside=byCourse[1],sashi=byCourse[2],center=byCourse[3];
   return [
     {combo:inside+'-'+sashi+'-'+center,label:'逃げ成立'},
     {combo:sashi+'-'+inside+'-'+center,label:'差し成立'},
     {combo:center+'-'+sashi+'-'+inside,label:'まくり差し成立'},
   ].filter(x=>valid(x.combo));
 }
 function choices(r){
   return [...options(r).map(combo=>({combo,kind:'forecast'})),
     ...studyOptions(r).filter(x=>!options(r).includes(x.combo)).map(x=>({...x,kind:'study'}))];
 }
 function explanation(combo,r){
   if(!valid(combo))return '展開情報が不足しています';
   const [a,b,c]=combo.split('-').map(Number),roles=rolesFor(combo,r);
   const inside=roles.find(x=>x.course===1);
   return inside.lane+'号艇が先マイで逃げを狙い、'+a+'号艇の'+roles[a-1].label+
      'が成立する仮説 → '+b+'号艇が2着 → '+c+'号艇が3着に残る想定';
 }
 function stageTexts(combo,r){
   if(!valid(combo))return ['スタートの攻防','1Mのターン','バックでの予想隊形'];
   const [a,b,c]=combo.split('-').map(Number),roles=rolesFor(combo,r);
   const inside=roles.find(x=>x.course===1);
   return [
     inside.lane+'号艇が1Mの先マイを狙う。2〜6コースは差し・まくり・まくり差し等を選ぶ仮説。展示STを本番STとみなさない。',
     '1M：'+inside.lane+'号艇の先マイに対し、'+a+'号艇が'+roles[a-1].label+
       'で攻める仮説。差し場・艇間は映像で未検証。',
     'バック：'+a+'–'+b+'–'+c+'を仮配置。実際の動きや4〜6番手を確定するアニメではない。'
   ];
 }
 function glyph(lane){
   const color=colors[lane-1],txt=texts[lane-1];
   return '<g data-sim-boat="'+lane+'" transform="translate(108 '+(164+lane*17)+')">'+
     '<path d="M-25 -7 L-54 -10 M-25 7 L-54 10" fill="none" stroke="'+color+'" opacity=".45" stroke-width="2.3"/>'+
     '<path d="M -25 -12 Q -1 -17 24 0 Q -1 17 -25 12 Z" fill="'+color+'" stroke="#082538" stroke-width="1.2"/>'+
     '<text x="0" y="5" text-anchor="middle" font-size="16" font-weight="900" fill="'+txt+'">'+lane+'</text></g>';
 }
 function animationHTML(r){
   const picks=options(r);
   if(!picks.length)return '<section class="card card-pad">アニメ再生に使える買い目がありません。</section>';
   const combo=picks[0],order=ranks(combo),tactic=tacticFor(combo),roles=rolesFor(combo,r);
   let html='<section class="card card-pad boat-sim boat-sim-v3 boat-sim-v4" data-boat-sim aria-label="予想展開アニメーション">'+
     '<div class="section-head"><div><h2 class="section-title">🎬 展開予想アニメ</h2><p class="boat-sim-mini">スタート → 第1ターンマーク → バックストレッチ</p></div><span class="boat-sim-tag">戦法別 v4</span></div>'+
     '<div class="boat-sim-narrative"><span>想定する攻め方 <b data-sim-tactic>'+tactic.label+'</b></span><strong data-sim-forecast>予想着順 '+combo+'</strong></div>'+
     '<p class="boat-sim-disclaimer">本線・対抗の買い目に加え、非購入の比較用展開も切り替えられるよ。各艇が独立して先マイ／差し／まくり／まくり差しを狙う仮説を描く。実際の進入や艇間の航跡・速度を再現したものではありません。艇の戦法と、1Mの外を回る位置関係を比較する模式図です。</p>'+
     '<div class="boat-sim-roles" data-sim-roles aria-label="各艇の攻め方の仮説">'+roles.map(x=>'<span>'+x.lane+'号艇('+x.course+'コース)：'+esc(x.label)+'</span>').join('')+'</div>'+
     '<div class="boat-sim-picks" role="group" aria-label="再現する買い目">';
   picks.forEach((pick,i)=>{
     html+='<button type="button" data-sim-pick="'+pick+'" data-sim-kind="forecast" aria-pressed="'+(i===0)+'" class="'+(i===0?'active':'')+'">'+(i===0?'本線':'展開'+(i+1))+' <strong>'+pick+'</strong></button>';
   });
   const extras=studyOptions(r).filter(x=>!picks.includes(x.combo));
   html+='</div><div class="boat-sim-study"><span>展開比較（買い目には含まれません）</span><div role="group" aria-label="未購入の比較用シナリオ">';
   extras.forEach(x=>{html+='<button type="button" data-sim-pick="'+x.combo+'" data-sim-kind="study" aria-pressed="false">'+esc(x.label)+' <strong>'+x.combo+'</strong></button>';});
   html+='</div></div><div class="boat-sim-picks-exit">';
   html+='</div><div class="boat-sim-water"><svg viewBox="0 0 1080 608" preserveAspectRatio="xMidYMid meet" role="img" aria-label="6艇が1マークの外を回る戦法別アニメーション">'+
     '<defs><linearGradient id="sim-water-shade" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#09546c"/><stop offset="1" stop-color="#052c43"/></linearGradient><pattern id="sim-waves" patternUnits="userSpaceOnUse" width="54" height="30"><path d="M0 17 Q13 9 27 17 T54 17" stroke="#67b8c9" opacity=".15" fill="none"/></pattern></defs>'+
     '<rect width="1080" height="608" fill="url(#sim-water-shade)" rx="13"/><rect width="1080" height="608" fill="url(#sim-waves)" rx="13"/>'+
     '<path d="M108 315 V552" stroke="#d1f3f8" stroke-width="3" stroke-dasharray="10 8"/>'+
     '<text x="115" y="579" fill="#b7e0e8" font-weight="700" font-size="21">START →</text>'+
     '<path d="M102 108 H708" stroke="#a3d7e3" stroke-width="2.5" stroke-dasharray="13 10"/>'+
     '<text x="375" y="83" text-anchor="middle" fill="#b7e0e8" font-size="21">← BACK STRETCH</text>'+
     '<circle cx="786" cy="278" r="46" stroke="#f4a541" stroke-width="2.0" stroke-dasharray="7 8" fill="none" opacity=".65"/>'+
     '<circle cx="786" cy="278" r="13" fill="#ffa936" stroke="#fff2ba" stroke-width="3"/>'+
     '<text x="774" y="214" fill="#ffd49b" font-size="22" font-weight="800">1M</text>'+
     '<text x="26" y="37" fill="#bfe4e9" font-size="15" letter-spacing="1.4">BOAT LAB / TACTICAL REPLAY v4</text>';
   // Each registered boat follows its own scenario-specific Bezier path.
   for(let lane=1;lane<=6;lane++)html+='<path data-sim-path="'+lane+'" d="'+path(lane,order[lane],tactic.id,Number(combo[0]),roles[lane-1].role,roles[lane-1].course)+'" stroke="transparent" fill="none"/>'+
   '<path data-sim-trail="'+lane+'" d="'+path(lane,order[lane],tactic.id,Number(combo[0]),roles[lane-1].role,roles[lane-1].course)+'" stroke="'+colors[lane-1]+'" opacity="'+(lane<=3?'.40':'.23')+'" stroke-width="2.6" stroke-dasharray="8 12" fill="none"/>';
   for(let lane=1;lane<=6;lane++)html+=glyph(lane);
   return html+'</svg><div class="boat-sim-stage" data-sim-stage>START / スタート想定</div></div>'+
     '<div class="boat-sim-phase" role="group" aria-label="アニメの場面に移動">'+
     '<button type="button" data-sim-jump="start" class="active" aria-pressed="true"><small>01</small> スタート</button>'+
     '<button type="button" data-sim-jump="turn" aria-pressed="false"><small>02</small> 第1ターンマーク</button>'+
     '<button type="button" data-sim-jump="back" aria-pressed="false"><small>03</small> バック</button>'+
     '</div>'+
     '<div class="boat-sim-timeline"><input type="range" data-sim-slider min="0" max="1000" value="0" step="1" aria-label="アニメの再生位置"/>'+
     '<div class="boat-sim-steps"><span>スタート</span><span>1マーク</span><span>バック</span></div></div>'+
     '<div class="boat-sim-controls"><div class="boat-sim-buttons"><button type="button" data-sim-control="play">▶ 再生</button><button type="button" data-sim-control="pause">Ⅱ 一時停止</button><button type="button" data-sim-control="restart">↻ 最初から</button></div>'+
     '<div class="boat-sim-speeds" role="group" aria-label="アニメ再生速度"><span>速度</span>'+
     '<button type="button" data-sim-speed="0.5" aria-pressed="false">0.5×</button>'+
     '<button type="button" data-sim-speed="1" aria-pressed="true" class="active">1×</button>'+
     '<button type="button" data-sim-speed="1.5" aria-pressed="false">1.5×</button></div>'+
     '</div>'+
     '<div class="boat-sim-outcome"><span>バック想定</span><strong data-sim-order>'+combo+'</strong><span>1着 → 2着 → 3着</span></div>'+
     '<p class="boat-sim-story" aria-live="polite" data-sim-story>'+stageTexts(combo,r)[0]+'</p>'+
     '<p class="boat-sim-disclaimer">※ 予想済み3連単の「どういう形でそうなるか」を表す<strong>説明用アニメ</strong>。艇速や実際のターン軌道を予測する計算、展示動画解析は未実装です。4〜6番手の表示は便宜上の隊列です。元の固定買い目や結果照合は変更しません。</p></section>';
 }
 function dispose(){
   if(current?.raf!==null&&current?.raf!==undefined&&typeof cancelAnimationFrame==='function')cancelAnimationFrame(current.raf);
   current=null;
 }
 function mount(root,r){
   dispose();
   if(!root||typeof root.querySelector!=='function'||typeof requestAnimationFrame!=='function')return;
   const card=root.querySelector('[data-boat-sim]');if(!card)return;
   const svg=card.querySelector('svg'),range=card.querySelector('[data-sim-slider]');
   if(!svg||!range)return;
   const paths=[],boats=[],trails=[];
   for(let i=1;i<=6;i++){
     paths.push(svg.querySelector('[data-sim-path="'+i+'"]'));
     boats.push(svg.querySelector('[data-sim-boat="'+i+'"]'));
     trails.push(svg.querySelector('[data-sim-trail="'+i+'"]'));
   }
   if(paths.some(p=>!p||typeof p.getTotalLength!=='function')||boats.some(b=>!b))return;
   const stage=card.querySelector('[data-sim-stage]'),caption=card.querySelector('[data-sim-story]');
   const orderLabel=card.querySelector('[data-sim-order]'),tacticLabel=card.querySelector('[data-sim-tactic]');
   const forecastLabel=card.querySelector('[data-sim-forecast]');
   const state={combo:options(r)[0],position:0,running:false,raf:null,last:null,speed:1};
   current=state;
   function phaseIndex(t){return t<.4?0:t<.73?1:2;}
   function update(){
     const t=clamp(state.position,0,1);
     const projected=ranks(state.combo);
     paths.forEach((p,i)=>{
       const len=p.getTotalLength();
       // Highlight a possible overtake only *after* 1M: no fictitious
       // instant jump at the start; no inference from actual race results.
       const edge=t>.56?(t-.56)/.44:0;
       const leadOffset=edge*(7-projected[i+1])*.010;
       const progress=clamp(t+leadOffset,0,1);
       const pos=p.getPointAtLength(progress*len);
       const prev=p.getPointAtLength(clamp(progress*len-2,0,len)),
             next=p.getPointAtLength(clamp(progress*len+2,0,len));
       const deg=Math.atan2(next.y-prev.y,next.x-prev.x)*180/Math.PI;
       boats[i].setAttribute('transform','translate('+pos.x.toFixed(2)+' '+pos.y.toFixed(2)+') rotate('+deg.toFixed(1)+')');
     });
     range.value=String(Math.round(t*1000));
     const phase=phaseIndex(t);
     stage.textContent=['START / スタートの攻防','1M / 第1ターンマーク','BACK / バック側の想定隊形'][phase];
     orderLabel.textContent='予想：'+state.combo;
     caption.textContent=stageTexts(state.combo,r)[phase];
     const phaseButtons=card.querySelectorAll('[data-sim-jump]');
     if(phaseButtons)phaseButtons.forEach(button=>{
       const selected=button.dataset.simJump===['start','turn','back'][phase];
       button.classList.toggle('active',selected);button.setAttribute('aria-pressed',String(selected));
     });
   }
   function tick(time){
     if(current!==state||!state.running)return;
     if(state.last!==null)state.position=clamp(state.position+(time-state.last)/8500*state.speed,0,1);
     state.last=time;update();
     if(state.position>=1){state.running=false;state.raf=null;state.last=null;return;}
     state.raf=requestAnimationFrame(tick);
   }
   function pause(){
     state.running=false;state.last=null;
     if(state.raf!==null&&typeof cancelAnimationFrame==='function')cancelAnimationFrame(state.raf);
     state.raf=null;
   }
   function play(){
     if(state.running)return;
     if(state.position>=1)state.position=0;
     state.running=true;state.last=null;state.raf=requestAnimationFrame(tick);
   }
   function restart(){pause();state.position=0;update();play();}
   function select(combo){
     const selectedChoice=choices(r).find(x=>x.combo===combo);
     if(!selectedChoice)return;
     pause();state.position=0;state.combo=combo;
     const ranking=ranks(combo),tactic=tacticFor(combo),roles=rolesFor(combo,r);
     paths.forEach((p,i)=>{
       const curve=path(i+1,ranking[i+1],tactic.id,Number(combo[0]),roles[i].role,roles[i].course);
       p.setAttribute('d',curve);
       if(trails[i])trails[i].setAttribute('d',curve);
     });
     card.querySelectorAll('[data-sim-pick]').forEach(button=>{
       const selected=button.dataset.simPick===combo;
       button.classList.toggle('active',selected);button.setAttribute('aria-pressed',String(selected));
     });
     const roleLegend=card.querySelector('[data-sim-roles]');
    if(roleLegend)roleLegend.innerHTML=roles.map(x=>'<span>'+x.lane+'号艇('+x.course+'コース)：'+esc(x.label)+'</span>').join('');
    if(tacticLabel)tacticLabel.textContent=tactic.label;
     if(forecastLabel)forecastLabel.textContent=
       selectedChoice.kind==='study'?'比較用（未購入） '+combo:'予想着順 '+combo;
     update();play();
   }
   function jump(phase){
     const progress={start:0,turn:.60,back:.96}[phase];
     if(progress===undefined)return;
     pause();state.position=progress;update();
   }
   function speed(value){
     const v=Number(value);if(![.5,1,1.5].includes(v))return;
     state.speed=v;state.last=null;
     const buttons=card.querySelectorAll('[data-sim-speed]');
     if(buttons)buttons.forEach(button=>{
       const selected=Number(button.dataset.simSpeed)===v;
       button.classList.toggle('active',selected);button.setAttribute('aria-pressed',String(selected));
     });
   }
   card.addEventListener('click',event=>{
     const button=event.target.closest('[data-sim-control],[data-sim-pick],[data-sim-jump],[data-sim-speed]');
     if(!button)return;
     if(button.dataset.simPick){select(button.dataset.simPick);return;}
     if(button.dataset.simJump){jump(button.dataset.simJump);return;}
     if(button.dataset.simSpeed){speed(button.dataset.simSpeed);return;}
     const action=button.dataset.simControl;
     if(action==='play')play();
     else if(action==='pause')pause();
     else if(action==='restart')restart();
   });
   range.addEventListener('input',()=>{pause();state.position=clamp(Number(range.value)/1000,0,1);update();});
   update();
 }
 window.BoatRaceVisual={entryHTML,animationHTML,mount,dispose,ranks,path,options,studyOptions,choices,explanation,tacticFor,rolesFor,stageTexts,MARK,SCENE};
})();
