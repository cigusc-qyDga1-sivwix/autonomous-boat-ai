/* Read-only pie of the displayed snapshot's saved six-way head shares.
 * Relative model scores, not calibrated win probabilities. No engine rerun.
 */
(function(root){
 'use strict';
 const COLORS=['#ffffff','#17212b','#e43e44','#2865d9','#f3d144','#18985a'];
 const INK=['#14263c','#ffffff','#ffffff','#ffffff','#14263c','#ffffff'];
 const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function data(r){
  if(!r||!(/^[a-f0-9]{64}$/i.test(r.sha256||'')))return null;
  const source=r.head_course_shares,boats=r.racers;
  if(!Array.isArray(source)||source.length!==6||!Array.isArray(boats)||boats.length!==6||
     source.some(x=>!x||typeof x!=='object')||boats.some(x=>!x||typeof x!=='object'))return null;
  const rows=[...source].sort((a,b)=>a.lane-b.lane);
  const byLane=new Map(boats.map(b=>[b.lane,b]));
  if(byLane.size!==6||new Set(rows.map(x=>x.course)).size!==6)return null;
  for(let i=0;i<6;i++){
   const x=rows[i],boat=byLane.get(i+1);
   if(x.lane!==i+1||!Number.isInteger(x.course)||x.course<1||x.course>6||!boat||boat.course!==x.course||
      typeof x.relative_share!=='number'||!Number.isFinite(x.relative_share)||x.relative_share<0||x.relative_share>1)return null;
  }
  const total=rows.reduce((n,x)=>n+x.relative_share,0);
  // Existing snapshots round six shares to 4 decimals. Permit that rounding
  // only, never turn arbitrary scores, selected bets or missing rows into rates.
  if(total<=0||Math.abs(total-1)>.001)return null;
  const exact=rows.map(x=>1000*x.relative_share/total),units=exact.map(Math.floor);
  const order=exact.map((x,i)=>({i,remainder:x-units[i]})).sort((a,b)=>b.remainder-a.remainder||a.i-b.i);
  const remaining=1000-units.reduce((a,b)=>a+b,0);
  for(let k=0;k<remaining;k++)units[order[k].i]++;
  return rows.map((x,i)=>({lane:x.lane,course:x.course,name:String(byLane.get(x.lane).name||'選手名未取得'),
   share:x.relative_share/total,percent:units[i]/10,color:COLORS[i],ink:INK[i]}));
 }
 function point(angle,radius=88){return [110+radius*Math.cos(angle),110+radius*Math.sin(angle)];}
 const pos=x=>x.map(n=>n.toFixed(3)).join(' ');
 function render(r){
  const rows=data(r),heading='<h2 class="section-title">1着奪取の相対評価</h2>';
  if(!rows)return '<section class="card card-pad head-share-card">'+heading+'<p class="head-share-empty">保存済みの6艇分の評価を確認できないため、円グラフは表示できません。</p></section>';
  const id='head-share-'+r.sha256.slice(0,16),exhibition=r.phase==='exhibition';
  const state=exhibition?'展示情報反映':'展示前・暫定';
  let angle=-Math.PI/2;
  const paths=[],labels=[];
  for(const x of rows){
   const next=angle+2*Math.PI*x.share,label=x.lane+'号艇 '+x.name+' '+x.percent.toFixed(1)+'％';
   if(x.share>0){
    if(x.share>=1-1e-12)paths.push('<circle cx="110" cy="110" r="88" fill="'+x.color+'"><title>'+esc(label)+'</title></circle>');
    else paths.push('<path d="M 110 110 L '+pos(point(angle))+' A 88 88 0 '+(x.share>.5?1:0)+' 1 '+pos(point(next))+' Z" fill="'+x.color+'" stroke="#8fa1b4" stroke-width="0.8"><title>'+esc(label)+'</title></path>');
    if(x.share>=.10){
     const [lx,ly]=point((angle+next)/2,x.share>=.999?0:60);
     labels.push('<text x="'+lx.toFixed(3)+'" y="'+ly.toFixed(3)+'" text-anchor="middle" dominant-baseline="middle" fill="'+x.ink+'" class="head-share-label">'+x.lane+'号艇</text>');
    }
   }
   angle=next;
  }
  const desc=rows.map(x=>x.lane+'号艇 '+x.name+' '+x.percent.toFixed(1)+'％').join('、');
  const svg='<svg class="head-share-pie" viewBox="0 0 220 220" role="img" aria-labelledby="'+id+'-title '+id+'-desc"><title id="'+id+'-title">'+esc(r.venue)+' '+esc(r.race)+'R 1着候補の相対評価</title><desc id="'+id+'-desc">'+esc(state+'。'+desc+'。実際の1着確率ではありません。')+'</desc>'+paths.join('')+'<circle cx="110" cy="110" r="88" fill="none" stroke="#8fa1b4" stroke-width="1"/>'+labels.join('')+'</svg>';
  const legend=rows.map(x=>'<li><span class="head-share-swatch head-share-lane-'+x.lane+'" aria-hidden="true">'+x.lane+'</span><span class="head-share-person"><b>'+x.lane+'号艇</b><span>'+esc(x.name)+'</span></span><strong class="head-share-percent">'+x.percent.toFixed(1)+'<small>％</small></strong></li>').join('');
  return '<section class="card card-pad head-share-card" data-head-share-chart><div class="head-share-heading">'+heading+'<span class="head-share-state">'+state+'</span></div><p class="head-share-subtitle">1〜6号艇の評価割合 · 合計100％</p><div class="head-share-content">'+svg+'<ol class="head-share-legend" aria-label="各艇の1着相対評価">'+legend+'</ol></div><p class="head-share-note"><strong>実際の1着確率・的中率ではありません。</strong>保存した予想の相対評価を、6艇で100％に換算した試験値です。表示は小数1桁に丸めています。'+(!exhibition?'展示・実進入の確認前の暫定値です。':'')+'</p></section>';
 }
 root.BoatHeadShareChart={data,render};
 if(typeof module!=='undefined')module.exports=root.BoatHeadShareChart;
})(typeof window==='undefined'?globalThis:window);
