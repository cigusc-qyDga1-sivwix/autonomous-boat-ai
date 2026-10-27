'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const lib=require('../local-video-bridge.js');
const html=fs.readFileSync('app/local-video-bridge.html','utf8');
const old=fs.readFileSync('app/exhibition-watch.js','utf8');
const cache=fs.readFileSync('app/service-worker.js','utf8');
assert.ok(lib.COLORS.length===6);
assert.ok(lib.validFile({name:'clip.MOV',size:131072}));
assert.ok(lib.validFile({name:'clip.mp4',size:1}));
assert.equal(lib.validFile({name:'script.js',size:500}),false);
assert.equal(lib.validFile({name:'clip.mp4',size:251*1024*1024}),false);
assert.equal(lib.validFile({name:'clip.mp4',size:0}),false);
assert.equal(lib.classify(254,20,20),'red_candidate');
assert.equal(lib.classify(22,82,252),'blue_candidate');
assert.equal(lib.classify(247,218,25),'yellow_candidate');
assert.equal(lib.classify(20,224,64),'green_candidate');
assert.equal(lib.classify(242,245,243),'white_candidate');
assert.equal(lib.classify(22,25,24),'black_candidate');
assert.equal(lib.classify(110,124,139),null);
assert.deepEqual(lib.secondsFor(5,0,.5),[0,.5,1,1.5,2,2.5,3,3.5,4,4.5]);
assert.deepEqual(lib.secondsFor(100,50,.2).length,24);
for(const [duration,start,gap] of [[0,0,.5],[15,-1,.5],[1,2,.5],[15,0,.05],[15,0,5]]){
 assert.throws(()=>lib.secondsFor(duration,start,gap));
}
const W=80,H=70, pixels=new Uint8ClampedArray(W*H*4);
for(let y=0;y<H;y++)for(let x=0;x<W;x++){
 const p=(y*W+x)*4;
 // Mid-blue background plus a red boat-like rectangle (but NOT an identified racer).
 const red=x>=32&&x<64&&y>=17&&y<43;
 pixels[p]=red?243:20;pixels[p+1]=red?12:108;pixels[p+2]=red?11:133;pixels[p+3]=255;
}
const metrics=lib.summarizePixels(pixels,W,H);
assert.equal(metrics.status,'UNVERIFIED_COLOR_REGIONS');
assert.ok(metrics.colour_candidates.red_candidate.pixel_samples>=8);
assert.ok(metrics.colour_candidates.red_candidate.center_px[0]>=32);
assert.equal(metrics.colour_candidates.red_candidate.verified_boat_id,null);
assert.equal(metrics.colour_candidates.blue_candidate.verified_boat_id,null);
const blank=new Uint8ClampedArray(W*H*4);
assert.equal(lib.summarizePixels(blank,W,H).status,'BLANK_OR_UNUSABLE_FRAME');
assert.throws(()=>lib.summarizePixels(blank,82,70),/invalid/);
const frames=[{t:0,width:80,height:70,pixel_audit:metrics,manual_marks:{mark:[32,20],1:[42,25]}},
 {t:.5,width:80,height:70,pixel_audit:lib.summarizePixels(blank,W,H),manual_marks:{}}];
const report=lib.buildAudit(frames,{date:'2026-10-28',venue:'唐津',race:1,source_type:'user_local_file'});
assert.equal(report.summary.frames_captured,2);
assert.equal(report.summary.usable_frames,1);
assert.equal(report.summary.blank_or_protected_frames,1);
assert.equal(report.summary.measured_turns,0);
assert.equal(report.summary.measured_post_start_stretches,0);
assert.equal(report.frames[0].manual_marks.mark[0],32);
assert.equal(report.frames[0].pixel_audit.colour_candidates.red_candidate.verified_boat_id,null);
assert.equal(report.upload_performed,false);
assert.equal(report.frames_exported,false);
assert.equal(report.actual_video_not_exported,true);
assert.equal(lib.raceParams({search:'?date=2026-10-28&venue=%E5%94%90%E6%B4%A5&race=1'}).venue,'唐津');
assert.match(html,/id="bridge-file"/);
assert.match(html,/id="bridge-share"/);
assert.match(html,/id="bridge-extract"/);
assert.match(html,/id="bridge-frame-canvas"/);
assert.match(html,/id="bridge-export"/);
assert.doesNotMatch(html,/<iframe/i);
assert.doesNotMatch(fs.readFileSync('app/local-video-bridge.js','utf8'),/\bfetch\s*\(/);
assert.doesNotMatch(fs.readFileSync('app/local-video-bridge.js','utf8'),/\bXMLHttpRequest\b/);
assert.doesNotMatch(fs.readFileSync('app/local-video-bridge.js','utf8'),/getUserMedia\s*\(/);
assert.match(cache,/local-video-bridge\.js/);
assert.match(old,/local-video-bridge\.html/);
console.log('Local video opt-in frame ingestion (file + screen capture) and pixel research audit PASS');
