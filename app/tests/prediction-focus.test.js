'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ctx={Intl,Date};ctx.globalThis=ctx;
vm.runInNewContext(fs.readFileSync('app/prediction-focus.js','utf8'),ctx);
const board=ctx.BoatPredictionFocus;
const now=new Date('2026-11-11T09:00:00Z'); // 18:00 JST
const policy={classify:()=>({formal:true})};
function race(venue,race,cutoff_jst,overrides={}){
 return {venue,race,cutoff_jst,classification:'WATCH',phase:'exhibition',
  entry_exhibition_gate:{final_eligible:true},
  exhibition_input_check:{verified_before_freeze:true},
  bets:[{combination:'1-3-4',virtual_yen:30000},{combination:'1-4-3',virtual_yen:15000},
    {combination:'3-1-4',virtual_yen:5000}],...overrides};
}
const confirmed=race('下関',9,'18:45',{scenario:'イン先マイ→2着差し残りの保存時仮説'});
const unconfirmed=race('若松',8,'18:20',{entry_exhibition_gate:{final_eligible:false}});
const skipped=race('大村',8,'19:30',{classification:'SKIP'});
const data={mode:'auto-live',event_date:'2026-11-11',forecast_races:[confirmed,unconfirmed,skipped],
 updated_at_utc:'2026-11-11T08:50:00Z'};
let model=board.summarize(data,now,policy);
assert.equal(model.formal.length,1);
assert.equal(model.research.length,2);
assert.equal(model.first.venue,'若松');
assert.equal(board.isFormal(skipped,data,policy),false);
assert.equal(board.isFormal(confirmed,data,policy,{imported:true}),false);
assert.equal(board.isFormal(confirmed,{...data,mode:'manual'},policy),false);
assert.equal(board.isFormal({...confirmed,exhibition_input_check:{}},data,policy),false);
assert.equal(board.isFormal(confirmed,data,{classify:()=>({formal:false})}),false);
assert.equal(board.isFormal(confirmed,data,null),false);
assert.equal(board.getMode(),'formal');
let html=board.render(data,now,policy);
assert.match(html,/下関/);
assert.match(html,/18:45/);
assert.match(html,/30,000円/);
assert.match(html,/保存時の展開仮説/);
assert.match(html,/イン先マイ→2着差し残りの保存時仮説/);
assert.doesNotMatch(html,/予想データの更新が遅れています/);
assert.match(board.render({...data,updated_at_utc:'2026-11-11T07:50:00Z'},now,policy),/更新が遅れています/);
assert.match(board.render({...data,updated_at_utc:''},now,policy),/最終取得時刻不明/);
assert.match(html,/1Rの正式予想詳細を開く|9Rの正式予想詳細を開く/);
assert.match(html,/data-race="下関\\|9"/);
assert.doesNotMatch(html,/class="bl-focus-card[^"]*"[^>]*>[^]*?若松/);
assert.match(html,/正式予想 <span>1<\/span>/);
assert.match(html,/暫定・研究 <span>2<\/span>/);
assert.equal(board.setMode('research'),'research');
html=board.render(data,now,policy);
assert.match(html,/若松/);
assert.match(html,/SKIP・研究記録/);
assert.doesNotMatch(html,/<strong>下関 <span>9R<\/span><\/strong>/);
assert.match(html,/参考表示のみ/);
assert.equal(board.setMode('unexpected'),'formal');
const old=board.render({...data,event_date:'2026-11-10'},now,policy);
assert.match(old,/今日の予想・締切として扱いません/);
assert.doesNotMatch(old,/<article class="bl-focus-card/);
const imported=board.render(data,now,policy,{imported:true});
assert.match(imported,/正式予想は、現在の締切予定にはありません/);
const byVenue=board.summarize(data,now,policy,{venue:'下関'});
assert.equal(byVenue.upcoming.length,1);
const escaped=board.render({...data,forecast_races:[race('<script>',1,'18:40')]},now,policy);
assert.match(escaped,/&lt;script&gt;/);
assert.doesNotMatch(escaped,/<script>/);
// Post-cutoff retention is precise to the second. An 11:00 cutoff
// remains visible until 11:09:59.999 and disappears at exactly 11:10.
const cutoffRace=race('芦屋',6,'11:00');
const tenData={...data,forecast_races:[cutoffRace]};
const beforeStart=new Date('2026-11-11T01:59:59Z'); // 10:59:59 JST
const atStart=new Date('2026-11-11T02:00:00Z'); // 11:00 JST
const nearEnd=new Date('2026-11-11T02:09:59Z'); // 11:09:59 JST
const afterEnd=new Date('2026-11-11T02:10:00Z'); // 11:10 JST
assert.equal(board.summarize(tenData,beforeStart,policy).postCutoff.length,0);
assert.equal(board.summarize(tenData,atStart,policy).postCutoff.length,1);
assert.equal(board.summarize(tenData,nearEnd,policy).postCutoff.length,1);
assert.equal(board.summarize(tenData,afterEnd,policy).postCutoff.length,0);
assert.equal(board.summarize(tenData,beforeStart,policy).upcoming.length,1);
assert.equal(board.summarize(tenData,atStart,policy).upcoming.length,0);
assert.match(board.render(tenData,atStart,policy),/締切後10分・固定予想の記録/);
assert.match(board.render(tenData,atStart,policy),/投票締切済み ・ 記録表示あと約10分/);
assert.match(board.render(tenData,nearEnd,policy),/記録表示あと約1分/);
assert.match(board.render(tenData,atStart,policy),/新規投票不可・買い目変更なし/);
assert.match(board.render(tenData,atStart,policy),/展示反映済みの正式固定記録/);
assert.doesNotMatch(board.render(tenData,beforeStart,policy),/bl-focus-urgent"/);
assert.doesNotMatch(board.render(tenData,afterEnd,policy),/bl-focus-urgent"/);
const pendingSoon={...tenData,forecast_races:[{...cutoffRace,entry_exhibition_gate:{final_eligible:false}}]};
assert.match(board.render(pendingSoon,atStart,policy),/展示未確認の暫定記録/);
assert.doesNotMatch(board.render(pendingSoon,atStart,policy),/展示反映済みの正式固定記録/);
const skippedClosed={...tenData,forecast_races:[{...cutoffRace,classification:'SKIP'}]};
assert.equal(board.summarize(skippedClosed,atStart,policy).postCutoff.length,0,
 'do not prioritize SKIP research as a recent frozen betting forecast');
assert.match(board.render({...tenData,event_date:'2026-11-10'},atStart,policy),
 /今日の予想・締切として扱いません/);
console.log('Prediction-first quickboard: post-cutoff ten-minute retention and source-safe display PASS');
