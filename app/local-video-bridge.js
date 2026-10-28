/* BOAT LAB local-video bridge v0.1
 * Browser opt-in: locally selected file or user-granted screen share only.
 * No official stream access, no third-party fetch, no cross-origin bypass,
 * no media recording/upload, no inference of validated boat identities.
 */
(function(root){
'use strict';
const LIMIT_BYTES=250*1024*1024, MAX_FRAMES=24, PIXEL_WIDTH=640;
const COLORS=['white_candidate','black_candidate','red_candidate','blue_candidate','yellow_candidate','green_candidate'];
const ID_NAMES=['マーク中心','①艇（人手確認）','②艇（人手確認）','③艇（人手確認）','④艇（人手確認）','⑤艇（人手確認）','⑥艇（人手確認）',
 '岸の固定目標 1','岸の固定目標 2','岸の固定目標 3','岸の固定目標 4','岸の固定目標 5','岸の固定目標 6'];
const MODE_KEYS=['mark','1','2','3','4','5','6','shore1','shore2','shore3','shore4','shore5','shore6'];
function validFile(file){
 if(!file||typeof file.size!=='number'||file.size<1||file.size>LIMIT_BYTES)return false;
 return /\.(mp4|mov|m4v|webm|avi)$/i.test(file.name||'');
}
function classify(r,g,b){
 const max=Math.max(r,g,b),min=Math.min(r,g,b),delta=max-min;
 if(max>215 && delta<34)return 'white_candidate';
 if(max<67 && delta<24)return 'black_candidate';
 if(max<83||delta<34)return null;
 const saturation=max?delta/max:0;
 if(saturation<.38)return null;
 let hue;
 if(max===r)hue=((g-b)/delta)%6;
 else if(max===g)hue=(b-r)/delta+2;
 else hue=(r-g)/delta+4;
 hue=(hue*60+360)%360;
 if(hue<19||hue>347)return 'red_candidate';
 if(hue>=35&&hue<67)return 'yellow_candidate';
 if(hue>=70&&hue<171)return 'green_candidate';
 if(hue>=185&&hue<264)return 'blue_candidate';
 return null;
}
function summarizePixels(rgba,width,height,{step=4,topCrop=.18,bottomCrop=.03}={}){
 if(!Number.isInteger(width)||width<2||!Number.isInteger(height)||height<2 ||
    !rgba||rgba.length<width*height*4)throw Error('frame_pixels_invalid');
 const n=Object.fromEntries(COLORS.map(k=>[k,{count:0,rx:0,ry:0}]));
 let count=0,sum=0,sumsq=0,changed=0;
 const top=Math.floor(height*topCrop),bottom=Math.floor(height*(1-bottomCrop));
 for(let y=top;y<bottom;y+=step)for(let x=0;x<width;x+=step){
  const p=(y*width+x)*4,r=rgba[p],g=rgba[p+1],b=rgba[p+2];
  const brightness=(r*77+g*150+b*29)/256;
  count++;sum+=brightness;sumsq+=brightness*brightness;
  if(brightness>25)changed++;
  const tag=classify(r,g,b);
  if(!tag)continue;
  n[tag].count++;n[tag].rx+=x;n[tag].ry+=y;
 }
 const mean=count?sum/count:0;
 const deviation=Math.sqrt(Math.max(0,count?sumsq/count-mean*mean:0));
 const candidates=Object.fromEntries(COLORS.map(k=>{
  const a=n[k];
  return [k,{pixel_samples:a.count,center_px:a.count>=8?
         [Math.round(a.rx/a.count),Math.round(a.ry/a.count)]:null,
         verified_boat_id:null}];
 }));
 const colourGroups=COLORS.filter(k=>n[k].count>=8).length;
 // Different brightly coloured regions may have nearly identical luma.
 // Pure black or a flat monochrome/protected stream stays unusable.
 return {status:(changed<10||(deviation<8&&colourGroups<2))?'BLANK_OR_UNUSABLE_FRAME':'UNVERIFIED_COLOR_REGIONS',
  width,height,luma_sd:Math.round(deviation*100)/100,
  meaningful_sample_count:count,colour_candidates:candidates,
  caveat:'Raw colour regions include water, graphics, reflections; NOT six confirmed boats.'};
}
function summaryFromSamples(frames){
 const usable=frames.filter(f=>f.pixel_audit?.status==='UNVERIFIED_COLOR_REGIONS').length;
 return {frames_captured:frames.length,usable_frames:usable,
  blank_or_protected_frames:frames.length-usable,
  confirmed_boats:0,measured_turns:0,measured_post_start_stretches:0};
}
function buildAudit(frames,{date,venue,race,source_type}={}){
 const samples=frames.map(f=>({
  t_seconds:typeof f.t==='number'?Math.round(f.t*1000)/1000:null,
  width:f.width,height:f.height,
  pixel_audit:f.pixel_audit,
  manual_marks:f.manual_marks||{},
 }));
 return {
  schema:'boatlabs.local_video_frame_bridge.v0.1',
  source_type:source_type||'not_reported',date:date||null,venue:venue||null,
  race:race||null,created_at_utc:new Date().toISOString(),
  upload_performed:false,frames_exported:false,
  actual_video_not_exported:true,frames:samples,
  summary:summaryFromSamples(samples),
  data_usage:'RESEARCH_ONLY; NO official ST, auto identity, predictions or settle/ROI',
  note:'Color candidates are NOT boat IDs. Frame observations are local, unverified and pixel-only; no first-mark clearance in meters.',
 };
}
function buildMikuniSeedLibrary(audit,source_sha256){
 // Source is an explicitly authorized local video. This JSON carries only
 // human-labelled first-frame seeds; not proof of racer ID or water calibration.
 if(!audit||audit.schema!=='boatlabs.local_video_frame_bridge.v0.1'||
    audit.venue!=='三国'||audit.source_type!=='user_local_file'||
    !/^20\\d{2}-\\d{2}-\\d{2}$/.test(audit.date||'')||
    !Number.isInteger(audit.race)||audit.race<1||audit.race>12)
   throw Error('mikuni_authorized_file_and_race_required');
 const sha=String(source_sha256||'').trim().toLowerCase();
 if(!/^[0-9a-f]{64}$/.test(sha))throw Error('source_sha256_required');
 const frames=audit.frames;
 if(!Array.isArray(frames)||frames.length<2)throw Error('at_least_two_frames_required');
 const a=frames[0],b=frames[1];
 if(!Number.isInteger(a.width)||!Number.isInteger(a.height)||
    a.width<120||a.height<80||!Number.isFinite(a.t_seconds)||
    !Number.isFinite(b.t_seconds)||
    Math.abs((b.t_seconds-a.t_seconds)-.5)>.001)
   throw Error('source_frame_size_or_half_second_interval_invalid');
 if(a.t_seconds<0||a.t_seconds>300)throw Error('clip_start_out_of_range');
 const marks=a.manual_marks||{};
 const checked=(key)=>{
   const point=marks[key];
   if(!Array.isArray(point)||point.length!==2||!point.every(Number.isFinite)||
      point[0]<8||point[0]>=a.width-8||point[1]<8||point[1]>=a.height-8)
      throw Error('missing_or_outside_seed_'+key);
   return point.map(x=>Math.round(x*100)/100);
 };
 const boats=Array.from({length:6},(_,i)=>({lane:i+1,center_px:checked(String(i+1))}));
 const static_landmarks=Array.from({length:6},(_,i)=>({id:'shore_'+(i+1),
                                      center_px:checked('shore'+(i+1))}));
 const record={
   schema:'boatlabs.mikuni_video_seed_annotations.v0.1',
   event_date:audit.date,venue_code:'10',race:audit.race,
   source_sha256:sha,reference_frame_index:0,
   clip_start_seconds:a.t_seconds,sample_interval_s:.5,
   frame_size:{width:a.width,height:a.height},
   boats,static_landmarks,
   annotations_provenance:'USER_SEEDED_PIXEL_ONLY_ID_AND_METRE_CALIBRATION_NOT_VERIFIED',
 };
 return {
   schema:'boatlabs.mikuni_seed_library.v0.1',
   event_date:audit.date,venue_code:'10',records:[record],
   video_content_included:false,
   verified_boat_id_count:0,
   note:'Six manual boat seed positions and six static image landmarks only; not racer ID proof, not speed in metres, not a final forecast.',
 };
}
function secondsFor(duration,start,interval,maxFrames=MAX_FRAMES){
 if(!Number.isFinite(duration)||duration<=0)throw Error('video_duration_unavailable');
 if(!Number.isFinite(start)||start<0||start>=duration)throw Error('start_out_of_range');
 if(!Number.isFinite(interval)||interval<.2||interval>3)throw Error('interval_out_of_range');
 const result=[];
 for(let i=0;i<maxFrames;i++){
  const t=start+i*interval;
  if(t>=duration-.02)break;
  result.push(Math.round(t*1000)/1000);
 }
 return result;
}
function raceParams(location){
 const q=new URLSearchParams(location?.search||'');
 const date=q.get('date'), venue=q.get('venue'), race=Number(q.get('race'));
 return {date:/^20\d{2}-\d{2}-\d{2}$/.test(date||'')?date:null,
         venue:venue||null,race:Number.isInteger(race)&&race>=1&&race<=12?race:null};
}
function mount(doc,win){
 const e=id=>doc.getElementById(id);
 const local=e('bridge-file'),permission=e('bridge-permission'),preview=e('bridge-preview'),
  screen=e('bridge-share'),stop=e('bridge-stop'),extract=e('bridge-extract'),
  start=e('bridge-start'),interval=e('bridge-interval'),
  status=e('bridge-status'),frameList=e('bridge-frame-list'),
  frameCanvas=e('bridge-frame-canvas'),frameTitle=e('bridge-frame-title'),
  mode=e('bridge-annotation-mode'),download=e('bridge-export'),json=e('bridge-json'),
  seedExport=e('bridge-seed-export'),videoSha=e('bridge-source-sha');
 if(!local||!preview||!screen||!frameCanvas||!permission)return false;
 const ctx=frameCanvas.getContext('2d',{willReadFrequently:true});
 let mediaUrl=null,stream=null,frameData=[],selected=0,capturing=false,sourceType=null;
 const sampleCanvas=doc.createElement('canvas');
 const sampleCtx=sampleCanvas.getContext('2d',{willReadFrequently:true});
 function notify(msg,error=false){status.textContent=msg;status.classList.toggle('error',error);}
 function disable(){
  extract.disabled=!(permission.checked&&preview.readyState>=2&&!capturing);
  download.disabled=!frameData.length;
  if(seedExport)seedExport.disabled=!frameData.length||!permission.checked;
 }
 function endStream(){
  if(stream){for(const t of stream.getTracks())t.stop();stream=null;}
  stop.disabled=true;
  if(sourceType==='user_granted_screen_share'){preview.pause();preview.srcObject=null;sourceType=null;}
  disable();
 }
 function endFile(){
  if(mediaUrl){win.URL.revokeObjectURL(mediaUrl);mediaUrl=null;}
  if(sourceType==='user_local_file'){preview.pause();preview.removeAttribute('src');preview.load();sourceType=null;}
  disable();
 }
 function resetFrames(){
  frameData=[];frameList.textContent='';frameTitle.textContent='まだフレームを取得していません。';
  ctx.clearRect(0,0,frameCanvas.width,frameCanvas.height);
  json.textContent='';disable();
 }
 function setupDimensions(){
  if(!preview.videoWidth||!preview.videoHeight)throw Error('video_dimensions_unavailable');
  const ratio=Math.min(1,PIXEL_WIDTH/preview.videoWidth);
  sampleCanvas.width=Math.max(4,Math.round(preview.videoWidth*ratio));
  sampleCanvas.height=Math.max(4,Math.round(preview.videoHeight*ratio));
  frameCanvas.width=sampleCanvas.width;frameCanvas.height=sampleCanvas.height;
 }
 function grab(t){
  sampleCtx.drawImage(preview,0,0,sampleCanvas.width,sampleCanvas.height);
  const data=sampleCtx.getImageData(0,0,sampleCanvas.width,sampleCanvas.height);
  return {t,width:sampleCanvas.width,height:sampleCanvas.height,
   thumbnail:sampleCanvas.toDataURL('image/jpeg',.7),
   pixel_audit:summarizePixels(data.data,sampleCanvas.width,sampleCanvas.height),
   manual_marks:{}};
 }
 function renderFrame(){
  if(!frameData.length)return;
  const f=frameData[selected];
  const image=new win.Image();
  image.onload=()=>{
   ctx.clearRect(0,0,frameCanvas.width,frameCanvas.height);
   ctx.drawImage(image,0,0,frameCanvas.width,frameCanvas.height);
   for(const [key,point] of Object.entries(f.manual_marks)){
    ctx.strokeStyle=key==='mark'?'#ffffff':'#00ffb7';
    ctx.lineWidth=3;ctx.beginPath();ctx.arc(point[0],point[1],7,0,2*Math.PI);ctx.stroke();
    ctx.fillStyle='#fff';ctx.font='bold 16px sans-serif';
    ctx.fillText(key==='mark'?'1M':String(key),point[0]+9,point[1]+5);
   }
  };
  image.src=f.thumbnail;
  frameTitle.textContent='フレーム '+(selected+1)+'/'+frameData.length+'｜'+f.t.toFixed(2)+'秒｜'+f.pixel_audit.status+
   '｜色候補は未検証（艇識別ではありません）';
  [...frameList.children].forEach((el,i)=>el.classList.toggle('selected',i===selected));
 }
 function renderGallery(){
  frameList.textContent='';
  frameData.forEach((f,i)=>{
   const b=doc.createElement('button');b.type='button';b.className='frame-select';
   const im=doc.createElement('img');im.src=f.thumbnail;im.alt=f.t.toFixed(2)+'秒のフレーム';im.loading='lazy';
   const cap=doc.createElement('span');cap.textContent=f.t.toFixed(2)+'秒';
   b.append(im,cap);b.addEventListener('click',()=>{selected=i;renderFrame();});
   frameList.append(b);
  });
  renderFrame();
  json.textContent=JSON.stringify(summaryFromSamples(frameData),null,2);
  download.disabled=false;
 }
 async function ready(){
  if(preview.readyState>=2&&preview.videoWidth)return;
  await new Promise((resolve,reject)=>{
   let timer=setTimeout(()=>{cleanup();reject(Error('video_decode_timeout'));},8500);
   const okay=()=>{cleanup();resolve();},failed=()=>{cleanup();reject(Error('video_decode_failed'));};
   const cleanup=()=>{clearTimeout(timer);preview.removeEventListener('loadeddata',okay);preview.removeEventListener('error',failed);};
   preview.addEventListener('loadeddata',okay,{once:true});preview.addEventListener('error',failed,{once:true});
  });
 }
 function seek(t){
  return new Promise((resolve,reject)=>{
   if(Math.abs(preview.currentTime-t)<.035&&preview.readyState>=2)return resolve();
   let timer=setTimeout(()=>{finish();reject(Error('video_seek_timeout'));},8000);
   const done=()=>{finish();resolve();},error=()=>{finish();reject(Error('video_seek_failed'));};
   const finish=()=>{clearTimeout(timer);preview.removeEventListener('seeked',done);preview.removeEventListener('error',error);};
   preview.addEventListener('seeked',done,{once:true});preview.addEventListener('error',error,{once:true});
   try{preview.currentTime=t;}catch(err){finish();reject(err);}
  });
 }
 async function captureLocal(){
  await ready();
  const tlist=secondsFor(preview.duration,Number(start.value),Number(interval.value));
  if(!tlist.length)throw Error('no_sample_times');
  preview.pause();setupDimensions();resetFrames();
  for(const t of tlist){
   await seek(t);
   frameData.push(grab(t));notify('動画を端末内で解析中：'+frameData.length+'/'+tlist.length+'フレーム');
  }
  renderGallery();
 }
 async function captureShare(){
  setupDimensions();resetFrames();
  const limit=16;const period=500;
  for(let i=0;i<limit;i++){
   if(!stream||!stream.getVideoTracks().some(t=>t.readyState==='live'))break;
   frameData.push(grab(i*.5));
   notify('本人が共有した画面を解析中：'+frameData.length+'/'+limit+'フレーム');
   await new Promise(resolve=>setTimeout(resolve,period));
  }
  renderGallery();endStream();
 }
 local.addEventListener('change',async()=>{
  endStream();endFile();resetFrames();
  if(!permission.checked){notify('先に利用条件の確認が必要です',true);return;}
  const file=local.files&&local.files[0];
  if(!validFile(file)){notify('250MB以下のMP4/MOV/WEBMなどを選んでください',true);return;}
  mediaUrl=win.URL.createObjectURL(file);sourceType='user_local_file';
  preview.src=mediaUrl;preview.hidden=false;preview.muted=true;preview.load();
  // On iOS Safari decoded video frames can require tapping Play first.
  // Do not discard a valid chosen file merely because autoplay is restricted.
  notify('動画ファイルを選択しました。iPhoneでは必要なら再生ボタンを一度押してから抽出してください。');
  disable();
 });
 preview.addEventListener('loadeddata',()=>{
  if(sourceType==='user_local_file')notify('動画を端末内で読み込めました。フレーム抽出を実行できます。');
  disable();
 });
 preview.addEventListener('canplay',disable);
 preview.addEventListener('error',()=>{
  if(sourceType==='user_local_file')notify('動画を再生できません。iPhoneではH.264 MP4形式でお試しください。',true);
  disable();
 });
 permission.addEventListener('change',()=>{
  local.disabled=!permission.checked;screen.disabled=!permission.checked||typeof win.navigator?.mediaDevices?.getDisplayMedia!=='function';
  if(!permission.checked){endStream();endFile();resetFrames();local.value='';notify('利用条件を確認してください');}
  else notify('許可されたファイルを選ぶか、対応ブラウザで画面共有を開始してください。');
  disable();
 });
 screen.addEventListener('click',async()=>{
  if(!permission.checked||typeof win.navigator?.mediaDevices?.getDisplayMedia!=='function'){
   notify('このブラウザでは画面共有を使えません。端末内ファイルをご利用ください。',true);return;
  }
  // The native browser permission dialog is user-initiated and cannot be bypassed.
  try{
   endFile();endStream();resetFrames();
   stream=await win.navigator.mediaDevices.getDisplayMedia({video:{frameRate:10},audio:false});
   stream.getVideoTracks()[0]?.addEventListener('ended',()=>{endStream();notify('画面共有が終了しました。');});
   preview.srcObject=stream;preview.hidden=false;preview.muted=true;sourceType='user_granted_screen_share';
   await preview.play();await ready();
   stop.disabled=false;
   notify('画面共有中。本人が選択した画面だけを短時間サンプリングできます。');
   disable();
  }catch(err){endStream();notify('画面共有は開始できませんでした：'+(err.message||err.name),true);}
 });
 stop.addEventListener('click',()=>{endStream();notify('画面共有を停止しました。');});
 extract.addEventListener('click',async()=>{
  if(capturing||!permission.checked||!sourceType)return;
  capturing=true;disable();
  try{
   if(sourceType==='user_local_file')await captureLocal();
   else await captureShare();
   const sum=summaryFromSamples(frameData);
   notify('読み取り成功：'+sum.frames_captured+'フレーム。映像有効候補'+sum.usable_frames+
     '／無効または保護された画面'+sum.blank_or_protected_frames+'。艇ID・ターン精度は未確定。');
  }catch(err){notify('フレームを取り込めませんでした：'+(err?.message||'不明')+
    '（DRM保護・対応コーデック・表示条件を確認）',true);}
  finally{capturing=false;disable();}
 });
 frameCanvas.addEventListener('click',event=>{
  if(!frameData.length)return;
  const rect=frameCanvas.getBoundingClientRect();
  const x=(event.clientX-rect.left)/rect.width*frameCanvas.width;
  const y=(event.clientY-rect.top)/rect.height*frameCanvas.height;
  if(!Number.isFinite(x)||!Number.isFinite(y)||x<0||y<0||x>frameCanvas.width||y>frameCanvas.height)return;
  const key=mode.value==='mark'?'mark':mode.value;
  frameData[selected].manual_marks[key]=[Math.round(x),Math.round(y)];
  renderFrame();download.disabled=false;
 });
 download.addEventListener('click',()=>{
  if(!frameData.length)return;
  const audit=buildAudit(frameData,{...raceParams(win.location),source_type:sourceType||'stopped_screen_share'});
  const blob=new win.Blob([JSON.stringify(audit,null,2)],{type:'application/json'});
  const u=win.URL.createObjectURL(blob);
  const a=doc.createElement('a');a.href=u;a.download='boat-lab-frame-audit-'+(audit.date||'local')+'.json';
  doc.body.append(a);a.click();a.remove();
  setTimeout(()=>win.URL.revokeObjectURL(u),1000);
  notify('フレーム画像を含まない研究JSONを、この端末へ書き出しました。');
 });
 if(seedExport){
  seedExport.addEventListener('click',async()=>{
   if(!permission.checked||sourceType!=='user_local_file'||
      !frameData.length){notify('三国の許可済みローカル動画が必要です。',true);return;}
   const file=local.files?.[0];
   let sha=videoSha?.value?.trim()?.toLowerCase()||'';
   try{
    if(!sha){
     if(!file||file.size>120*1024*1024||!win.crypto?.subtle?.digest)
      throw Error('SHA256を入力してください。120MB以下の動画なら端末内で計算できます。');
     notify('動画のSHA256を端末内で計算中。ファイルはアップロードしません。');
     const hashed=await win.crypto.subtle.digest('SHA-256',await file.arrayBuffer());
     sha=Array.from(new Uint8Array(hashed),b=>b.toString(16).padStart(2,'0')).join('');
     if(videoSha)videoSha.value=sha;
    }
    const audit=buildAudit(frameData,{...raceParams(win.location),source_type:'user_local_file'});
    const seeds=buildMikuniSeedLibrary(audit,sha);
    const blob=new win.Blob([JSON.stringify(seeds,null,2)],{type:'application/json'});
    const u=win.URL.createObjectURL(blob);
    const a=doc.createElement('a');a.href=u;
    a.download='mikuni-6boat-seeds-'+audit.date+'.json';
    doc.body.append(a);a.click();a.remove();
    setTimeout(()=>win.URL.revokeObjectURL(u),1000);
    notify('艇6点・岸6点の未検証の初期位置をJSONとして端末に保存。動画は送信・保存しません。');
   }catch(err){notify('6艇の初期位置データが未完成：'+(err?.message||'確認不足'),true);}
  });
 }
 win.addEventListener?.('pagehide',()=>{endStream();endFile();});
 local.disabled=true;screen.disabled=true;extract.disabled=true;download.disabled=true;stop.disabled=true;
 ID_NAMES.forEach((name,i)=>{
  const o=doc.createElement('option');o.value=MODE_KEYS[i];o.textContent=name;mode.append(o);
 });
 const race=raceParams(win.location);
 if(race.venue&&race.race)notify((race.date||'対象日未設定')+' '+race.venue+' '+race.race+'R：動画を選ぶと解析できます。');
 else notify('端末内ファイル、または画面共有から解析を開始できます。');
 return true;
}
const api={COLORS,ID_NAMES,MODE_KEYS,LIMIT_BYTES,MAX_FRAMES,validFile,classify,summarizePixels,summaryFromSamples,
 buildAudit,buildMikuniSeedLibrary,secondsFor,raceParams,mount};
root.BoatLocalVideoBridge=api;
if(typeof module==='object'&&module.exports)module.exports=api;
if(root.document)mount(root.document,root);
})(typeof window!=='undefined'?window:globalThis);
