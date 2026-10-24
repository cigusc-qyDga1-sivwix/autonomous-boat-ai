'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const data=JSON.parse(fs.readFileSync('app/data/live/latest.json','utf8'));
const mainEvents={};
const elements=new Map();
for(const id of ['main','breadcrumb-label','reload-btn','toast']){
 elements.set(id,{
  innerHTML:'',textContent:'',
  classList:{add(){},remove(){},toggle(){}},
  addEventListener(name,fn){if(id==='main')(mainEvents[name]||=[]).push(fn);},
  setAttribute(){},removeAttribute(){}
 });
}
const listeners={};
const document={hidden:false,
 getElementById:id=>elements.get(id),
 querySelectorAll:()=>[],
 addEventListener:(name,cb)=>{(listeners[name]||=[]).push(cb);}
};
const localStorage={getItem:()=>null,setItem(){},removeItem(){}};
const window={scrollTo(){}};
const context=vm.createContext({window,document,localStorage,
 fetch:async()=>({ok:true,json:async()=>data}),
 navigator:{},location:{protocol:'file:'},
 setTimeout,clearTimeout,console,Blob,URL,Date,Intl});
vm.runInContext(fs.readFileSync('app/mobile-race-nav.js','utf8'),context);
vm.runInContext(fs.readFileSync('app/race-visual.js','utf8'),context);
vm.runInContext(fs.readFileSync('app/venue-board.js','utf8'),context);
vm.runInContext(fs.readFileSync('app/app.js','utf8'),context);
const nav=window.BoatMobileRaceNav;
const forecast=[{venue:'鳴門',race:1},{venue:'鳴門',race:3},{venue:'鳴門',race:12}];
const picker=nav.racePicker('鳴門',3,forecast,[{venue:'鳴門',race:2}]);
assert.equal((picker.match(/data-select-race="/g)||[]).length,12);
assert.equal((picker.match(/data-select-race="鳴門\|/g)||[]).length,12);
assert.equal((picker.match(/data-select-race="鳴門\|3" aria-current="true"/g)||[]).length,1);
assert.match(picker,/data-select-race="鳴門\|2" disabled/,'unfixed race disabled');
assert.equal((picker.match(/class="venue-race-choice[^"]*" data-select-race=/g)||[]).length,12);
assert.equal((picker.match(/class="venue-race-choice[^"]*is-unavailable/g)||[]).length,9);
assert.match(picker,/未固定/);
assert.doesNotMatch(picker,/3連単|50,000円/,'never fabricate missing tickets');
const htmlEscape=nav.racePicker('A"<>',1,[{venue:'A"<>',race:1}]);
assert.match(htmlEscape,/A&amp;quot;|A&quot;/);
assert.doesNotMatch(htmlEscape,/data-select-race="A"<>/);
const start={x:330,y:210,time:0,fingers:1,exclude:false};
const end={x:185,y:218,time:400,fingers:1,exclude:false};
assert.equal(nav.decideSwipe(start,end),true,'left swipe is back');
assert.equal(nav.decideSwipe(start,{...end,x:470}),false,'right is not back');
assert.equal(nav.decideSwipe(start,{...end,y:340}),false,'vertical drag preserved');
assert.equal(nav.decideSwipe(start,{...end,time:800}),false,'long horizontal gesture ignored');
assert.equal(nav.decideSwipe({...start,fingers:2},end),false,'pinch ignored');
assert.equal(nav.decideSwipe({...start,exclude:true},end),false,'tables excluded');
assert.equal(nav.shouldIgnore({closest:s=>s.includes('button')?{}:null,parentElement:null}),true);
assert.equal(nav.shouldIgnore({closest:s=>s.includes('.tablewrap')?{}:null,parentElement:null}),true);
assert.equal(nav.shouldIgnore({closest:()=>null,clientWidth:100,scrollWidth:400,parentElement:null}),true);
assert.equal(nav.shouldIgnore({closest:()=>null,parentElement:null}),false);
function click(selector,node){
 const target={closest:s=>s===selector?node:null};
 for(const cb of listeners.click||[])cb({target});
}
function swipe(fromX=345,toX=185,target={closest:()=>null,parentElement:null}){
 const send=(name,x,y=190)=>{for(const cb of mainEvents[name]||[]){
  cb({target,touches:name==='touchstart'?[{clientX:x,clientY:y}]:[],
   changedTouches:[{clientX:x,clientY:y}]});
 }};
 send('touchstart',fromX);
 send('touchend',toX);
}
setTimeout(()=>{
 const main=elements.get('main');
 assert.match(main.innerHTML,/今日の開催一覧/);
 assert.ok(mainEvents.touchstart?.length===1&&mainEvents.touchend?.length===1,
  'native left swipe handler installed on main exactly once');
 const counts=new Map();
 for(const r of data.forecast_races)counts.set(r.venue,(counts.get(r.venue)||0)+1);
 const venue=[...counts].find(([,n])=>n>=2)?.[0]||data.forecast_races[0].venue;
 const entries=data.forecast_races.filter(x=>x.venue===venue).sort((a,b)=>a.race-b.race);
 const first=entries[0],second=entries[1]||entries[0];
 click('[data-open-venue]',{dataset:{openVenue:venue},disabled:false});
 assert.match(main.innerHTML,/全12R/);
 assert.equal((main.innerHTML.match(/data-select-race="/g)||[]).length,12,
   'venue-level picker covers 1–12R');
 click('[data-select-race]',{dataset:{selectRace:venue+'|'+first.race},disabled:false});
 assert.match(main.innerHTML,/3連単フォーメーション/);
 assert.equal((main.innerHTML.match(/data-select-race="/g)||[]).length,12,
   'race detail also has 1–12R picker');
 assert.match(main.innerHTML,new RegExp('data-select-race="'+venue+'\\|'+first.race+'" aria-current="true"'));
 if(second!==first){
  click('[data-select-race]',{dataset:{selectRace:venue+'|'+second.race},disabled:false});
  assert.match(main.innerHTML,new RegExp('data-select-race="'+venue+'\\|'+second.race+'" aria-current="true"'));
  swipe();
  assert.match(main.innerHTML,new RegExp('data-select-race="'+venue+'\\|'+first.race+'" aria-current="true"'),
   'swipe back from second race returns to previously viewed first race');
 }
 const unchanged=main.innerHTML;
 swipe(345,180,{closest:s=>s.includes('button')?{}:null,parentElement:null});
 assert.equal(main.innerHTML,unchanged,'horizontal gestures on controls do not leave detail');
 swipe(345,180,{closest:s=>s.includes('.tablewrap')?{}:null,parentElement:null});
 assert.equal(main.innerHTML,unchanged,'horizontal table scrolling is not navigation');
 swipe(345,180);
 assert.match(main.innerHTML,/全12R/,'detail to venue board');
 assert.equal((main.innerHTML.match(/data-select-race="/g)||[]).length,12);
 swipe(345,180);
 assert.match(main.innerHTML,/今日の開催一覧/,'venue board to home');
 swipe(345,180);
 assert.match(main.innerHTML,/今日の開催一覧/,'home does not navigate into nonexistent previous page');
 click('[data-open-venue]',{dataset:{openVenue:venue},disabled:false});
 click('[data-select-race]',{dataset:{selectRace:venue+'|'+first.race},disabled:false});
 const settled=main.innerHTML;
 click('[data-select-race]',{dataset:{selectRace:venue+'|'+11},disabled:true});
 assert.equal(main.innerHTML,settled,'disabled slots must never create late predictions');
 click('[data-action]',{dataset:{action:'back-races'}});
 assert.match(main.innerHTML,/全12R/,'explicit return goes to venue listing');
 assert.match(fs.readFileSync('app/service-worker.js','utf8'),/mobile-race-nav\.js/);
 assert.match(fs.readFileSync('app/index.html','utf8'),/mobile-race-nav\.js/);
 console.log('BOAT LAB native touch swipe back + both venue/detail 1–12R picker: PASS');
},200);
