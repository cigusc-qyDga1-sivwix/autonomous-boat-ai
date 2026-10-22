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
 function path(lane,rank){
   const begin=164+lane*17,approach=190+lane*8,back=44+rank*17,turnX=551+rank*2,turnY=166+rank*3.3;
   return 'M 108 '+begin+' C 228 '+(begin-4)+' 366 '+approach+' 478 '+approach+
     ' C 534 '+approach+' '+(turnX+21)+' '+(turnY+18)+' '+turnX+' '+turnY+
     ' C '+(turnX-11)+' '+(turnY-43)+' 500 '+back+' 450 '+back+
     ' C 392 '+back+' 306 '+back+' '+(236+rank*16)+' '+back;
 }
 function explanation(combo){
   const p=combo.split('-').map(Number);
   const first=p[0]===1?'①が先マイして逃げる想定':p[0]===2?'②が差し込む想定':
     p[0]<=4?'センター勢が仕掛ける想定':'外側の艇が浮上する想定';
   return first+' → '+p[1]+'号艇が2着 → '+p[2]+'号艇が3着の仮説';
 }
 function glyph(lane){
   const color=colors[lane-1],txt=texts[lane-1];
   return '<g data-sim-boat="'+lane+'" transform="translate(108 '+(164+lane*17)+')">'+
     '<path d="M-21 -6 L-33 0 L-21 6" fill="none" stroke="'+color+'" opacity=".45" stroke-width="2.3"/>'+
     '<path d="M -14 -9 Q -2 -12 14 0 Q -2 12 -14 9 Z" fill="'+color+'" stroke="#082538" stroke-width="1.2"/>'+
     '<text x="-3" y="4" text-anchor="middle" font-size="11" font-weight="900" fill="'+txt+'">'+lane+'</text></g>';
 }
 function animationHTML(r){
   const picks=options(r);
   if(!picks.length)return '<section class="card card-pad">アニメ再生に使える買い目がありません。</section>';
   const combo=picks[0],order=ranks(combo);
   let html='<section class="card card-pad boat-sim" data-boat-sim aria-label="予想展開アニメーション">'+
     '<div class="section-head"><div><h2 class="section-title">🎬 展開予想アニメ</h2><p class="boat-sim-mini">スタート → 第1ターンマーク → バックストレッチ</p></div><span class="boat-sim-tag">模式図</span></div>'+
     '<p class="boat-sim-disclaimer">再現する買い目を選んで、6艇の動きとバック側の予想隊形を確認できるよ。</p>'+
     '<div class="boat-sim-picks" role="group" aria-label="再現する買い目">';
   picks.forEach((pick,i)=>{
     html+='<button type="button" data-sim-pick="'+pick+'" aria-pressed="'+(i===0)+'" class="'+(i===0?'active':'')+'">'+(i===0?'本線':'展開'+(i+1))+' <strong>'+pick+'</strong></button>';
   });
   html+='</div><div class="boat-sim-water"><svg viewBox="0 0 680 315" preserveAspectRatio="xMidYMid meet" role="img" aria-label="六艇がスタートし第一ターンマークを回ってバックストレッチに進む模式図">'+
     '<defs><pattern id="sim-waves" patternUnits="userSpaceOnUse" width="42" height="28"><path d="M0 19 Q 11 13 21 19 T42 19" stroke="#5cb4c8" opacity=".14" fill="none"/></pattern></defs>'+
     '<rect width="680" height="315" fill="#08384e" rx="13"/><rect width="680" height="315" rx="13" fill="url(#sim-waves)"/>'+
     '<path d="M96 164 V276" stroke="#d1f3f8" stroke-width="2.5" stroke-dasharray="8 6"/>'+
     '<text x="62" y="289" fill="#b7e0e8" font-weight="700" font-size="13">START</text>'+
     '<text x="340" y="285" fill="#b7e0e8" text-anchor="middle" font-size="14">スタート → 1M</text>'+
     '<path d="M164 30 H459" stroke="#a3d7e3" stroke-width="1.8" stroke-dasharray="9 6"/>'+
     '<text x="312" y="19" text-anchor="middle" fill="#b7e0e8" font-size="13">← BACK STRETCH</text>'+
     '<circle cx="558" cy="175" r="27" stroke="#f4a541" stroke-width="1.3" stroke-dasharray="4 5" fill="none" opacity=".5"/>'+
     '<circle cx="558" cy="175" r="8" fill="#ffa936" stroke="#fff2ba" stroke-width="2"/>'+
     '<text x="592" y="176" fill="#ffd49b" font-size="14" font-weight="800">1M</text>'+
     '<text x="17" y="29" fill="#bfe4e9" font-size="10" letter-spacing="1.4">BOAT LAB / REPLAY</text>';
   for(let lane=1;lane<=6;lane++)html+='<path data-sim-path="'+lane+'" d="'+path(lane,order[lane])+'" stroke="transparent" fill="none"/>';
   for(let lane=1;lane<=6;lane++)html+=glyph(lane);
   return html+'</svg><div class="boat-sim-stage" data-sim-stage>START / スタート想定</div></div>'+
     '<div class="boat-sim-timeline"><input type="range" data-sim-slider min="0" max="1000" value="0" step="1" aria-label="アニメの再生位置"/>'+
     '<div class="boat-sim-steps"><span>スタート</span><span>1マーク</span><span>バック</span></div></div>'+
     '<div class="boat-sim-controls"><div class="boat-sim-buttons"><button type="button" data-sim-control="play">▶ 再生</button><button type="button" data-sim-control="pause">Ⅱ 一時停止</button><button type="button" data-sim-control="restart">↻ 最初から</button></div><strong data-sim-order>本線：'+combo+'</strong></div>'+
     '<p class="boat-sim-story" data-sim-story>'+explanation(combo)+'</p>'+
     '<p class="boat-sim-disclaimer">※ AIの予想買い目を視覚化する試作アニメ。実際の進入・艇速・ターン角度・航跡を測定したものではありません。固定予想や結果照合は変更しません。</p></section>';
 }
 function dispose(){
   if(current?.raf!==null&&current?.raf!==undefined&&typeof cancelAnimationFrame==='function')cancelAnimationFrame(current.raf);
   current=null;
 }
 function mount(root,r){
   dispose();
   if(!root||typeof root.querySelector!=='function'||typeof requestAnimationFrame!=='function')return;
   const card=root.querySelector('[data-boat-sim]');
   if(!card)return;
   const svg=card.querySelector('svg'),range=card.querySelector('[data-sim-slider]');
   if(!svg||!range)return;
   const paths=[],boats=[];
   for(let i=1;i<=6;i++){paths.push(svg.querySelector('[data-sim-path="'+i+'"]'));boats.push(svg.querySelector('[data-sim-boat="'+i+'"]'));}
   if(paths.some(p=>!p||typeof p.getTotalLength!=='function')||boats.some(b=>!b))return;
   const stage=card.querySelector('[data-sim-stage]'),caption=card.querySelector('[data-sim-story]'),orderLabel=card.querySelector('[data-sim-order]');
   const state={combo:options(r)[0],position:0,running:false,raf:null,last:null};current=state;
   function update(){
     const t=clamp(state.position,0,1);
     paths.forEach((p,i)=>{
       const len=p.getTotalLength(),pos=p.getPointAtLength(t*len);
       const prev=p.getPointAtLength(clamp(t*len-1,0,len)),next=p.getPointAtLength(clamp(t*len+1,0,len));
       const deg=Math.atan2(next.y-prev.y,next.x-prev.x)*180/Math.PI;
       boats[i].setAttribute('transform','translate('+pos.x.toFixed(2)+' '+pos.y.toFixed(2)+') rotate('+deg.toFixed(1)+')');
     });
     range.value=String(Math.round(t*1000));
     stage.textContent=t<.4?'START / スタートの攻防':t<.73?'1M / 第1ターンマーク':'BACK / バック側の想定隊形';
     orderLabel.textContent='予想：'+state.combo;
   }
   function tick(time){
     if(current!==state||!state.running)return;
     if(state.last!==null)state.position=clamp(state.position+(time-state.last)/8500,0,1);
     state.last=time;update();
     if(state.position>=1){state.running=false;state.raf=null;state.last=null;return;}
     state.raf=requestAnimationFrame(tick);
   }
   function pause(){state.running=false;state.last=null;if(state.raf!==null)cancelAnimationFrame(state.raf);state.raf=null;}
   function play(){if(state.running)return;if(state.position>=1)state.position=0;state.running=true;state.last=null;state.raf=requestAnimationFrame(tick);}
   function restart(){pause();state.position=0;update();play();}
   function select(combo){
     if(!options(r).includes(combo))return;
     pause();state.position=0;state.combo=combo;
     const ranksByLane=ranks(combo);
     paths.forEach((p,i)=>p.setAttribute('d',path(i+1,ranksByLane[i+1])));
     card.querySelectorAll('[data-sim-pick]').forEach(btn=>{
       const active=btn.dataset.simPick===combo;btn.classList.toggle('active',active);btn.setAttribute('aria-pressed',String(active));
     });
     caption.textContent=explanation(combo);update();play();
   }
   card.addEventListener('click',e=>{
     const btn=e.target.closest('[data-sim-control],[data-sim-pick]');if(!btn)return;
     if(btn.dataset.simPick){select(btn.dataset.simPick);return;}
     const action=btn.dataset.simControl;
     if(action==='play')play();else if(action==='pause')pause();else if(action==='restart')restart();
   });
   range.addEventListener('input',()=>{pause();state.position=clamp(Number(range.value)/1000,0,1);update();});
   update();
 }
 window.BoatRaceVisual={entryHTML,animationHTML,mount,dispose,ranks,path,options,explanation};
})();
