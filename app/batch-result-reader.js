/* BOAT LAB full-day / multi-venue batch result reader.
 * Official URL: same-origin independently fetched daily BOATRACE pay snapshot.
 * Image: device-side OCR via Tesseract.js; results ALWAYS unverified drafts.
 * Neither path edits frozen predictions. A deliberate review/confirm is required.
 */
(function(){
 'use strict';
 const VENUES=['桐生','戸田','江戸川','平和島','多摩川','浜名湖','蒲郡','常滑','津','三国','びわこ','住之江','尼崎','鳴門','丸亀','児島','宮島','徳山','下関','若松','芦屋','福岡','唐津','大村'];
 const OCR_CDN='https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js';
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const validFinish=v=>typeof v==='string'&&/^[1-6]-[1-6]-[1-6]$/.test(v)&&new Set(v.split('-')).size===3;
 const validPayout=v=>Number.isSafeInteger(v)&&v>=100&&v<=10000000&&v%10===0;
 const key=(date,venue,race)=>date+'|'+venue+'|'+race;
 const clean=v=>String(v||'').normalize('NFKC').replace(/[￥]/g,'¥').replace(/[，]/g,',').replace(/[ー－−–—‐→]/g,'-');
 let contextDate=null,imageFile=null,imageUrl='',working=false,message='',error=false;
 let rows=[],inputUrl='',importKind='',sourceStamp='',warnings=[],recognizedText='',selectedVenue='',recognizedTotal=0;
 let scriptPromise=null;
 function reset(){
   if(imageUrl && typeof URL!=='undefined'&&URL.revokeObjectURL)URL.revokeObjectURL(imageUrl);
   imageFile=null;imageUrl='';working=false;message='';error=false;
   rows=[];inputUrl='';importKind='';sourceStamp='';warnings=[];recognizedText='';selectedVenue='';recognizedTotal=0;
 }
 function ensureContext(ctx){
   if(contextDate!==ctx.date){reset();contextDate=ctx.date;}
 }
 function setMessage(s,isError=false){message=s;error=!!isError;}
 function toRow(input,ctx,kind,reason){
   const matches=ctx.races.filter(r=>r.venue===input.venue&&r.race===input.race);
   const forecast=matches[0]||null;
   const fullKey=key(ctx.date,input.venue,input.race);
   const official=ctx.officialResults?.[fullKey];
   const alert=ctx.alerts?.[fullKey];
   const mismatch=official&&official.verified&&
     (official.finish!==input.finish||official.payout_per_100!==input.payout_per_100);
   const summary=(!forecast?'発走前予想なし':alert?'返還・中止・異常の要確認':
     mismatch?'現在の公式結果と不一致':
     official?.verified?'公式照合済み':'照合候補');
   const blocked=!forecast||!!alert||!!mismatch||!!input.review||
     !validFinish(input.finish)||!validPayout(input.payout_per_100)||
     !forecast.sha256&&kind==='url' || kind==='url'&&(!forecast.frozen_at_utc || !forecast.cutoff_jst);
   return {
     venue:input.venue,race:input.race,finish:input.finish||'',payout_per_100:input.payout_per_100??'',
     date:ctx.date,kind,reason:input.review||reason||'',matched:!!forecast,blocked,
     summary,officialDone:!!(official?.verified&&!mismatch&&!alert),
     source:kind==='url'?'boatrace_official_pay':'image_ocr_unverified',
     snapshot_sha256:forecast?.sha256||null,checked:!blocked&&!official?.verified,
   };
 }
 function looksRefund(value){return /返還|中止|同着|不成立|返金|取り消し|欠場|払戻なし/.test(value);}
 function parseTriplet(text){
   const v=clean(text);
   let tuples=[];
   const explicit=/([1-6])\s*[-＞>]\s*([1-6])\s*[-＞>]\s*([1-6])/g;
   for(const m of v.matchAll(explicit))tuples.push(m[1]+'-'+m[2]+'-'+m[3]);
   if(!tuples.length){
     const packed=/(?:^|[^\d])([1-6])([1-6])([1-6])(?=$|[^\d])/g;
     for(const m of v.matchAll(packed))tuples.push(m[1]+'-'+m[2]+'-'+m[3]);
   }
   tuples=[...new Set(tuples.filter(validFinish))];
   const amounts=[];
   for(const m of v.matchAll(/¥\s*([\d,]{3,})/g))amounts.push(Number(m[1].replaceAll(',','')));
   if(!amounts.length)for(const m of v.matchAll(/([\d,]{3,})\s*円/g))amounts.push(Number(m[1].replaceAll(',','')));
   const payouts=[...new Set(amounts.filter(validPayout))];
   return {finish:tuples.length===1?tuples[0]:'',payout_per_100:payouts.length===1?payouts[0]:'',
     review:looksRefund(v)?'返還・中止・同着などを検出':
       tuples.length>1||payouts.length>1?'複数候補があるので要確認':
       !tuples.length||!payouts.length?'3連単の組番・払戻が一意に読めない':''};
 }
 function explicitDate(text){
   const m=clean(text).match(/(20\d{2})[\/.年-](\d{1,2})[\/.月-](\d{1,2})日?/);
   return m?m[1]+'-'+m[2].padStart(2,'0')+'-'+m[3].padStart(2,'0'):null;
 }
 function parseLineRows(raw,ctx,venueOverride){
   const text=clean(raw).slice(0,120000),date=explicitDate(text);
   const notes=[];
   if(date&&date!==ctx.date)return {rows:[],warnings:['画像の日付 '+date+' が現在の予想日 '+ctx.date+' と違うため、反映できません。'],recognized:0};
   if(!date)notes.push('画像の日付は未確認。現在表示している予想日 '+ctx.date+' の結果として慎重に確認してね。');
   const lines=text.split(/\r?\n/).map(l=>l.trim()).filter(Boolean);
   const named=VENUES.filter(v=>text.includes(v));
   if(named.length>1&&!venueOverride)notes.push('複数開催場が写っています。文字の並びから場を判定できない行は取り込みません。');
   let venue=venueOverride|| (named.length===1?named[0]:null),chunks=[],part=null;
   function finishPart(){if(part){chunks.push(part);part=null;}}
   for(const line of lines){
     const inLine=VENUES.filter(v=>line.includes(v));
     if(inLine.length===1){finishPart();venue=inLine[0];}
     else if(inLine.length>1&&!venueOverride){finishPart();venue=null;continue;}
     const match=line.match(/(?:^|\s)(1[0-2]|[1-9])\s*(?:R|レース)\b/i);
     if(match){
       finishPart();
       const inline=VENUES.filter(v=>line.includes(v));
       const assigned=inline.length===1?inline[0]:venue;
       if(assigned)part={venue:assigned,race:Number(match[1]),text:line};
     }else if(part)part.text+=' '+line;
   }
   finishPart();
   const seen=new Map();
   for(const part of chunks){
     if(venueOverride&&part.venue!==venueOverride){notes.push('指定した開催場と画像の開催場が異なる行は除外しました。');continue;}
     if(!part.venue||part.race<1||part.race>12)continue;
     const check=parseTriplet(part.text);
     const item={...part,...check};
     const id=part.venue+'|'+part.race;
     if(seen.has(id)){seen.get(id).review='同じ開催場・Rが複数回検出されたため要確認';continue;}
     seen.set(id,item);
   }
   return {rows:[...seen.values()].sort((a,b)=>VENUES.indexOf(a.venue)-VENUES.indexOf(b.venue)||a.race-b.race),
     warnings:notes,recognized:chunks.length};
 }
 function flattenedWords(blocks){
   const result=[];
   for(const block of blocks||[]){
     for(const para of block.paragraphs||[])for(const line of para.lines||[])
       for(const word of line.words||[]){
         const b=word.bbox||{},text=clean(word.text||'').trim();
         if(text&&Number.isFinite(b.x0)&&Number.isFinite(b.y0))
           result.push({text,x:(b.x0+b.x1)/2,y:(b.y0+b.y1)/2});
       }
   }
   return result;
 }
 function parseColumnLayout(blocks,ctx){
   const words=flattenedWords(blocks);
   if(words.length<18)return {rows:[],warnings:[]};
   const venues=[];
   for(const v of VENUES){
     const m=words.find(w=>w.text.includes(v));
     if(m)venues.push({venue:v,x:m.x,y:m.y});
   }
   if(venues.length<2)return {rows:[],warnings:[]};
   venues.sort((a,b)=>a.x-b.x);
   const upper=Math.min(...venues.map(v=>v.y));
   const raceTags=words.map(w=>{
     const m=w.text.match(/^(1[0-2]|[1-9])\s*R$/i);
     return m?{race:Number(m[1]),x:w.x,y:w.y}:null;
   }).filter(Boolean).filter(w=>w.y>upper);
   const byRace=new Map();
   for(const rt of raceTags){const list=byRace.get(rt.race)||[];list.push(rt);byRace.set(rt.race,list);}
   if(byRace.size<2)return {rows:[],warnings:[]};
   const centers=[...byRace.entries()].map(([race,points])=>({
     race,y:points.reduce((s,p)=>s+p.y,0)/points.length
   })).sort((a,b)=>a.y-b.y);
   const output=[],issues=[];
   for(const [vi,v] of venues.entries()){
     const left=vi===0?-Infinity:(venues[vi-1].x+v.x)/2;
     const right=vi===venues.length-1?Infinity:(v.x+venues[vi+1].x)/2;
     for(let i=0;i<centers.length;i++){
       const r=centers[i],up=i===0?upper+4:(centers[i-1].y+r.y)/2;
       const down=i===centers.length-1?r.y+36:(centers[i+1].y+r.y)/2;
       const cell=words.filter(w=>w.x>=left&&w.x<right&&w.y>=up&&w.y<down&&
         !/^(1[0-2]|[1-9])R$/.test(w.text));
       if(!cell.length)continue;
       const line=cell.sort((a,b)=>a.y-b.y||a.x-b.x).map(w=>w.text).join(' ');
       const parsed=parseTriplet(line);
       if(!parsed.finish&&!parsed.payout_per_100)continue;
       output.push({venue:v.venue,race:r.race,...parsed,
         review:parsed.review||'複数場の画像位置から推定。元画像で場・Rを必ず確認',
         line});
     }
   }
   if(output.length)issues.push('複数場の画像を位置情報で分割しました。OCRの列ずれが起きるため、全行の場・R・配当を確認してから反映してください。');
   return {rows:output,warnings:issues};
 }
 function parseImageResults(raw,ctx,blocks,venueOverride){
   const line=parseLineRows(raw,ctx,venueOverride);
   const col=!venueOverride?parseColumnLayout(blocks,ctx):{rows:[],warnings:[]};
   const all=new Map();
   for(const x of col.rows)all.set(x.venue+'|'+x.race,x);
   for(const x of line.rows)if(!all.has(x.venue+'|'+x.race))all.set(x.venue+'|'+x.race,x);
   const dateConflict=line.warnings.some(x=>x.includes('日付')&&x.includes('違う'));
   if(dateConflict)return {...line,rows:[]};
   return {rows:[...all.values()].sort((a,b)=>VENUES.indexOf(a.venue)-VENUES.indexOf(b.venue)||a.race-b.race),
     recognized:Math.max(line.recognized,col.rows.length),warnings:line.warnings.concat(col.warnings)};
 }
 function officialURL(raw,ctx){
   if(!window.BoatResultReader?.parseOfficialUrl)throw Error('公式URLを解析するモジュールがありません');
   const info=window.BoatResultReader.parseOfficialUrl(raw.trim());
   if(info.date!==ctx.date)throw Error('URLの対象日 '+info.date+' が表示中の予想日 '+ctx.date+' と異なります。');
   return info;
 }
 function officialRows(snapshot,ctx,info){
   if(!snapshot||snapshot.status!=='verified_by_server_fetch'||
      snapshot.evidence_type!=='official_boatrace_pay_snapshot'||snapshot.date!==ctx.date||
      !snapshot.source_url?.startsWith('https://www.boatrace.jp/owpc/pc/race/pay?hd='+ctx.date.replaceAll('-','')))
      throw Error('公式払戻データの形式・日付・取得元を確認できません');
   const proposed=[],scores=snapshot.results||{};
   for(const [index,payout] of Object.entries(scores)){
     const keyMatch=index.match(/^([1-9]|1\d|2[0-4])-(1[0-2]|[1-9])$/);
     if(!keyMatch)continue;
     const venue=VENUES[Number(keyMatch[1])-1],race=Number(keyMatch[2]);
     if(info.venue&&venue!==info.venue||info.race&&race!==info.race)continue;
     if(!validFinish(payout.finish)||!validPayout(payout.payout_per_100))continue;
     proposed.push({venue,race,finish:payout.finish,payout_per_100:payout.payout_per_100,
       review:snapshot.conflicts?.[index]||snapshot.reviews?.[index]?'訂正・異常払戻の要確認':''});
   }
   return {proposed,officialTotal:Object.keys(scores).length,
     needsReview:Object.keys(snapshot.reviews||{}).length+
       Object.keys(snapshot.cancellations||{}).length+Object.keys(snapshot.conflicts||{}).length,
     updated:snapshot.retrieved_at_utc};
 }
 function imageSelected(file,ctx){
   ensureContext(ctx);
   if(!file){imageFile=null;return;}
   if(!['image/png','image/jpeg','image/webp'].includes(file.type))
     throw Error('PNG・JPEG・WebPの結果画像に対応しています。HEICはiPhoneでJPEGに変換してください。');
   if(!Number.isFinite(file.size)||file.size<1||file.size>12*1024*1024)
     throw Error('画像は12MB以下にしてね');
   if(imageUrl&&typeof URL!=='undefined'&&URL.revokeObjectURL)URL.revokeObjectURL(imageUrl);
   imageFile=file;imageUrl=URL.createObjectURL(file);
   rows=[];recognizedTotal=0;importKind='image';
   setMessage('画像を選択したよ。次に「画像を一括読み取り」を押してね。');
 }
 function setVenue(v,ctx){
   ensureContext(ctx);
   if(v&& !VENUES.includes(v))throw Error('開催場が不正です');
   selectedVenue=v;rows=[];recognizedTotal=0;
 }
 function loadOcr(){
   if(window.Tesseract?.createWorker)return Promise.resolve();
   if(scriptPromise)return scriptPromise;
   scriptPromise=new Promise((resolve,reject)=>{
     const el=document.createElement('script');el.src=OCR_CDN;el.async=true;
     el.onload=()=>window.Tesseract?.createWorker?resolve():reject(Error('OCRを起動できませんでした'));
     el.onerror=()=>reject(Error('OCRライブラリをダウンロードできませんでした'));
     document.head.appendChild(el);
   }).catch(e=>{scriptPromise=null;throw e});
   return scriptPromise;
 }
 async function readImage(ctx,onUpdate){
   ensureContext(ctx);
   if(working||!imageFile)return;
   working=true;setMessage('日本語OCRの準備中。初回は通信が必要です。');onUpdate();
   let worker;
   try{
     await loadOcr();
     worker=await window.Tesseract.createWorker('jpn+eng',1);
     const o=await worker.recognize(imageFile,{}, {text:true,blocks:true});
     const parsed=parseImageResults(o?.data?.text||'',ctx,o?.data?.blocks||[],selectedVenue);
     recognizedText=String(o?.data?.text||'').slice(0,8000);
     warnings=parsed.warnings;recognizedTotal=parsed.recognized;
     rows=parsed.rows.map(x=>toRow(x,ctx,'image'));
     importKind='image';sourceStamp='';
     setMessage(rows.length+'Rを候補として検出したよ。画像を見ながら各行を確認して、まとめて反映してね。');
   }catch(e){rows=[];setMessage('画像の一括OCRに失敗しました：'+e.message+'。文字をコピーして下の欄に貼り付けることもできます。',true);}
   finally{try{await worker?.terminate()}catch{}working=false;onUpdate();}
 }
 function parseText(text,ctx){
   ensureContext(ctx);
   const p=parseImageResults(text,ctx,[],selectedVenue);
   recognizedText=String(text||'').slice(0,8000);
   warnings=p.warnings;recognizedTotal=p.recognized;
   rows=p.rows.map(x=>toRow(x,ctx,'image'));importKind='image';sourceStamp='';
   setMessage(rows.length+'Rを文字情報から抽出したよ。場・R・着順・配当を確認してね。');
 }
 async function readURL(text,ctx,onUpdate){
   ensureContext(ctx);
   if(working)return;
   inputUrl=String(text||'').trim();rows=[];working=true;setMessage('公式払戻の公開済み一括データを確認中…');onUpdate();
   try{
     const info=officialURL(inputUrl,ctx);
     const url='./data/live/official-pay/'+info.date+'.json?refresh='+Date.now();
     const res=await fetch(url,{cache:'no-store'});
     if(!res.ok)throw Error('この日の全場公式払戻データはまだ公開されていません。上の「結果を更新」で最新を確認してね。');
     const snap=await res.json();
     const parsed=officialRows(snap,ctx,info);
     rows=parsed.proposed.map(x=>toRow(x,ctx,'url'));
     importKind='url';recognizedTotal=parsed.officialTotal;sourceStamp=parsed.updated||'';
     warnings=parsed.needsReview?['返還・中止・訂正確認待ちが'+parsed.needsReview+'件あるため、これらは自動照合しません。']:[];
     const match=rows.filter(r=>r.matched).length;
     setMessage('公式一覧 '+recognizedTotal+'Rから、発走前予想と照合できる'+match+'Rを検出したよ。公開済みデータの取得時刻を確認してね。');
   }catch(e){rows=[];setMessage(e.message||'URLの読み取りに失敗しました',true);}
   finally{working=false;onUpdate();}
 }
 function label(row){
   if(!row.matched)return '発走前予想なし';
   if(row.blocked)return row.summary;
   if(row.officialDone)return '公式照合済み';
   return row.kind==='url'?'公式データ確認・反映可能':'画像OCR（未検証）';
 }
 function render(ctx){
   ensureContext(ctx);
   const count=rows.length,match=rows.filter(r=>r.matched).length;
   const selected=rows.filter(r=>r.checked&&!r.blocked&&!r.officialDone).length;
   let html='<section class="card card-pad batch-reader" aria-label="全レース一括結果照合">';
   html+='<div class="section-head"><div><h2 class="section-title">📷 全レース結果をまとめて照合</h2><p class="batch-subhead">1Rずつ入力せず、複数場・最大12Rずつ確認</p></div><span class="batch-badge">一括読取</span></div>';
   html+='<p class="batch-help">一日の公式払戻一覧URL、または全レースの結果画像を入力すると、読めた行をまとめて表示するよ。<strong>必ず内容を確認してから</strong>一括反映してね。</p>';
   html+='<div class="batch-grid"><div class="batch-source"><strong>① 結果一覧画像</strong>'+
     '<input type="file" id="batch-image" accept="image/png,image/jpeg,image/webp" aria-label="複数レースの結果画像を選択"/>'+
     (imageUrl?'<div class="batch-preview"><img src="'+esc(imageUrl)+'" alt="選択した結果一覧画像"/><small>'+esc(imageFile?.name)+'</small></div>':'')+
     '<label class="batch-label" for="batch-venue">画像の開催場</label>'+
     '<select id="batch-venue"><option value="">自動判定（複数場も可）</option>'+
     VENUES.map(v=>'<option value="'+v+'" '+(selectedVenue===v?'selected':'')+'>'+v+'</option>').join('')+'</select>'+
     '<button type="button" class="btn btn-soft" data-action="batch-image-read" '+(imageFile&&!working?'':'disabled')+'>🔍 画像を一括読み取り</button>'+
     '<p class="batch-hint">端末内でOCR。画像はBOAT LABに送信しません。初回はOCRソフト・日本語データのダウンロードが必要。複数場の表では列ずれに注意。</p></div>';
   html+='<div class="batch-source"><strong>② BOATRACE公式払戻一覧URL</strong>'+
     '<input type="url" id="batch-url" placeholder="https://www.boatrace.jp/owpc/pc/race/pay?hd=20261023" value="'+esc(inputUrl)+'" inputmode="url" autocomplete="off"/>'+
     '<button type="button" class="btn btn-soft" data-action="batch-url-read" '+(working?'disabled':'')+'>🔗 公式結果をまとめて確認</button>'+
     '<p class="batch-hint">公式URLの日付をチェックし、GitHub側で公式ページを取得・公開したデータを読む方式。公開前の結果をその場で直接スクレイピングするものではありません。</p>'+
     '<details class="batch-fallback"><summary>画像からコピーした文字を貼って読み取る</summary>'+
     '<textarea id="batch-ocr-text" rows="4" placeholder="例：大村&#10;1R 1-2-3 ¥1,250&#10;2R 3-1-2 ¥4,560"></textarea>'+
     '<button type="button" class="btn btn-soft" data-action="batch-text-read">貼り付けた結果を解析</button></details></div></div>';
   if(working)html+='<p class="batch-status" role="status">⏳ 解析中…</p>';
   if(message)html+='<p class="batch-status '+(error?'is-error':'')+'" role="status">'+esc(message)+'</p>';
   if(sourceStamp)html+='<p class="batch-hint">公式結果取得時刻：'+esc(sourceStamp)+'（UTC）。公式サイトの最新公開分とは時間差がある場合があります。</p>';
   if(warnings.length)html+='<div class="batch-warnings">'+warnings.map(w=>'<p>⚠ '+esc(w)+'</p>').join('')+'</div>';
   if(count){
     html+='<div class="batch-count"><b>'+count+'R 抽出</b><span>発走前予想あり '+match+'R ／ 反映候補 '+selected+'R</span></div>';
     html+='<div class="batch-table-scroll"><table class="batch-table"><thead><tr><th>選択</th><th>場・R</th><th>3連単</th><th>100円払戻</th><th>判定</th></tr></thead><tbody>';
     rows.forEach((r,i)=>{
       const can=!r.blocked&&!r.officialDone;
       html+='<tr data-batch-row="'+i+'" class="'+(r.blocked?'batch-unverified':r.officialDone?'batch-verified':'')+'">'+
         '<td><input type="checkbox" data-batch-check '+(r.checked?'checked':'')+' '+(can?'':'disabled')+' aria-label="'+esc(r.venue)+' '+r.race+'Rを反映"/></td>'+
         '<td><b>'+esc(r.venue)+'</b><span>'+r.race+'R</span></td>'+
         '<td><input type="text" data-batch-finish value="'+esc(r.finish)+'" '+(can?'':'readonly')+' placeholder="1-2-3" aria-label="'+esc(r.venue)+' '+r.race+'R 3連単"/></td>'+
         '<td><input type="number" data-batch-pay value="'+esc(r.payout_per_100)+'" '+(can?'':'readonly')+' min="100" max="10000000" step="10" aria-label="'+esc(r.venue)+' '+r.race+'R 100円払戻"/></td>'+
         '<td><small>'+esc(label(r))+'</small>'+(r.reason?'<em>'+esc(r.reason)+'</em>':'')+'</td></tr>';
     });
     html+='</tbody></table></div>'+
       '<div class="batch-actions"><button type="button" class="btn btn-primary" data-action="batch-apply" '+(selected&&!working?'':'disabled')+'>✓ 確認した結果を一括反映</button>'+
       '<button type="button" class="btn btn-soft" data-action="batch-clear">候補を消す</button></div>'+
       '<p class="batch-hint">'+(importKind==='image'?'画像由来の結果は「暫定・未確認」として端末内だけに保存し、公式確認済み成績には加えません。':'公式URLからの結果はサーバー側で取得・検証済みの払戻のみ反映します。')+
       ' 返還・中止・同着や不一致がある行は除外。後から発走前買い目を作ることはありません。</p>';
   }
   return html+'</section>';
 }
 function selectedUpdates(ctx,root){
   ensureContext(ctx);
   const checks=root?.querySelectorAll?.('[data-batch-row]')||[];
   const updates=[],invalid=[];
   for(const tr of checks){
     const i=Number(tr.dataset.batchRow),r=rows[i];
     if(!r||r.blocked||r.officialDone)continue;
     const chosen=tr.querySelector('[data-batch-check]')?.checked;
     if(!chosen)continue;
     const val=clean(tr.querySelector('[data-batch-finish]')?.value||'').replace(/\s+/g,'');
     const payout=Number(tr.querySelector('[data-batch-pay]')?.value||'');
     if(!validFinish(val)||!validPayout(payout)){invalid.push(r.venue+' '+r.race+'R');continue;}
     const forecast=ctx.races.find(x=>x.venue===r.venue&&x.race===r.race);
     const k=key(ctx.date,r.venue,r.race);
     const official=ctx.officialResults?.[k];
     if(!forecast||ctx.alerts?.[k]||
        official?.verified&&(official.finish!==val||official.payout_per_100!==payout)){
       invalid.push(r.venue+' '+r.race+'R（公式データ不一致）');continue;
     }
     // Only already-published server-confirmed snapshots may be labelled official.
     if(r.kind==='url'&&(r.finish!==val||r.payout_per_100!==payout)){
       invalid.push(r.venue+' '+r.race+'R（公式データは編集不可）');continue;
     }
     updates.push({key:k,venue:r.venue,race:r.race,finish:val,payout_per_100:payout,
       kind:r.kind,snapshot_sha256:forecast.sha256||null,source_url:inputUrl,
       source_timestamp:sourceStamp});
   }
   if(invalid.length)throw Error('未完成・不一致の行を確認してね：'+invalid.slice(0,4).join('、'));
   if(!updates.length)throw Error('反映する行を選択してね。すでに公式照合済みの行は更新しません。');
   return updates;
 }
 function clearResults(ctx){ensureContext(ctx);rows=[];warnings=[];recognizedTotal=0;setMessage('読み取り候補をクリアしました。');}
 function snapshot(){return {working,message,error,rows:rows.map(x=>({...x})),warnings:[...warnings],kind:importKind,recognizedTotal,sourceStamp};}
 window.BoatBatchReader={render,reset,ensureContext,imageSelected,setVenue,readImage,parseText,readURL,
   selectedUpdates,clearResults,snapshot,parseLineRows,parseImageResults,parseColumnLayout,officialRows,validFinish,validPayout};
})();
