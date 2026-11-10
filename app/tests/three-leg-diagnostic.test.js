'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const diag=require('../three-leg-diagnostic.js');
const four=require('../four-factor.js');

function fixture(venue='児島'){
 return {venue,phase:'exhibition',ticket_status:'formal',
   sha256:'fixture-frozen-sha',
   racers:Array.from({length:6},(_,i)=>({
     lane:i+1,course:i+1,exhibition_st:.12+i*.01,
     exhibition_time:6.70+i*.03,
     original_exhibition:{lap_time:36.0+i*.12,half_lap_time:18.0+i*.08,
       turn_time:5.2+i*.055,straight_time:7.0+i*.045}
   }))};
}
const base=fixture();
const before=JSON.stringify(base);
const a=diag.evaluate(base);
assert.equal(a.status,'ready');
assert.equal(a.not_formal,true);
assert.equal(a.result_data_used,false);
assert.equal(a.calibrated,false);
assert.equal(a.rows.length,6);
assert.equal(a.rows[0].stretch.status,'上位傾向');
assert.equal(a.rows[0].pickup.status,'上位傾向');
assert.equal(a.rows[0].launch.status,'判定保留');
assert.equal(a.rows[0].launch.evidence_level,'判定不可');
assert.equal(a.rows[0].stretch.evidence_level,'中');
assert.equal(JSON.stringify(base),before,'Never mutate pre-cutoff formal snapshot');

const hamanako=diag.evaluate(fixture('浜名湖'));
assert.equal(hamanako.rows[0].launch.measured_keys[0],'straight_time');
assert.deepEqual(hamanako.rows[0].stretch.measured_keys,['exhibition_time']);
assert.equal(hamanako.rows[0].launch.evidence_level,'低');

const fukuoka=diag.evaluate(fixture('福岡'));
assert.ok(fukuoka.venue_measurement_note.includes('他場と異なる'));
assert.equal(fukuoka.rows[0].stretch.evidence_level,'低');
assert.deepEqual(fukuoka.rows[0].launch.measured_keys,['straight_time']);

const kiryu=diag.evaluate(fixture('桐生'));
assert.ok(kiryu.rows[0].pickup.measured_keys.includes('half_lap_time'));
assert.ok(!kiryu.rows[0].pickup.measured_keys.includes('lap_time'));
const suminoe=diag.evaluate(fixture('住之江'));
assert.ok(!suminoe.complete_six_boat_metrics.includes('straight_time'));
assert.ok(!suminoe.missing_expected_metrics.includes('straight_time'));

const oneMissing=fixture();oneMissing.racers[4].original_exhibition.turn_time=null;
const m=diag.evaluate(oneMissing);
assert.ok(m.missing_expected_metrics.includes('turn_time'));
assert.ok(!m.rows[0].pickup.measured_keys.includes('turn_time'));
assert.ok(diag.evaluate({...base,phase:'baseline'}).status==='not_verified');
assert.ok(diag.evaluate({...base,ticket_status:'provisional'}).status==='not_verified');
assert.ok(diag.evaluate({...base,racers:base.racers.slice(0,5)}).status==='invalid_six_boats');

const injected={...fixture(),result:{finish:'6-5-4'},official_pay:1000000};
assert.deepEqual(diag.evaluate(injected),a,'No postrace fields may affect diagnosis');
assert.ok(diag.panel({...base,ticket_status:'provisional'})==='');
assert.ok(diag.panel(base).includes('出足系（回り・周回）'));
assert.ok(diag.panel(base).includes('実映像'));
assert.ok(!diag.panel({...base,ticket_status:'provisional'}).includes('上位傾向'));

const html=four.panel({...base,four_factor:{rows:Array.from({length:6},(_,i)=>({
  lane:i+1,factors:{athlete:{applied_multiplier:1},motor:{applied_multiplier:1},
   exhibition:{applied_multiplier:1},weather:{applied_multiplier:1}},combined_multiplier:1
 }))}});
assert.ok(html.includes('3種類の足・展示数値診断'));
assert.ok(fs.readFileSync('app/index.html','utf8').includes('three-leg-diagnostic.js'));
console.log('Three-leg numeric exhibition diagnostic: venue segments, 6-boat, no results, no main impact PASS');
