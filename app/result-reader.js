/* BOAT LAB result-evidence import: local image OCR + official-URL lookup.
 * OCR is strictly a DRAFT requiring user confirmation, never official verification.
 * Official URLs are validated and matched to already published official payout
 * records; browser-side CORS prevents us from claiming live official page scraping.
 * No images are uploaded to BOAT LAB. OCR binaries/language data use public CDN.
 */
(function(){
  'use strict';
  const OCR_CDN='https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js';
  const VENUES=['桐生','戸田','江戸川','平和島','多摩川','浜名湖','蒲郡','常滑','津','三国','びわこ','住之江','尼崎','鳴門','丸亀','児島','宮島','徳山','下関','若松','芦屋','福岡','唐津','大村'];
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const isCombo=x=>/^[1-6]-[1-6]-[1-6]$/.test(String(x))&&new Set(String(x).split('-')).size===3;
  const validPay=x=>Number.isSafeInteger(x)&&x>=100&&x<=10000000&&x%10===0;
  let file=null,previewUrl=null,reading=false,candidate=null,notice='',isError=false,sourceUrl='',currentRaceKey=null;
  let injectedScript=null;

  function clean(text){
    return String(text||'').normalize('NFKC')
      .replace(/[ー－−–—‐―→➞➡︎▶︎-]/g,'-')
      .replace(/[￥]/g,'¥')
      .replace(/[，]/g,',');
  }
  function parsePayout(text){
    const lines=clean(text).split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
    const tagged=lines.flatMap((line,i)=>/3\s*連\s*単/.test(line)?
      [lines.slice(i,Math.min(lines.length,i+4)).join(' ')]:[]);
    const source=tagged.length?tagged.join('\n'):lines.join('\n');
    const pattern=/([1-6])\s*[->\s]\s*([1-6])\s*[-→>\s]\s*([1-6])/g;
    let matches=[...source.matchAll(pattern)].map(m=>[m[1],m[2],m[3]].join('-')).filter(isCombo);
    matches=[...new Set(matches)];
    const payoutCandidates=[];
    const marked=[...source.matchAll(/[¥]\s*([\d,]{3,})/g)];
    for(const x of marked)payoutCandidates.push(Number(x[1].replaceAll(',','')));
    if(!payoutCandidates.length){
      for(const x of source.matchAll(/(\d[\d,]{2,})\s*円/g))payoutCandidates.push(Number(x[1].replaceAll(',','')));
    }
    const pays=[...new Set(payoutCandidates.filter(validPay))];
    return {finish:matches.length===1?matches[0]:null,
      payout_per_100:pays.length===1?pays[0]:null,
      ambiguous:matches.length>1||pays.length>1,
      marked3tf:tagged.length>0};
  }
  function parseOcrText(raw,context){
    const text=clean(raw).slice(0,16000);
    const payout=parsePayout(text);
    const warnings=[];
    if(/返還|不成立|中止|同着|欠場|無効|払い戻しなし/.test(text))warnings.push('返還・中止・同着などの表示を検出。通常の単一3連単ではない可能性があります。');
    const venueMatches=VENUES.filter(v=>text.includes(v));
    if(venueMatches.length===1&&venueMatches[0]!==context.venue)
      warnings.push('画像内の競艇場「'+venueMatches[0]+'」と選択した「'+context.venue+'」が違います。');
    if(venueMatches.length>1)warnings.push('画像内に複数の競艇場名があります。');
    const taggedRace=[...text.matchAll(/(?:^|[^\d])([1-9]|1[0-2])\s*(?:R|レース)/gm)].map(m=>Number(m[1]));
    const foundRace=[...new Set(taggedRace)];
    if(foundRace.length===1&&foundRace[0]!==Number(context.race))
      warnings.push('画像内の'+foundRace[0]+'Rと選択した'+context.race+'Rが一致しません。');
    if(foundRace.length>1)warnings.push('画像に複数のレース番号があります。');
    const dates=[...text.matchAll(/(20\d{2})[年\/.-](\d{1,2})[月\/.-](\d{1,2})日?/g)]
      .map(m=>[m[1],m[2].padStart(2,'0'),m[3].padStart(2,'0')].join('-'));
    const uniqDates=[...new Set(dates)];
    if(uniqDates.length===1&&uniqDates[0]!==context.date)
      warnings.push('画像内の日付が予想データの'+context.date+'と一致しません。');
    if(uniqDates.length>1)warnings.push('画像に複数の日付があります。');
    if(payout.ambiguous)warnings.push('複数の組番や配当が読み取れました。対応する3連単を確認してください。');
    if(!payout.marked3tf)warnings.push('「3連単」の見出しを認識できませんでした。払戻種別を必ず確認してください。');
    if(!payout.finish)warnings.push('3連単の着順を一意に特定できませんでした。');
    if(payout.payout_per_100===null)warnings.push('100円あたりの払戻金を一意に特定できませんでした。');
    return {...payout,venue:venueMatches.length===1?venueMatches[0]:null,
      race:foundRace.length===1?foundRace[0]:null,
      date:uniqDates.length===1?uniqDates[0]:null,
      warnings,raw_excerpt:text.slice(0,2000),
      source:'image_ocr',status:'unconfirmed'};
  }
  function parseOfficialUrl(raw){
    let url;
    if(typeof raw!=='string'||raw.length>2000)throw Error('URLを確認してね');
    try{url=new URL(raw);}catch{throw Error('https://www.boatrace.jp/ の公式結果URLを貼り付けてね');}
    if(url.protocol!=='https:'||!['boatrace.jp','www.boatrace.jp'].includes(url.hostname)||
       url.username||url.password||url.port)throw Error('BOATRACE公式のhttps URLだけ対応しています');
    if(!['/owpc/pc/race/pay','/owpc/pc/race/raceresult'].includes(url.pathname))
      throw Error('BOATRACE公式の払戻ページまたはレース結果ページだけ対応しています');
    const hd=url.searchParams.getAll('hd');
    if(hd.length!==1||!/^20\d{6}$/.test(hd[0]))throw Error('URLの日付（hd=YYYYMMDD）が必要です');
    const y=Number(hd[0].slice(0,4)),mo=Number(hd[0].slice(4,6)),day=Number(hd[0].slice(6,8));
    const actual=new Date(Date.UTC(y,mo-1,day));
    if(actual.getUTCFullYear()!==y||actual.getUTCMonth()!==mo-1||actual.getUTCDate()!==day)
      throw Error('URLの日付が正しくありません');
    const date=hd[0].slice(0,4)+'-'+hd[0].slice(4,6)+'-'+hd[0].slice(6);
    const isRace=url.pathname.endsWith('/raceresult');
    let race=null,venue=null;
    if(isRace){
      const j=url.searchParams.getAll('jcd'),r=url.searchParams.getAll('rno');
      if(j.length!==1||r.length!==1||!/^0?\d{1,2}$/.test(j[0])||!/^\d{1,2}$/.test(r[0])||
         Number(j[0])<1||Number(j[0])>24||Number(r[0])<1||Number(r[0])>12)
        throw Error('結果URLには正しい競艇場コード（jcd）とR番号（rno）が必要です');
      venue=VENUES[Number(j[0])-1];race=Number(r[0]);
    }
    return {date,venue,race,type:isRace?'raceresult':'pay',url:url.href};
  }
  function lookupOfficial(info,context,officialResults,alerts){
    if(info.date!==context.date)throw Error('URLの日付とBOAT LABの対象日が違います。この日の保存済み予想を開いてください');
    if(info.venue&&info.venue!==context.venue)throw Error('URLの競艇場が選択レースと違います（'+info.venue+'）');
    if(info.race&&info.race!==Number(context.race))throw Error('URLのレース番号が選択中の'+context.race+'Rと違います');
    const key=context.date+'|'+context.venue+'|'+context.race;
    if(alerts?.[key])throw Error('公式結果が返還・中止・訂正待ちです。自動照合には使えません');
    const payout=officialResults?.[key];
    if(!payout||payout.verified!==true||payout.source!=='boatrace_official_pay'||
       !isCombo(payout.finish)||!validPay(payout.payout_per_100))
      return {found:false,message:'このレースの公式払戻は公開済みBOAT LABデータにまだありません。「結果を更新」で確認するか、公式ページの画像を添付してね。'};
    if(context.sha256&&payout.snapshot_sha256&&context.sha256!==payout.snapshot_sha256)
      throw Error('発走前固定予想の照合IDが一致しません。公式データを保留します');
    return {found:true,finish:payout.finish,payout_per_100:payout.payout_per_100,
      status:'official_verified',source:'boatrace_official_pay',warnings:[],url:info.url};
  }

  function contextKey(ctx){return ctx.date+'|'+ctx.venue+'|'+ctx.race;}
  function reset(){
    if(previewUrl&&typeof URL!=='undefined'&&URL.revokeObjectURL)URL.revokeObjectURL(previewUrl);
    file=null;previewUrl=null;reading=false;candidate=null;notice='';isError=false;sourceUrl='';
  }
  function ensureContext(ctx){
    const key=contextKey(ctx);
    if(currentRaceKey!==key){reset();currentRaceKey=key;}
  }
  function fileSelected(selected,ctx){
    ensureContext(ctx);candidate=null;
    if(!selected){reset();return;}
    const mime=String(selected.type||'');
    if(!['image/png','image/jpeg','image/webp'].includes(mime))
      throw Error('画像はPNG・JPEG・WebPに対応しています。iPhoneのHEIC画像はJPEGに変換してね');
    if(!Number.isFinite(selected.size)||selected.size<1||selected.size>8*1024*1024)
      throw Error('画像ファイルは8MB以下にしてね');
    if(previewUrl&&URL.revokeObjectURL)URL.revokeObjectURL(previewUrl);
    file=selected;previewUrl=URL.createObjectURL(selected);
    notice='画像を選択しました。「画像を読み取る」を押してね。';isError=false;
  }
  function setNotice(message,error){notice=message;isError=!!error;}
  function snapshot(){return {fileName:file?.name||null,reading,candidate,notice,isError,sourceUrl};}
  function render(ctx){
    ensureContext(ctx);
    let html='<section class="card card-pad result-reader" aria-label="画像と公式URLで結果を照合">'+
      '<div class="section-head"><h2 class="section-title">📷 画像・URLから結果を読み取る</h2><span class="result-reader-tag">確認して反映</span></div>'+
      '<p class="result-reader-help">選択中の<strong>'+esc(ctx.venue)+' '+ctx.race+'R</strong>の結果を読み取るよ。公式照合済みの結果は上書きしません。</p>'+
      '<div class="result-reader-steps">'+
      '<div class="result-reader-step"><label for="result-image-file">① スクショ・結果画像</label>'+
      '<input id="result-image-file" type="file" accept="image/png,image/jpeg,image/webp" aria-label="結果画像を選択"/>'+
      (previewUrl?'<div class="result-reader-preview"><img src="'+esc(previewUrl)+'" alt="選択した結果画像のプレビュー"/><span>'+esc(file?.name)+'</span></div>':'')+
      '<button type="button" class="btn btn-soft" data-action="read-result-image" '+(!file||reading?'disabled':'')+'>'+(reading?'文字を認識中…':'🔍 画像を読み取る')+'</button>'+
      '<p class="result-reader-hint">端末上で日本語・数字をOCR解析。初回はOCRエンジンと言語データのダウンロードが必要（通信環境によっては利用不可）。画像そのものはBOAT LABのサーバーにアップロードしません。</p></div>'+
      '<div class="result-reader-step"><label for="result-official-url">② BOATRACE公式の結果URL</label>'+
      '<input id="result-official-url" type="url" placeholder="https://www.boatrace.jp/owpc/pc/race/raceresult?..." value="'+esc(sourceUrl)+'" inputmode="url" autocapitalize="off" autocomplete="off"/>'+
      '<button type="button" class="btn btn-soft" data-action="read-result-url" '+(reading?'disabled':'')+'>🔗 URLで照合</button>'+
      '<p class="result-reader-hint">公式の払戻ページ・レース結果URLだけ対応。URLから日付・場・Rを照合し、BOAT LABに公開済みの公式払戻から結果を表示するよ。ブラウザから公式サイトを直接取得する機能ではありません。</p></div></div>';
    if(notice)html+='<div class="result-reader-notice '+(isError?'error':'')+'" role="status">'+esc(notice)+'</div>';
    if(candidate){
      const v=candidate,blocked=v.warnings?.some(w=>/返還|中止|同着|違い|一致しません|複数の/.test(w));
      const verified=v.status==='official_verified';
      html+='<div class="result-reader-candidate"><strong>'+(verified?'✅ 公開済み公式結果を確認':'📝 OCRで読み取った候補（未確定）')+'</strong>'+
        '<dl><div><dt>対象</dt><dd>'+esc(ctx.venue)+' '+ctx.race+'R</dd></div>'+
        '<div><dt>3連単</dt><dd>'+esc(v.finish||'未認識')+'</dd></div>'+
        '<div><dt>100円払戻</dt><dd>'+(v.payout_per_100==null?'未認識':Number(v.payout_per_100).toLocaleString('ja-JP')+'円')+'</dd></div></dl>';
      if(v.warnings?.length)html+='<div class="result-reader-warnings">'+v.warnings.map(x=>'<p>⚠ '+esc(x)+'</p>').join('')+'</div>';
      if(!verified){
        html+='<p class="result-reader-hint">OCRの文字認識は誤る場合があります。必ず元画像と照らし、正しい開催場・R・着順・払戻を確認してね。反映後も正式な公式照合成績には含まれません。</p>'+
          '<button type="button" class="btn btn-primary" data-action="apply-result-read" '+(blocked?'disabled':'')+'>✓ 候補を入力フォームに反映</button>';
        if(blocked)html+='<p class="result-reader-hint">この画像は対象が一致しないか複数候補があるため、自動反映を止めています。フォームで元画像を確認して手入力してね。</p>';
      }else html+='<p class="result-reader-hint">BOAT LABの公式結果データで照合済み。手入力の反映は不要です。</p>';
      html+='</div>';
    }
    return html+'</section>';
  }
  function loadScript(){
    if(window.Tesseract?.createWorker)return Promise.resolve();
    if(injectedScript)return injectedScript;
    injectedScript=new Promise((resolve,reject)=>{
      const script=document.createElement('script');
      script.src=OCR_CDN;script.async=true;
      script.onload=()=>window.Tesseract?.createWorker?resolve():reject(Error('OCRライブラリを読み込めませんでした'));
      script.onerror=()=>reject(Error('OCRライブラリの通信に失敗しました'));
      document.head.appendChild(script);
    }).catch(err=>{injectedScript=null;throw err;});
    return injectedScript;
  }
  async function readImage(ctx,onUpdate){
    ensureContext(ctx);
    if(!file||reading)return;
    reading=true;setNotice('OCRを準備中です。初回は日本語データの読込に通信が必要です。',false);onUpdate();
    let worker;
    try{
      await loadScript();
      worker=await window.Tesseract.createWorker('jpn+eng',1,{
        logger:progress=>{
          if(!reading)return;
          if(progress.status==='recognizing text'&&Number.isFinite(progress.progress)){
            setNotice('画像を読み取り中… '+Math.floor(progress.progress*100)+'%',false);
            onUpdate();
          }
        }
      });
      const result=await worker.recognize(file);
      const extracted=String(result?.data?.text||'');
      candidate=parseOcrText(extracted,ctx);
      setNotice('画像の文字認識が終わったよ。下に表示された候補と元画像を確認してね。',false);
    }catch(error){
      candidate=null;
      setNotice('画像を読み取れませんでした。通信環境を確認するか、画像を見ながら手入力してね。（'+(error?.message||'OCR失敗')+'）',true);
    }finally{
      try{await worker?.terminate()}catch{}
      reading=false;onUpdate();
    }
  }
  function useUrl(text,ctx,officialResults,alerts){
    ensureContext(ctx);sourceUrl=String(text||'').trim();candidate=null;
    try{
      const parsed=parseOfficialUrl(sourceUrl);
      const match=lookupOfficial(parsed,ctx,officialResults,alerts);
      if(match.found){
        candidate={...match,warnings:[]};setNotice('保存済み公式払戻と一致したよ。公式結果は上書きしません。',false);
      }else setNotice(match.message,false);
      return match;
    }catch(err){setNotice(err.message,true);return{found:false,error:err.message}}
  }
  function apply(ctx){
    ensureContext(ctx);
    if(!candidate||candidate.status==='official_verified')return null;
    const value=candidate;
    if(!isCombo(value.finish)||!validPay(value.payout_per_100))
      throw Error('着順・払戻が両方認識できていません。元画像を確認して手入力してね');
    if((value.warnings||[]).some(w=>/返還|中止|同着|違い|一致しません|複数の/.test(w)))
      throw Error('対象レースが一致しない、または異常払戻の疑いがあるため反映できません');
    setNotice('候補をフォームへ入力したよ。着順と配当を最終確認してから「暫定結果を保存」を押してね。',false);
    return {finish:value.finish,payout_per_100:value.payout_per_100};
  }
  window.BoatResultReader={parseOcrText,parseOfficialUrl,lookupOfficial,
    reset,ensureContext,fileSelected,readImage,useUrl,apply,render,snapshot};
})();
