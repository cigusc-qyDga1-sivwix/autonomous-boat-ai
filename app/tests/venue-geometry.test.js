const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const window={};
const context=vm.createContext({window,Number,Intl});
for(const file of ['app/venue-geometry.js','app/race-visual.js','app/tactical-preview.js'])
 vm.runInContext(fs.readFileSync(file,'utf8'),context);
const geo=window.BoatVenueGeometry,api=window.BoatRaceVisual;
assert.equal(geo.venues.length,24);
assert.equal(new Set(geo.venues).size,24);
assert.equal(geo.get('戸田').quality,'official_text_crosschecked');
assert.equal(geo.get('戸田').startWidthM,50);
assert.equal(geo.get('戸田').turn1WidthM,37);
assert.equal(geo.get('住之江').quality,'third_party_unverified');
assert.equal(geo.get('unknown'),null);
for(const venue of geo.venues){
 const map=geo.layout({venue});assert.ok(map.available);assert.ok(map.markY>=145&&map.markY<=225);
}
const racer=i=>({lane:i,course:i,name:'選手'+i,national_win_rate:5,
 average_start_timing:.17,course_average_st_by_course:{1:.14,2:.15,3:.16,4:.17,5:.18,6:.19}});
const original={venue:'戸田',race:1,racers:[1,2,3,4,5,6].map(racer),bets:[{combination:'1-2-3'}]};
const suminoe={...original,venue:'住之江'};
const before=JSON.stringify(original);
const a=api.tactics.analyze(original,api.tactics.defaults(original));
const b=api.tactics.analyze(suminoe,api.tactics.defaults(suminoe));
assert.notEqual(a.geometry.markY,b.geometry.markY);
assert.notEqual(api.tactics.trajectory(a.boats[0],a.rank[1],a),api.tactics.trajectory(b.boats[0],b.rank[1],b));
const cfg=api.tactics.defaults(original);cfg.turn1WidthM=28;
const manual=api.tactics.analyze(original,cfg);
assert.notEqual(a.geometry.markY,manual.geometry.markY);
assert.notEqual(api.tactics.trajectory(a.boats[0],a.rank[1],a),api.tactics.trajectory(manual.boats[0],manual.rank[1],manual));
assert.match(api.animationHTML(original),/data-plan-env="turn1WidthM"/);
assert.match(api.animationHTML(original),/data-plan-env="startWidthM"/);
assert.match(api.animationHTML(original),/data-plan-mark="1"/);
assert.match(api.animationHTML(original),/戸田/);
assert.equal(JSON.stringify(original),before);

// Accept authorized independent course data in either 1-based objects or 0-based arrays.
const racer3=racer(3);racer3.course_average_st_by_course=[.10,.12,.14,.16,.18,.20];
racer3.course_st_samples_by_course=[31,25,8,21,19,11];
const withSamples={...original,racers:original.racers.map((x,i)=>i===2?racer3:x)};
const saved=api.tactics.defaults(withSamples);
assert.equal(saved.boats[2].st,.14);
assert.equal(saved.boats[2].stSamples,8);
assert.match(api.animationHTML(withSamples),/小標本|8走/);

console.log('24 venue layout profiles, mark positions and ST sample metadata: PASS');