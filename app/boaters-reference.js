/* BOAT LAB external reference: link out to BOATERS, NEVER fetch or scrape it.
 * BOATERS Terms §8 ban scraping/crawling (including user-triggered requests).
 * Only BOAT LAB's own previously saved race data are analyzed below.
 */
(function(){
  'use strict';
  const slugs=Object.freeze({
    '桐生':'kiryu','戸田':'toda','江戸川':'edogawa','平和島':'heiwajima',
    '多摩川':'tamagawa','浜名湖':'hamanako','蒲郡':'gamagori',
    '常滑':'tokoname','津':'tsu','三国':'mikuni','びわこ':'biwako',
    '住之江':'suminoe','尼崎':'amagasaki','鳴門':'naruto',
    '丸亀':'marugame','児島':'kojima','宮島':'miyajima',
    '徳山':'tokuyama','下関':'shimonoseki','若松':'wakamatsu',
    '芦屋':'ashiya','福岡':'fukuoka','唐津':'karatsu','大村':'omura'
  });
  function linkFor(venue,date,race){
    const slug=slugs[venue];
    if(!slug || !/^\d{4}-\d{2}-\d{2}$/.test(String(date)) || !Number.isInteger(race)||race<1||race>12)
      return 'https://boaters-boatrace.com/race';
    return 'https://boaters-boatrace.com/race/'+slug+'/'+date+'/'+race+'R/race-detail';
  }
  function escapeHtml(value){
    return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }
  function n(v){return v===null||v===undefined||v===''?null:
    (typeof v==='number'&&Number.isFinite(v)?v:Number.isFinite(Number(v))?Number(v):null);}
  function itemCompare(r,field,ascending){
    const values=Array.isArray(r.racers)?r.racers.map(x=>({
      lane:Number(x.lane), name:String(x.name||''), value:n(x[field])
    })).filter(x=>x.lane>=1&&x.lane<=6&&x.value!==null):[];
    values.sort((a,b)=>ascending?a.value-b.value:a.value-b.value);
    if(!ascending)values.reverse();
    return values.slice(0,3);
  }
  function ranking(label,items,suffix,digits){
    if(!items.length)return '<div class="external-row"><span>'+escapeHtml(label)+'</span><b>未取得</b></div>';
    return '<div class="external-rank"><strong>'+escapeHtml(label)+'</strong><div>'+
      items.map((x,i)=>'<span class="external-rank-pill">'+
        (i+1)+'位 '+x.lane+'号艇 '+escapeHtml(x.value.toFixed(digits))+escapeHtml(suffix)+'</span>').join('')+
      '</div></div>';
  }
  function analysisHTML(r){
    const exp=Array.isArray(r.racers)&&r.racers.some(x=>n(x.exhibition_time)!==null);
    let html='<div class="external-analysis">'+
      '<div class="external-analysis-head"><b>取得済みデータの比較</b><span>BOAT LAB保存記録のみ</span></div>'+
      '<p>BOATERSのデータを取得した結果ではありません。発走前に固定した出走表・展示データから比較しています。</p>'+
      ranking('全国勝率 上位',itemCompare(r,'national_win_rate',false),'',2)+
      ranking('モーター2連対率 上位',itemCompare(r,'motor_top_2_percent',false),'%',1)+
      ranking('平均ST 速い順',itemCompare(r,'average_start_timing',true),'秒',2)+
      ranking('展示タイム 速い順',itemCompare(r,'exhibition_time',true),'秒',2)+
      ranking('展示ST 速い順（F表示は参考値）',itemCompare(r,'exhibition_st',true),'秒',2);
    const w=r.weather_observed;
    if(w&&n(w.wind_speed)!==null){
      html+='<div class="external-row"><span>展示時の場内気象</span><b>風速 '+escapeHtml(w.wind_speed)+
        'm/s ／ 波高 '+escapeHtml(w.wave_height??'—')+'cm</b></div>';
    }
    html+='<div class="notice">'+(exp?'展示値は取得時点の参考値で、レース本番の進入や結果を示すものではありません。':
      '展示値は未取得。出走表・モーター・平均STだけで比較しています。')+
      ' この分析は保存済み買い目や発走前固定記録を変更しません。</div></div>';
    return html;
  }
  window.BoatExternalReference={linkFor,analysisHTML};
})();
