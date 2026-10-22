/* BOAT LAB screenshot OCR and official URL intake: deterministic offline tests. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const script=fs.readFileSync('app/result-reader.js','utf8');
const mockURL=class extends URL{};
mockURL.createObjectURL=()=> 'blob:https://boatlab.test/draft-preview';
mockURL.revokeObjectURL=()=>{};
const w={};
const context=vm.createContext({window:w,URL:mockURL,console,Date});
vm.runInContext(script,context);
const x=w.BoatResultReader;
const ctx={date:'2026-10-22',venue:'大村',race:6,sha256:'frozen-sha'};
assert.equal(x.parseOfficialUrl('https://www.boatrace.jp/owpc/pc/race/pay?hd=20261022').date,'2026-10-22');
const raceURL=x.parseOfficialUrl('https://www.boatrace.jp/owpc/pc/race/raceresult?rno=6&jcd=24&hd=20261022');
assert.equal(raceURL.venue,'大村');
assert.equal(raceURL.race,6);
assert.equal(raceURL.type,'raceresult');
assert.equal(x.parseOfficialUrl('https://boatrace.jp/owpc/pc/race/raceresult?hd=20261022&jcd=01&rno=12').venue,'桐生');
for(const bad of [
 'https://evil.example/owpc/pc/race/pay?hd=20261022',
 'http://www.boatrace.jp/owpc/pc/race/pay?hd=20261022',
 'https://boatrace.jp.evil.tld/owpc/pc/race/pay?hd=20261022',
 'https://www.boatrace.jp/owpc/pc/race/pay?hd=20261322',
 'https://www.boatrace.jp/owpc/pc/race/pay?hd=20261022&hd=20261023',
 'https://www.boatrace.jp/owpc/pc/race/odds3t?hd=20261022',
 'https://www.boatrace.jp/owpc/pc/race/raceresult?rno=6&jcd=0&hd=20261022',
 'https://www.boatrace.jp/owpc/pc/race/raceresult?rno=13&jcd=24&hd=20261022',
 ])assert.throws(()=>x.parseOfficialUrl(bad));
const key='2026-10-22|大村|6';
const results={[key]:{verified:true,source:'boatrace_official_pay',finish:'2-1-3',
  payout_per_100:2460,snapshot_sha256:'frozen-sha'}};
const matched=x.lookupOfficial(raceURL,ctx,results,{});
assert.equal(matched.found,true);
assert.equal(matched.finish,'2-1-3');
assert.equal(matched.payout_per_100,2460);
assert.equal(matched.status,'official_verified');
assert.equal(x.lookupOfficial(raceURL,ctx,{},{}).found,false);
assert.throws(()=>x.lookupOfficial(x.parseOfficialUrl('https://www.boatrace.jp/owpc/pc/race/pay?hd=20261021'),ctx,results,{}),/日付/);
assert.throws(()=>x.lookupOfficial(x.parseOfficialUrl('https://www.boatrace.jp/owpc/pc/race/raceresult?jcd=12&rno=6&hd=20261022'),ctx,results,{}),/競艇場/);
assert.throws(()=>x.lookupOfficial(x.parseOfficialUrl('https://www.boatrace.jp/owpc/pc/race/raceresult?jcd=24&rno=5&hd=20261022'),ctx,results,{}),/レース番号/);
assert.throws(()=>x.lookupOfficial(raceURL,ctx,results,{[key]:{status:'cancelled'}}),/返還・中止/);
assert.throws(()=>x.lookupOfficial(raceURL,{...ctx,sha256:'not-frozen'},results,{}),/照合ID/);
assert.match(x.render(ctx),/画像を読み取る/);
assert.match(x.render(ctx),/URLで照合/);
assert.match(x.render(ctx),/BOATRACE公式/);
const candidate=x.parseOcrText('大村 6R 2026年10月22日\n3連単 2-1-3  ¥2,460  5人気',ctx);
assert.equal(candidate.finish,'2-1-3');
assert.equal(candidate.payout_per_100,2460);
assert.equal(candidate.venue,'大村');
assert.equal(candidate.race,6);
assert.equal(candidate.date,'2026-10-22');
assert.equal(candidate.warnings.length,0);
assert.equal(candidate.status,'unconfirmed');
assert.equal(x.parseOcrText('3連単 2-1-3 ￥1,290',ctx).payout_per_100,1290);
assert.ok(x.parseOcrText('住之江 11R\n3連単 2-1-3 ¥2,460',ctx).warnings.some(v=>/競艇場/.test(v)));
assert.ok(x.parseOcrText('大村 6R\n3連単 2-1-3 1-2-3 ¥2,460 ¥3,480',ctx).warnings.some(v=>/複数/.test(v)));
assert.ok(x.parseOcrText('大村 6R 3連単 2-1-3 ¥2,460 返還',ctx).warnings.some(v=>/返還/.test(v)));
assert.ok(x.parseOcrText('大村 6R 3連単 2-1-3 ¥2,460 同着',ctx).warnings.some(v=>/同着/.test(v)));
assert.ok(x.parseOcrText('1-2-3 ¥2,460',ctx).warnings.some(v=>/3連単/.test(v)));
assert.equal(x.parseOcrText('1-2-3 ¥2,460',ctx).finish,'1-2-3');
assert.ok(!script.includes('fetch('),'Official URLs must never trigger cross-origin scraping');
assert.ok(!script.includes('.upload('),'Images must not be uploaded');
assert.ok(script.includes('Tesseract.createWorker'),'On-device OCR must really run');
console.log('BOAT LAB image OCR parser and official URL validation: PASS');
