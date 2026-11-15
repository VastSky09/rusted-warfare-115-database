window.RWViews = window.RWViews || {};
window.RWViews.a = (a) => {
  const u = a.u;
  const incoming = a.incoming || [];
  const outgoing = a.outgoing || [];
  const xIn = a.xIn || [];
  const xOut = a.xOut || [];
  const count = (items) => `<span class="a-count">${a.n(items.length)}</span>`;
  const empty = (text) => `<p class="a-empty">${text}</p>`;
  const hasTransforms = xIn.length + xOut.length > 0;

  return `<div class="view-a">
    <div class="a-layout">
      <aside class="a-sidebar" aria-label="单位目录">${a.sidebar()}</aside>
      <article class="a-detail" aria-label="${a.e(u.name_zh)}资料">
        <div class="a-toolbar">${a.toolbar()}</div>
        <header class="a-unit-header">
          <div class="a-unit-heading">
            <h1>${a.e(u.name_zh)}</h1>
            <span class="a-unit-category">${a.e(u.category)}</span>
          </div>
          <p class="a-identity"><span>${a.e(u.native_id)}</span><span>${a.e(u.object_id)}</span></p>
          <div class="a-price-line"><span>已记录获取费用</span><strong>${a.price(u)}</strong></div>
        </header>

        <div class="a-relations">
          <section class="a-relation-section" aria-labelledby="a-incoming-title">
            <div class="a-section-heading"><h2 id="a-incoming-title">从哪里获得</h2>${count(incoming)}</div>
            <p class="a-section-note">按来源及其状态查看获取条件。</p>
            ${incoming.length ? a.rows(incoming, false) : empty('当前资料未记录获取来源。可在下方查看是否有相关形态转换。')}
          </section>
          <section class="a-relation-section a-outgoing" aria-labelledby="a-outgoing-title">
            <div class="a-section-heading"><h2 id="a-outgoing-title">可生产／建造／升级</h2>${count(outgoing)}</div>
            <p class="a-section-note">以当前对象为起点的科技关系。</p>
            ${outgoing.length ? a.rows(outgoing, true) : empty('未记录此对象的生产、建造或升级关系。')}
          </section>
        </div>

        <section class="a-transform-section" aria-labelledby="a-transform-title">
          <div class="a-section-heading"><h2 id="a-transform-title">形态与模式</h2>${count([...xIn, ...xOut])}</div>
          ${hasTransforms ? `<div class="a-transform-grid">
            <section><h3>转入当前形态</h3>${xIn.length ? a.rows(xIn, false) : empty('未记录转入关系。')}</section>
            <section><h3>从当前形态转出</h3>${xOut.length ? a.rows(xOut, true) : empty('未记录转出关系。')}</section>
          </div>` : empty('未记录相关形态或模式转换。')}
        </section>

        <div class="a-battle">${a.battle()}</div>
        <div class="a-info">${a.info()}</div>
      </article>
    </div>
  </div>`;
};
