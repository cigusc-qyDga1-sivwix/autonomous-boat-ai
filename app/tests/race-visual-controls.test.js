const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const fixture=JSON.parse(fs.readFileSync('app/data/live/latest.json','utf8'));
const race=fixture.forecast_races.find(r=>r.bets.length>=2);
let callback=null,nextId=1,cancelled=0;
const requests=[];
const fakePath=()=>({d:'',getTotalLength(){return 1000},
 getPointAtLength(n){return {x:n/2,y:260-n/6}},
 setAttribute(k,v){if(k==='d')this.d=v}});
const paths=Array.from({length:6},fakePath);
const boats=Array.from({length:6},()=>({
 transform:'',setAttribute(k,v){if(k==='transform')this.transform=v}
}));
const buttons=Array.from({length:3},(_,i)=>({
 dataset:{simPick:race.bets[i].combination,simKind:'forecast'},
 classList:{toggle(){}},setAttribute(k,v){if(k==='aria-pressed')this.pressed=v}
}));
let clickHandler=null,inputHandler=null;
const slider={value:'0',addEventListener:(event,handler)=>{if(event==='input')inputHandler=handler}};
const stage={textContent:''},caption={textContent:''},result={textContent:''},tactic={textContent:''},forecast={textContent:''};
const wakeLabel={textContent:''},wakeButton={dataset:{simWakeToggle:''},pressed:'true',textContent:'',setAttribute(k,v){if(k==='aria-pressed')this.pressed=v}},wakeLayer={style:{display:'none'}};
const stages=['start','turn','back'].map(simJump=>({dataset:{simJump},classList:{toggle(){}},setAttribute(k,v){if(k==='aria-pressed')this.pressed=v}}));
const speedBtns=[.5,1,1.5].map(simSpeed=>({dataset:{simSpeed:String(simSpeed)},classList:{toggle(){}},setAttribute(k,v){if(k==='aria-pressed')this.pressed=v}}));
const svg={querySelector(query){
 const m=query.match(/\[data-sim-(?:path|boat)="(\d)"\]/);
 if(!m)return null;
 return query.includes('path')?paths[Number(m[1])-1]:boats[Number(m[1])-1];
}};
const card={
 querySelector(selector){
  if(selector==='svg')return svg;
  if(selector==='[data-sim-slider]')return slider;
  if(selector==='[data-sim-stage]')return stage;
  if(selector==='[data-sim-story]')return caption;
  if(selector==='[data-sim-order]')return result;
  if(selector==='[data-sim-tactic]')return tactic;
  if(selector==='[data-sim-forecast]')return forecast;
   if(selector==='[data-sim-wake-info]')return wakeLabel;
   if(selector==='[data-sim-wake-toggle]')return wakeButton;
   if(selector==='[data-sim-wake]')return wakeLayer;
  return null;
 },
 querySelectorAll:(selector)=>selector==='[data-sim-pick]'?buttons:selector==='[data-sim-jump]'?stages:selector==='[data-sim-speed]'?speedBtns:[],
 addEventListener:(ev,fn)=>{if(ev==='click')clickHandler=fn}
};
const root={querySelector:q=>q==='[data-boat-sim]'?card:null};
const win={};
const context=vm.createContext({
 window:win,Number,Intl,
 requestAnimationFrame:cb=>{callback=cb;requests.push(cb);return nextId++},
 cancelAnimationFrame:id=>{cancelled++;callback=null}
});
vm.runInContext(fs.readFileSync('app/wake-study.js','utf8'),context);
vm.runInContext(fs.readFileSync('app/race-visual.js','utf8'),context);
const visual=win.BoatRaceVisual;
visual.mount(root,race);
assert.equal(stage.textContent,'START / スタートの攻防');
assert.equal(slider.value,'0');
assert.match(wakeLabel.textContent,/🌀 ON/,'all races start with wake research ON');
assert.match(boats[0].transform,/translate/);
function actionNode(node){clickHandler({target:{closest:()=>node}})}
function action(control,pick){
 const node=pick?{dataset:{simPick:pick,simKind:'forecast'}}:{dataset:{simControl:control}};
 actionNode(node);
}
action('play');
assert.equal(typeof callback,'function');
let frame=callback;frame(1000);
frame=callback;frame(4500);
assert.equal(stage.textContent,'1M / 第1ターンマーク');
assert.ok(Number(slider.value)>0);
action('pause');
assert.ok(cancelled>0);
slider.value='950';inputHandler();
assert.match(stage.textContent,/BACK/);
action('restart');
assert.equal(slider.value,'0');
assert.equal(typeof callback,'function');
const other=race.bets[1].combination;
action('pause');
action('',other);
assert.equal(paths[0].d,visual.path(1,visual.ranks(other)[1],visual.tacticFor(other).id,Number(other[0])));
assert.match(caption.textContent,/仮説/);
assert.equal(buttons[1].pressed,'true');
assert.match(wakeLabel.textContent,/🌀 ON/,'scenario changes keep wake ON');
assert.equal(result.textContent,(visual.tacticalOptions(race).length?'表示中：':'予想：')+other);
assert.equal(tactic.textContent,visual.tacticFor(other).label);
assert.equal(forecast.textContent,'元の固定予想 '+other);
actionNode(wakeButton);
assert.equal(wakeButton.pressed,'false');
assert.match(wakeLabel.textContent,/OFF/);
action('',race.bets[0].combination);
assert.match(wakeLabel.textContent,/OFF/,'switching back keeps manual OFF');
actionNode(wakeButton);
assert.equal(wakeButton.pressed,'true');
assert.match(wakeLabel.textContent,/🌀 ON/);
actionNode({dataset:{simJump:'turn'}});
assert.match(stage.textContent,/1M/);
assert.equal(stages[1].pressed,'true');
actionNode({dataset:{simJump:'back'}});
assert.match(stage.textContent,/BACK/);
assert.equal(stages[2].pressed,'true');
actionNode({dataset:{simSpeed:'1.5'}});
assert.equal(speedBtns[2].pressed,'true');
actionNode({dataset:{simJump:'start'}});
assert.match(stage.textContent,/START/);
assert.equal(slider.value,'0');
action('play');
const accelerated=callback;
accelerated(9000);
const next=callback;
next(10500);
assert.ok(Number(slider.value)>200,'speed 1.5 should advance faster than normal');
action('pause');
visual.dispose();
assert.equal(typeof callback,'object');
console.log('BOAT LAB animated replay controls: PASS');
