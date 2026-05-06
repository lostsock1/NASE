const state = { data: null, view: 'opportunities', filter: '' };
const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? '').replace(
  /[&<>"']/g,
  (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char])
);
const fmt = new Intl.NumberFormat('en-US');
const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });

function n(value) { return Number(value || 0); }
function price(value) {
  const x = n(value);
  if (x >= 1) return money.format(x);
  if (x >= 0.01) return `$${x.toFixed(4)}`;
  return `$${x.toPrecision(6)}`;
}
function pct(value) { return `${n(value).toFixed(3)}%`; }
function compact(value) {
  const x = n(value);
  if (x >= 1_000_000) return `$${(x / 1_000_000).toFixed(1)}M`;
  if (x >= 1_000) return `$${(x / 1_000).toFixed(0)}K`;
  return money.format(x);
}
function confidenceClass(score) { return score >= 80 ? 'good' : score >= 60 ? 'warn' : 'bad'; }
function matches(text) { return String(text).toLowerCase().includes(state.filter.toLowerCase()); }

async function loadSnapshot() {
  const res = await fetch('/api/snapshot', { cache: 'no-store' });
  state.data = await res.json();
  render();
}
async function refreshNow() {
  const btn = $('refresh');
  btn.disabled = true;
  btn.textContent = 'Refreshing';
  try {
    const res = await fetch('/api/refresh', { method: 'POST' });
    state.data = await res.json();
    render();
  } finally {
    btn.disabled = false;
    btn.textContent = 'Refresh';
  }
}

function render() {
  const data = state.data;
  if (!data) return;
  $('cycle').textContent = data.cycle || 0;
  $('updated').textContent = data.updated_at ? new Date(data.updated_at).toLocaleTimeString() : 'warming up';
  const s = data.summary || {};
  $('m-opps').textContent = fmt.format(s.opportunities || 0);
  $('m-best').textContent = `best ${pct(s.best_spread || 0)}`;
  $('m-quotes').textContent = fmt.format(s.normalized_quotes || 0);
  $('m-raw').textContent = `${fmt.format(s.raw_quotes || 0)} raw`;
  $('m-exec').textContent = fmt.format(s.executable_quotes || 0);
  $('m-conf').textContent = n(s.median_confidence).toFixed(0);
  $('m-lat').textContent = `${n(data.elapsed_seconds).toFixed(1)}s`;
  $('m-state').textContent = data.busy ? 'refreshing' : data.error ? 'error' : 'idle';
  renderChains(data.chains || []);
  renderOpps(data.opportunities || []);
  renderSources(data.sources || []);
  renderQuotes(data.top_quotes || []);
}

function renderChains(chains) {
  $('chain-bars').innerHTML = chains.slice(0, 10).map(c => `<span class="chain-pill">${esc(c.name)} ${fmt.format(c.count)}</span>`).join('');
}

function renderOpps(items) {
  const rows = items.filter(o => matches(`${o.pair} ${o.buy_chain} ${o.sell_chain} ${o.buy_at} ${o.sell_at} ${(o.sources || []).join(' ')}`));
  $('opps-body').innerHTML = rows.length ? rows.map(o => `
    <tr>
      <td data-label="Pair"><span class="pair">${esc(o.pair)}</span><div class="note">${esc(o.chain)}</div></td>
      <td data-label="Route"><div class="route">${esc(o.buy_at)} → ${esc(o.sell_at)}</div><div class="note">${esc(o.buy_chain)} / ${esc(o.sell_chain)}</div></td>
      <td data-label="Buy">${price(o.buy_price)}</td>
      <td data-label="Sell">${price(o.sell_price)}</td>
      <td data-label="Spread" class="${n(o.spread_pct) > 1 ? 'good' : 'warn'}">${pct(o.spread_pct)}</td>
      <td data-label="TVL">${compact(o.liquidity_usd)}</td>
      <td data-label="Conf"><span class="badge ${confidenceClass(o.confidence)}">${o.confidence}</span></td>
      <td data-label="Notes"><span class="note">${esc((o.notes || []).slice(0, 2).join('; ') || (o.sources || []).join(', '))}</span></td>
    </tr>`).join('') : `<tr><td colspan="8" class="empty">No matching opportunities after filters.</td></tr>`;
}

function renderSources(items) {
  $('source-grid').innerHTML = items.map(src => {
    const cls = src.circuit_open ? 'bad' : src.rate_limited ? 'warn' : src.healthy ? 'good' : 'bad';
    const label = src.circuit_open ? `CB ${src.wait}s` : src.rate_limited ? `wait ${src.wait}s` : src.healthy ? 'healthy' : 'down';
    return `<article class="source-card">
      <h3>${esc(src.name)}<span class="${cls}">${esc(label)}</span></h3>
      <p>${src.success_rate.toFixed(0)}% success rate</p>
      <div class="source-meta">
        <div><span>Raw</span><strong>${fmt.format(src.raw)}</strong></div>
        <div><span>Norm</span><strong>${fmt.format(src.normalized)}</strong></div>
        <div><span>Exec</span><strong>${fmt.format(src.executable)}</strong></div>
      </div>
    </article>`;
  }).join('');
}

function renderQuotes(items) {
  const rows = items.filter(q => matches(`${q.pair} ${q.chain} ${q.source} ${q.dex}`));
  $('quotes-body').innerHTML = rows.length ? rows.map(q => `
    <tr>
      <td data-label="Pair"><span class="pair">${esc(q.pair)}</span></td>
      <td data-label="Chain">${esc(q.chain)}</td>
      <td data-label="Source">${esc(q.source)}</td>
      <td data-label="DEX">${esc(q.dex)}</td>
      <td data-label="Price">${price(q.price)}</td>
      <td data-label="Liquidity">${compact(q.liquidity_usd)}</td>
      <td data-label="Exec" class="${q.executable ? 'good' : 'note'}">${q.executable ? 'yes' : 'pool'}</td>
      <td data-label="Conf"><span class="badge ${confidenceClass(q.confidence)}">${q.confidence}</span></td>
    </tr>`).join('') : `<tr><td colspan="8" class="empty">No quotes match this filter.</td></tr>`;
}

for (const tab of document.querySelectorAll('.tab')) {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active-view'));
    tab.classList.add('active');
    $(tab.dataset.view).classList.add('active-view');
  });
}
$('filter').addEventListener('input', (event) => { state.filter = event.target.value; render(); });
$('refresh').addEventListener('click', refreshNow);
loadSnapshot();
setInterval(loadSnapshot, 5000);
