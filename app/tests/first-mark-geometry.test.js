const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const window={};
vm.runInNewContext(fs.readFileSync('app/race-visual.js','utf8'),{window,Number,Intl});
const V=window.BoatRaceVisual;
const buoy=V.MARK;
assert.equal(buoy.x,786);assert.equal(buoy.y,278);
assert.equal(V.SCENE.width,1080);
assert.equal(V.SCENE.height,608);
assert.equal(V.tacticFor('3-2-1').id,'makuri-zashi');
const r={
  racers:Array.from({length:6},(_,i)=>({lane:i+1,course:i+1,name:'選手'+(i+1)})),
  bets:[{combination:'1-3-2',virtual_yen:25000},
        {combination:'2-1-3',virtual_yen:15000},
        {combination:'3-2-1',virtual_yen:10000}]
};
const pre=JSON.stringify(r);
const combinations=['1-3-2','2-1-3','3-2-1'];
for(const comb of combinations) {
 const roles=V.rolesFor(comb,r),rank=V.ranks(comb);
 assert.equal(roles[0].role,'escape','1 must seek inside first turn even when not winner');
 for(let i=1;i<=6;i++){
   const d=V.path(i,rank[i],V.tacticFor(comb).id,Number(comb[0]),roles[i-1].role,i);
   assert.match(d,/^M\d+/);
   const values=[...d.matchAll(/-?\d+(?:\.\d+)?/g)].map(m=>Number(m[0]));
   assert.equal(values.length,20,'1 move + 3 cubic segments');
   const pts=[[values[0],values[1]]];
   function bezier(a,b,c,d,t){const q=1-t;return q*q*q*a+3*q*q*t*b+3*q*t*t*c+t*t*t*d}
   for(let seg=0;seg<3;seg++){
     const ix=2+seg*6;
     const p0=pts.at(-1),p1=values.slice(ix,ix+2),
           p2=values.slice(ix+2,ix+4),p3=values.slice(ix+4,ix+6);
     for(let step=0;step<=100;step++){
       const t=step/100;
       const x=bezier(p0[0],p1[0],p2[0],p3[0],t),
             y=bezier(p0[1],p1[1],p2[1],p3[1],t);
       assert.ok(x>=0&&x<=1080&&y>=0&&y<=608,comb+' lane '+i+' offscene ('+x+','+y+')');
       const near=Math.hypot(x-buoy.x,y-buoy.y);
       assert.ok(near>=30,comb+' lane '+i+' passed too close to 1M ('+near.toFixed(1)+')');
     }
     pts.push(p3);
   }
 }
}
const html=V.animationHTML(r);
assert.match(html,/viewBox="0 0 1080 608"/);
assert.equal((html.match(/data-sim-path="/g)||[]).length,6);
assert.equal((html.match(/data-sim-trail="/g)||[]).length,6);
assert.match(html,/展開比較/);
assert.match(html,/買い目には含まれません/);
assert.equal(JSON.stringify(r),pre,'simulation must not edit frozen tickets');
const oneOnly={racers:r.racers,bets:[r.bets[0]]};
const choices=V.choices(oneOnly);
assert.ok(choices.some(x=>x.combo==='3-2-1'&&x.kind==='study'));
assert.ok(choices.some(x=>x.combo==='1-3-2'&&x.kind==='forecast'));
console.log('Tactical 16:9 six-boat buoy clearance and untouched bets: PASS');
