/* Read-only, pre-cutoff frozen ticket breakdown. No inference or repricing. */
(function () {
  'use strict';
  const escapeHtml = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[c]);
  const amount = value => Number(value).toLocaleString('ja-JP') + '円';
  const validCombo = value => /^[1-6]-[1-6]-[1-6]$/.test(value) &&
    new Set(value.split('-')).size === 3;
  const enclosed = ['','①','②','③','④','⑤','⑥'];
  function groups(bets) {
    const heads = new Map();
    for (const bet of bets || []) {
      if (!validCombo(bet?.combination) || !Number.isFinite(bet.virtual_yen) || bet.virtual_yen < 0) continue;
      const [head, second, third] = bet.combination.split('-').map(Number);
      if (!heads.has(head)) heads.set(head, {head, second: new Map(), count: 0, total: 0});
      const h = heads.get(head);
      if (!h.second.has(second)) h.second.set(second, {second, third: [], count: 0, total: 0});
      const s = h.second.get(second);
      s.third.push({third, yen: bet.virtual_yen, combination: bet.combination});
      s.total += bet.virtual_yen; s.count++;
      h.total += bet.virtual_yen; h.count++;
    }
    return Array.from(heads.values());
  }
  function render(r, opts = {}) {
    if (!r || !Array.isArray(r.bets) || !r.bets.length) return '';
    const heads = groups(r.bets);
    if (!heads.length) return '';
    const formal = opts.formal === true;
    const total = heads.reduce((sum, h) => sum + h.total, 0);
    const status = formal ? '✅ 正式・発走前固定' : '⏳ 暫定・研究表示';
    const tags = heads.map(h => '<span class="wpm-head-chip">' +
      '<span class="wpm-boat wpm-boat-' + h.head + '">' + enclosed[h.head] + '</span>' +
      '頭 ' + h.count + '点</span>').join('');
    const rows = heads.map((h, index) => {
      const seconds = Array.from(h.second.values());
      const secondRows = seconds.map(s => {
        const thirdTags = s.third.map(t => '<span class="wpm-third" aria-label="3着' +
          enclosed[t.third] + '、仮想' + amount(t.yen) + '">' +
          '<strong>' + enclosed[t.third] + '</strong><small>' + amount(t.yen) + '</small></span>').join('');
        return '<div class="wpm-second"><div class="wpm-second-label">' +
          '<span class="wpm-boat wpm-boat-' + s.second + '">' + enclosed[s.second] + '</span>' +
          '<span><strong>2着 ' + enclosed[s.second] + '</strong><small>' + s.count +
          '点 · 仮想' + amount(s.total) + '</small></span></div>' +
          '<div class="wpm-third-list"><span class="wpm-third-prefix">3着候補</span>' +
          thirdTags + '</div></div>';
      }).join('');
      return '<details class="wpm-head" ' + (index === 0 ? 'open' : '') + '><summary>' +
        '<span class="wpm-boat wpm-boat-' + h.head + '">' + enclosed[h.head] + '</span>' +
        '<span class="wpm-head-copy"><strong>1着 ' + enclosed[h.head] + ' の紐</strong>' +
        '<small>2着 ' + seconds.length + '艇 · ' + h.count + '点</small></span>' +
        '<span class="wpm-head-allocation">仮想' + amount(h.total) + '</span>' +
        '<span class="wpm-chevron" aria-hidden="true">⌄</span></summary>' +
        '<div class="wpm-head-body"><p>この艇が1着の場合に、保存済み買い目が採用した2・3着の組合せです。</p>' +
        secondRows + '</div></details>';
    }).join('');
    const scenario = r.scenario ? '<div class="wpm-scenario"><strong>保存時の全体展開仮説</strong><span>' +
      escapeHtml(r.scenario) + '</span></div>' : '';
    return '<section class="card card-pad wpm-panel" aria-label="1着別の紐マップ">' +
      '<div class="wpm-heading"><div><span class="wpm-eyebrow">WINNER → PARTNERS</span>' +
      '<h2>🚤 1着から読む紐マップ</h2></div><span class="wpm-status ' +
      (formal ? 'wpm-status-formal' : 'wpm-status-pending') + '">' + status + '</span></div>' +
      '<p class="wpm-intro">1着候補 → 2着候補 → 3着候補を順番に確認。見たい1着のカードを開いて紐を比較できます。</p>' +
      '<div class="wpm-head-chips" aria-label="採用された1着候補">' + tags + '</div>' +
      scenario + '<div class="wpm-head-list">' + rows + '</div>' +
      '<p class="wpm-footnote">保存済みの3連単' + r.bets.length + '点・仮想' + amount(total) +
      'を表示用に整理したものです。<strong>買い目・金額・優先順位は変更していません。</strong>' +
      '勝ち方別の紐確率は未検証のため断定せず、割合や勝率として表示しません。' +
      (!formal ? '展示6艇の発走前確認が済むまで正式予想ではありません。' : '') + '</p></section>';
  }
  const api = Object.freeze({render, groups});
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof window !== 'undefined') window.BoatWinnerPartnerMap = api;
})();
