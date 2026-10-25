/* Formal tickets are the latest complete exhibition snapshot frozen before cutoff. */
(function(root){
'use strict';
function classify(r,day){
 const held={formal:false,label:'暫定買い目（展示未確認・正式化保留）'};
 if(r?.phase!=='exhibition'||!/^\d{4}-\d{2}-\d{2}$/.test(day||'')||
    !/^[a-f0-9]{64}$/i.test(r.sha256||''))return held;
 const cutoff=Date.parse(day+'T'+r.cutoff_jst+':00+09:00'),frozen=Date.parse(r.frozen_at_utc);
 if(!Number.isFinite(cutoff)||!Number.isFinite(frozen)||frozen>cutoff-120000||
    frozen<Date.parse(day+'T00:00:00+09:00'))return held;
 const rows=r.racers;
 if(!Array.isArray(rows)||rows.length!==6)return held;
 const lanes=new Set(),courses=new Set();
 for(const b of rows){
  if(!Number.isInteger(b.lane)||b.lane<1||b.lane>6||lanes.has(b.lane)||
     !Number.isInteger(b.course)||b.course<1||b.course>6||courses.has(b.course)||
     typeof b.exhibition_st!=='number'||!Number.isFinite(b.exhibition_st)||b.exhibition_st<-.5||b.exhibition_st>1||
     typeof b.exhibition_time!=='number'||!Number.isFinite(b.exhibition_time)||b.exhibition_time<5||b.exhibition_time>10)return held;
  lanes.add(b.lane);courses.add(b.course);
 }
 return {formal:true,label:'正式買い目（展示反映・締切前固定）'};
}
root.BoatTicketPolicy={classify};
if(typeof module!=='undefined')module.exports=root.BoatTicketPolicy;
})(typeof window==='undefined'?globalThis:window);
