window.RWViews = window.RWViews || {};
RWViews.b = (a) => {
  const { u, e, n } = a;
  const incoming = a.incoming || [], outgoing = a.outgoing || [];
  const xIn = a.xIn || [], xOut = a.xOut || [];
  const stage = (value) => value ? String(value).replace(/^S-OBJ-\d+-/, '') : '阶段未记录';
  const fee = (row) => row.cost_credits === '' || row.cost_credits == null ? '费用未记录' : '$' + n(Number(row.cost_credits));
  const uniqueRows = (rows) => [...new Map(rows.map(r => [r.relation_id || JSON.stringify(r), r])).values()];
  const self = uniqueRows([...incoming, ...outgoing, ...xIn, ...xOut].filter(r => r.source_native_id === u.native_id && r.target_native_id === u.native_id));

  function neighbors(rows, outbound) {
    const found = new Map();
    uniqueRows(rows).forEach(row => {
      const id = outbound ? row.target_native_id : row.source_native_id;
      if (!id || id === u.native_id) return;
      if (!found.has(id)) found.set(id, { id, name: (a.getUnit(id) || {}).name_zh || (outbound ? row.target_name : row.source_name) || id, rows: [] });
      found.get(id).rows.push(row);
    });
    return [...found.values()];
  }

  function edgeLine(row) {
    return '<div class="path-edge"><span>' + e(row.relation) + ' · ' + e(stage(row.source_state)) + ' → ' + e(stage(row.target_state)) + '</span><strong>' + fee(row) + '</strong></div>';
  }

  function node(item) {
    const records = item.rows.map(edgeLine);
    const extra = records.length > 2 ? '<details class="path-node-extra"><summary>其余 ' + (records.length - 2) + ' 条阶段记录</summary>' + records.slice(2).join('') + '</details>' : '';
    return '<li class="path-node"><div class="path-node-title">' + a.link(item.id, item.name, 'path-node-name') + '<code>' + e(item.id) + '</code></div><div class="path-node-edges">' + records.slice(0, 2).join('') + extra + '</div></li>';
  }

  function lane(items, outbound) {
    const title = outbound ? '下游去向' : '上游来源';
    const empty = outbound ? '未记录由此对象生产、建造或转换出的其他对象。' : '未记录此对象的直接获取来源。';
    return '<section class="path-lane" aria-label="' + title + '"><h3>' + title + '<span>' + items.length + ' 个对象</span></h3>' + (items.length ? '<ul class="path-neighbors">' + items.slice(0, 6).map(node).join('') + '</ul>' + (items.length > 6 ? '<details class="path-more"><summary>展开其余 ' + (items.length - 6) + ' 个对象</summary><ul class="path-neighbors">' + items.slice(6).map(node).join('') + '</ul></details>' : '') : '<p class="path-empty">' + empty + '</p>') + '</section>';
  }

  const sources = neighbors([...incoming, ...xIn], false);
  const targets = neighbors([...outgoing, ...xOut], true);
  const ownStages = self.length ? '<section class="path-internal"><h4>内部升级与模式</h4>' + self.slice(0, 2).map(edgeLine).join('') + (self.length > 2 ? '<details><summary>其余 ' + (self.length - 2) + ' 条记录</summary>' + self.slice(2).map(edgeLine).join('') + '</details>' : '') + '</section>' : '';

  return `<div class="view-b">
    <div class="path-topline">
      <div><h2>科技路径浏览</h2><p>从当前对象出发，查找获取来源与后续去向。</p></div>
      <div class="path-navigation">${a.toolbar()}</div>
    </div>
    <details class="path-directory">
      <summary>切换查看对象<span>搜索完整目录</span></summary>
      <div class="path-directory-body">${a.sidebar()}</div>
    </details>
    <section class="path-canvas" aria-label="当前对象的局部科技关系">
      ${lane(sources, false)}
      <div class="path-connector" aria-hidden="true"></div>
      <article class="path-focus" aria-label="当前对象">
        <div class="path-focus-heading"><h3>${e(u.name_zh)}</h3><span>当前对象</span></div>
        <p class="path-identity"><code>${e(u.native_id)}</code><span>${e(u.object_id)} · ${e(u.category)}</span></p>
        <dl class="path-price"><dt>已记录获取费用</dt><dd>${a.price(u)}</dd></dl>
        ${ownStages}
        <p class="path-focus-note">点选两侧对象，继续沿路径查找。</p>
      </article>
      <div class="path-connector" aria-hidden="true"></div>
      ${lane(targets, true)}
    </section>
    <div class="path-caption"><span>只显示与当前对象直接相连的关系</span><span>来源 → 当前对象 → 去向</span></div>
    <section class="path-records" aria-labelledby="path-record-title">
      <div class="path-record-heading"><h2 id="path-record-title">完整费用与阶段</h2><p>同一对象可有多个获取来源。费用按每条关系记录，空白不代表免费。</p></div>
      <details class="path-record-set" open><summary>获取与前置来源<span>${incoming.length} 条记录</span></summary>${a.rows(incoming, false)}</details>
      <details class="path-record-set" open><summary>生产、建造与升级<span>${outgoing.length} 条记录</span></summary>${a.rows(outgoing, true)}</details>
      <details class="path-record-set"><summary>形态与模式转换<span>${xIn.length + xOut.length} 条方向记录</span></summary><div class="path-transform"><section><h3>转换为当前对象</h3>${a.rows(xIn, false)}</section><section><h3>由当前对象转换</h3>${a.rows(xOut, true)}</section></div></details>
    </section>
    <div class="path-secondary">${a.battle()}${a.info()}</div>
  </div>`;
};
