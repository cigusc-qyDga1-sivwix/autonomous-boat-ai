/* BOAT LAB venue water-layout profiles.
 * These are approximate stand-side clearances from published diagrams/summaries,
 * not surveyed coordinates, turning radii, or validated performance coefficients.
 * Treat third-party figures as provisional until individually checked with venue
 * official water maps; never use these values for official bet predictions.
 * The 300m distance between turn markers is a national standard.
 */
(function(){
'use strict';
const overview='https://jekyll-analysis-lab.com/layout-wind-and-tide/';
const officialToda='https://www.boatrace-toda.jp/data/suimen_guide.html';
const entries=[
 ['桐生',57.5,47],['戸田',50,37],['江戸川',58.2,37.1],
 ['平和島',49,37],['多摩川',56,41],['浜名湖',59,42.7],
 ['蒲郡',57,41.3],['常滑',57,40],['津',55,40],
 ['三国',62,45],['びわこ',59,47],['住之江',51,45],
 ['尼崎',55.9,49.1],['鳴門',55,45],['丸亀',58.5,42],
 ['児島',59,43],['宮島',55,40],['徳山',60,45],
 ['下関',50,43],['若松',50,41],['芦屋',55,50],
 ['福岡',63.8,50],['唐津',55,42],['大村',58,48]
];
const profiles={};
entries.forEach(([venue,startWidthM,turn1WidthM])=>{
 const official=venue==='戸田';
 profiles[venue]=Object.freeze({
  venue,startWidthM,turn1WidthM, shiftM:Math.max(0,startWidthM-turn1WidthM),
  quality:official?'official_text_crosschecked':'third_party_unverified',
  source:official?officialToda:overview,
  note:official?'会場公式テキストと照合済み（模式配置）':'二次資料の参考値。公式水面図との照合未完了'
 });
});
function get(venue){
 const data=profiles[String(venue||'')];
 return data?{...data}:null;
}
function layout(input){
 const base=get(input?.venue);
 const startWidthM=Number(input?.startWidthM??base?.startWidthM);
 const turn1WidthM=Number(input?.turn1WidthM??base?.turn1WidthM);
 if(!Number.isFinite(startWidthM)||!Number.isFinite(turn1WidthM)||
    startWidthM<20||startWidthM>100||turn1WidthM<20||turn1WidthM>100)
  return {venue:input?.venue||'',available:false,quality:'unavailable',
    startWidthM:null,turn1WidthM:null,shiftM:null,markY:182,
    narrowingPx:0,source:base?.source||null};
 const shiftM=startWidthM-turn1WidthM;
 return {
  venue:input?.venue||'',available:true,startWidthM,turn1WidthM,shiftM,
  quality:base?.quality||'user_input',
  source:base?.source||null,
  // Visual scale only. Fixed SVG width is NOT a measured digital twin.
  markY:Math.max(145,Math.min(225,260-turn1WidthM*1.55)),
  narrowingPx:Math.max(-35,Math.min(45,shiftM*1.7)),
  note:base?.note||'手動入力・実測未照合'
 };
}
window.BoatVenueGeometry=Object.freeze({get,layout,venues:Object.freeze(entries.map(x=>x[0]))});
})();