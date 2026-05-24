const API_BASE = window.DASHBOARD_API_BASE || '';
let tradingViewScriptPromise;
let selectedPair = null;
let selectedPairTitle = null;
let chartModel = 'clear-candles';
let activeTimeframe = '5m';
let activeChartLimit = 240;
let latestPairs = [];
let latestPositions = [];
let latestSignals = [];
let latestTrades = [];
let localChart = null;
let chartCandlestickSeries = null;
let chartLineSeries = null;
let chartAreaSeries = null;
let chartVolumeSeries = null;
let chartEntryLine = null;
let chartSlLine = null;
let chartTpLine = null;

const BINANCE_BLUE = '#2f6bff';
const BINANCE_RED = '#f6465d';
const BINANCE_BG = '#0b0e11';
const BINANCE_GRID = '#1e2329';
const BINANCE_TEXT = '#eaecef';

function rupiah(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return new Intl.NumberFormat('id-ID', {
    style: 'currency',
    currency: 'IDR',
    maximumFractionDigits: 0,
  }).format(Number(value));
}

function number(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return new Intl.NumberFormat('id-ID', { maximumFractionDigits: 8 }).format(Number(value));
}

function percent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  const numeric = Number(value);
  return `${numeric > 0 ? '+' : ''}${numeric.toFixed(2)}%`;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;',
  })[char]);
}

function badgeClass(freshness) {
  return `badge freshness-${escapeHtml(freshness || 'unknown')}`;
}

function normalizeTradingViewSymbol(symbol, pair) {
  const rawSymbol = String(symbol || '').trim().toUpperCase();
  if (rawSymbol && !rawSymbol.startsWith('INDODAX:')) {
    return rawSymbol;
  }

  const rawPair = String(pair || rawSymbol.replace(/^INDODAX:/, '') || 'BTCIDR')
    .replace(/[\/_-]/g, '')
    .toUpperCase();
  const normalizedPair = rawPair.endsWith('IDR') ? rawPair : `${rawPair}IDR`;
  return `INDODAX:${normalizedPair}`;
}

function normalizePair(pair) {
  const raw = String(pair || '').replace(/[\/_-]/g, '').toLowerCase();
  if (!raw) return 'btcidr';
  return raw.endsWith('idr') ? raw : `${raw}idr`;
}

function parseChartTime(value) {
  if (typeof value === 'number') return value;
  const text = String(value || '').trim();
  if (!text) return Math.floor(Date.now() / 1000);
  const normalized = text.includes('T') ? text : text.replace(' ', 'T');
  const millis = Date.parse(normalized.endsWith('Z') ? normalized : `${normalized}Z`);
  if (Number.isNaN(millis)) return Math.floor(Date.now() / 1000);
  return Math.floor(millis / 1000);
}

function loadTradingViewScript() {
  if (window.TradingView) return Promise.resolve();
  if (tradingViewScriptPromise) return tradingViewScriptPromise;

  tradingViewScriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector('script[src="https://s3.tradingview.com/tv.js"]');
    const script = existing || document.createElement('script');
    script.src = 'https://s3.tradingview.com/tv.js';
    script.async = true;
    script.onload = resolve;
    script.onerror = () => reject(new Error('TradingView script gagal dimuat'));
    if (!existing) document.head.appendChild(script);
  });

  return tradingViewScriptPromise;
}

async function getJson(path) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: 'application/json' },
    cache: 'no-store',
  });
  if (!response.ok) {
    throw new Error(`${path} failed with HTTP ${response.status}`);
  }
  return response.json();
}

function renderSafetyStatus(payload) {
  const data = payload.data || {};
  const container = document.getElementById('safety-status');
  const banner = document.getElementById('safety-banner');
  const locked = data.real_trading_locked !== false;

  banner.textContent = locked ? 'DRY RUN LOCKED' : 'REAL TRADING UNLOCKED';
  banner.classList.toggle('danger', !locked);

  const items = [
    ['Real Trading Lock', locked ? 'LOCKED / DRY RUN' : 'UNLOCKED', locked ? 'safe' : 'danger'],
    ['AutoTrade', data.auto_trading_enabled ? 'Enabled' : 'Disabled', 'neutral'],
    ['AutoTrade Mode', data.auto_trade_dry_run ? 'DRY RUN' : 'REAL', data.auto_trade_dry_run ? 'safe' : 'danger'],
    ['Manual Trading', data.manual_trading_enabled ? 'Enabled' : 'Disabled', 'neutral'],
    ['Cancel Trade', data.cancel_trade_enabled ? 'Enabled' : 'Disabled', 'neutral'],
    ['Dashboard Write', data.dashboard_write_enabled ? 'Enabled' : 'Disabled', data.dashboard_write_enabled ? 'danger' : 'safe'],
    ['SmartHunter', data.smart_hunter?.mode || 'DRY_RUN', data.smart_hunter?.mode === 'REAL' ? 'danger' : 'safe'],
    ['AutoHunter', data.auto_hunter?.mode || 'DRY_RUN', data.auto_hunter?.mode === 'REAL' ? 'danger' : 'safe'],
  ];

  container.innerHTML = items
    .map(([label, value, tone]) => `
      <article class="status-card ${tone}">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
      </article>
    `)
    .join('');
}

function renderHealthStatus(health, sources) {
  const healthData = health.data || {};
  const sourceData = sources.data || {};
  const freshness = sources.meta?.freshness || 'unknown';
  document.getElementById('health-freshness').className = badgeClass(freshness);
  document.getElementById('health-freshness').textContent = freshness;

  const items = [
    ['API', healthData.api_status || 'unknown', healthData.api_status === 'online' ? 'safe' : 'danger'],
    ['Read-only', healthData.read_only ? 'true' : 'false', healthData.read_only ? 'safe' : 'danger'],
    ['Trading DB', sourceData.trading_db?.status || 'unknown', sourceData.trading_db?.status === 'online' ? 'safe' : 'danger'],
    ['Signals DB', sourceData.signals_db?.status || 'unknown', sourceData.signals_db?.status === 'online' ? 'safe' : 'danger'],
    ['Redis', sourceData.redis?.status || 'unknown', 'neutral'],
    ['Dashboard Write', sourceData.dashboard_write_enabled ? 'enabled' : 'disabled', sourceData.dashboard_write_enabled ? 'danger' : 'safe'],
  ];
  document.getElementById('health-status').innerHTML = items
    .map(([label, value, tone]) => `
      <article class="status-card ${tone}">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
      </article>
    `)
    .join('');
}

function walletReadyClass(status) {
  const key = String(status?.status || 'watch_only');
  if (key.includes('sell') && key.includes('buy')) return 'sell-ready buy-ready';
  if (key.includes('sell')) return 'sell-ready';
  if (key.includes('buy')) return 'buy-ready';
  return 'watch-only';
}

function walletReadyText(status) {
  if (!status) return 'PANTAU';
  const parts = [];
  if (status.sell_ready) parts.push(`SIAP JUAL ${number(status.asset_balance)} ${String(status.asset || '').toUpperCase()}`);
  if (status.buy_ready) parts.push(`SIAP BELI ${rupiah(status.idr_balance)}`);
  return parts.length ? parts.join(' • ') : (status.label || 'PANTAU');
}

function renderTopVolumePairs(payload) {
  const pairs = payload.data?.pairs || [];
  latestPairs = pairs;
  document.getElementById('pairs-count').textContent = `${pairs.length} pair`;
  const container = document.getElementById('pairs-list');
  if (!pairs.length) {
    container.innerHTML = '<div class="empty-chart">Pair volume > 500.000.000 IDR belum tersedia.</div>';
    return;
  }
  if (!selectedPair || !pairs.some((pair) => normalizePair(pair.pair) === selectedPair)) {
    selectedPair = normalizePair(pairs[0].pair);
    selectedPairTitle = pairs[0].display_pair || pairs[0].pair;
  }
  container.innerHTML = pairs.map((pair) => {
    const normalized = normalizePair(pair.pair);
    const activeClass = normalized === selectedPair ? ' selected' : '';
    const change = Number(pair.change_percent || 0);
    const changeClass = change >= 0 ? 'positive' : 'negative';
    const walletStatus = pair.wallet_status || {};
    const walletClass = walletReadyClass(walletStatus);
    return `
      <button class="pair-card${activeClass}" type="button" data-pair="${escapeHtml(normalized)}" data-symbol="${escapeHtml(pair.tradingview_symbol)}" data-title="${escapeHtml(pair.display_pair || pair.pair)}">
        <span class="pair-card-topline">
          <span class="rank-pill">#${escapeHtml(pair.top_volume_rank || '-')}</span>
          <span class="wallet-ready-pill ${escapeHtml(walletClass)}">${escapeHtml(walletStatus.label || 'PANTAU')}</span>
        </span>
        <strong>${escapeHtml(pair.display_pair || pair.pair)}</strong>
        <span>${rupiah(pair.last_price)} <em class="${changeClass}">${percent(pair.change_percent)}</em></span>
        <small>${escapeHtml(walletReadyText(walletStatus))}</small>
        <small>Vol IDR: ${rupiah(pair.volume_idr)} • ${escapeHtml(pair.tradingview_symbol)}</small>
      </button>
    `;
  }).join('');
  Array.from(container.querySelectorAll('.pair-card')).forEach((button) => {
    button.addEventListener('click', () => {
      selectedPair = normalizePair(button.dataset.pair);
      selectedPairTitle = button.dataset.title || selectedPair.toUpperCase();
      renderTopVolumePairs(payload);
      renderLocalPairChart(selectedPair, selectedPairTitle).catch(renderChartError);
    });
  });
}

const renderPairs = renderTopVolumePairs;

function renderSignals(payload) {
  const signals = payload.data?.signals || [];
  latestSignals = signals;
  document.getElementById('signals-count').textContent = `${signals.length} sinyal`;
  const container = document.getElementById('signals-list');
  if (!signals.length) {
    container.innerHTML = '<div class="empty-chart">Belum ada sinyal terbaru.</div>';
    return;
  }
  container.innerHTML = signals.slice(0, 20).map((signal) => `
    <article class="signal-card">
      <div>
        <strong>${escapeHtml(signal.display_pair || signal.pair)}</strong>
        <span class="badge">${escapeHtml(signal.recommendation || '-')}</span>
      </div>
      <p>${escapeHtml(signal.analysis || '')}</p>
      <small>${escapeHtml(signal.received_at || signal.created_at || '')} • confidence ${number(signal.ml_confidence)}</small>
    </article>
  `).join('');
}

function renderTrades(payload) {
  const trades = payload.data?.trades || [];
  latestTrades = trades;
  document.getElementById('trades-count').textContent = `${trades.length} trade`;
  const table = document.getElementById('trades-table');
  if (!trades.length) {
    table.innerHTML = '<tr><td colspan="6">Trade history kosong.</td></tr>';
    return;
  }
  table.innerHTML = trades.slice(0, 50).map((trade) => `
    <tr>
      <td><strong>${escapeHtml(trade.display_pair || trade.pair)}</strong><br><small>${escapeHtml(trade.tradingview_symbol || '')}</small></td>
      <td>${escapeHtml(trade.type || '-')}</td>
      <td>${escapeHtml(trade.status || '-')}</td>
      <td>${rupiah(trade.entry_price)}</td>
      <td>${rupiah(trade.total)}</td>
      <td>${trade.profit_loss === null || trade.profit_loss === undefined ? '-' : rupiah(trade.profit_loss)}</td>
    </tr>
  `).join('');
}

function renderChartError(error) {
  document.getElementById('tradingview-chart').innerHTML = `<div class="empty-chart">${escapeHtml(error.message)}</div>`;
}

function resetLocalChart() {
  if (localChart) {
    localChart.remove();
    localChart = null;
  }
  chartCandlestickSeries = null;
  chartLineSeries = null;
  chartAreaSeries = null;
  chartVolumeSeries = null;
  chartEntryLine = null;
  chartSlLine = null;
  chartTpLine = null;
}

function chartTitleSuffix() {
  if (chartModel === 'bold-line') return ` • Garis Tegas ${activeTimeframe}`;
  if (chartModel === 'area-trend') return ` • Area Trend ${activeTimeframe}`;
  if (chartModel === 'tradingview') return ` • TradingView ${activeTimeframe}`;
  return ` • Candle Jelas ${activeTimeframe}`;
}

function setChartModel(model) {
  chartModel = model || 'bold-line';
  if (selectedPair) {
    renderLocalPairChart(selectedPair, selectedPairTitle).catch(renderChartError);
  }
}

async function renderTradingView(symbol, pair) {
  const chart = document.getElementById('tradingview-chart');
  const widgetSymbol = normalizeTradingViewSymbol(symbol, pair);
  resetLocalChart();
  chart.innerHTML = '<div class="empty-chart">Memuat grafik TradingView fallback...</div>';

  try {
    await loadTradingViewScript();
  } catch (error) {
    renderChartError(error);
    return;
  }

  chart.innerHTML = '';
  new TradingView.widget({
    autosize: true,
    symbol: widgetSymbol,
    interval: '5',
    timezone: 'Asia/Jakarta',
    theme: 'dark',
    style: '1',
    locale: 'id',
    container_id: 'tradingview-chart',
    hide_side_toolbar: false,
    allow_symbol_change: false,
    studies: ['Volume@tv-basicstudies'],
  });
}

async function renderLocalPairChart(pair, title) {
  const normalized = normalizePair(pair);
  const chart = document.getElementById('tradingview-chart');
  const symbol = normalizeTradingViewSymbol('', normalized);
  document.getElementById('chart-title').textContent = `${title || normalized.toUpperCase()}${chartTitleSuffix()}`;
  document.getElementById('chart-symbol').textContent = symbol;
  chart.innerHTML = '<div class="empty-chart">Memuat grafik Pair Aktif Terpilih dari data bot.py...</div>';

  if (chartModel === 'tradingview') {
    renderTradingView(symbol, normalized);
    return;
  }

  const payload = await getJson(`/api/v1/pairs/${encodeURIComponent(pair)}/chart?limit=${activeChartLimit}`);
  const candles = payload.data?.candles || [];
  if (!candles.length) {
    chart.innerHTML = '<div class="empty-chart">Belum ada candle untuk pair aktif ini.</div>';
    return;
  }

  if (!window.LightweightCharts) {
    renderTradingView(symbol, normalized);
    return;
  }

  chart.innerHTML = '';
  resetLocalChart();

  const candleData = candles.map((candle) => ({
    time: parseChartTime(candle.time || candle.timestamp),
    open: Number(candle.open),
    high: Number(candle.high),
    low: Number(candle.low),
    close: Number(candle.close),
  })).filter((candle) => [candle.open, candle.high, candle.low, candle.close].every(Number.isFinite));
  const closeData = candleData.map((candle) => ({ time: candle.time, value: candle.close }));
  const volumeData = candles.map((candle) => ({
    time: parseChartTime(candle.time || candle.timestamp),
    value: Number(candle.volume || 0),
    color: Number(candle.close) >= Number(candle.open) ? 'rgba(47, 107, 255, 0.32)' : 'rgba(246, 70, 93, 0.32)',
  }));

  localChart = LightweightCharts.createChart(chart, {
    autoSize: true,
    layout: { background: { color: BINANCE_BG }, textColor: BINANCE_TEXT },
    grid: { vertLines: { color: BINANCE_GRID }, horzLines: { color: BINANCE_GRID } },
    rightPriceScale: { borderColor: BINANCE_GRID },
    timeScale: { borderColor: BINANCE_GRID, timeVisible: true, secondsVisible: false },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  });

  if (chartModel === 'bold-line') {
    chartLineSeries = localChart.addLineSeries({
      color: BINANCE_BLUE,
      lineWidth: 1,
      priceLineVisible: true,
      priceLineWidth: 1,
      priceLineColor: BINANCE_BLUE,
      lastValueVisible: true,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 2,
      priceFormat: { type: 'price', precision: 0, minMove: 1 },
    });
    chartLineSeries.setData(closeData);
    applyBotPriceLines(chartLineSeries, closeData);
  } else if (chartModel === 'area-trend') {
    chartAreaSeries = localChart.addAreaSeries({
      topColor: 'rgba(47, 107, 255, 0.20)', bottomColor: 'rgba(47, 107, 255, 0.03)', lineColor: BINANCE_BLUE, lineWidth: 1,
      priceLineVisible: true, priceLineWidth: 1, priceLineColor: BINANCE_BLUE, lastValueVisible: true,
      priceFormat: { type: 'price', precision: 0, minMove: 1 },
    });
    chartAreaSeries.setData(closeData);
    applyBotPriceLines(chartAreaSeries, closeData);
  } else {
    chartCandlestickSeries = localChart.addCandlestickSeries({
      upColor: BINANCE_BLUE, downColor: BINANCE_RED, borderUpColor: BINANCE_BLUE, borderDownColor: BINANCE_RED, wickUpColor: BINANCE_BLUE, wickDownColor: BINANCE_RED,
      priceFormat: { type: 'price', precision: 0, minMove: 1 },
    });
    chartCandlestickSeries.setData(candleData);
    applyBotPriceLines(chartCandlestickSeries, closeData);
  }

  chartVolumeSeries = localChart.addHistogramSeries({
    color: '#64748b', priceFormat: { type: 'volume' }, priceScaleId: '',
  });
  chartVolumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  chartVolumeSeries.setData(volumeData);
  localChart.timeScale().fitContent();
  renderBotOverlay(normalized, closeData.at(-1)?.value || null);
}

function selectedPosition(pair) {
  const normalized = normalizePair(pair);
  return latestPositions.find((position) => normalizePair(position.pair) === normalized) || null;
}

function selectedSignal(pair) {
  const normalized = normalizePair(pair);
  return latestSignals.find((signal) => normalizePair(signal.pair) === normalized) || null;
}

function botLevels(pair, lastClose = null) {
  const position = selectedPosition(pair);
  const signal = selectedSignal(pair);
  const market = latestPairs.find((item) => normalizePair(item.pair) === normalizePair(pair));
  const entry = Number(position?.entry_price || signal?.price || lastClose || market?.last_price || 0);
  const current = Number(lastClose || market?.last_price || entry || 0);
  const sl = entry > 0 ? entry * 0.97 : null;
  const tp = entry > 0 ? entry * 1.06 : null;
  const pnl = position && entry > 0 && current > 0 ? ((current - entry) / entry) * 100 : null;
  return { position, signal, entry: entry || null, current: current || null, sl, tp, pnl };
}

function renderBotOverlay(pair = selectedPair, lastClose = null) {
  const levels = botLevels(pair, lastClose);
  document.getElementById('overlay-entry').textContent = levels.entry ? rupiah(levels.entry) : '-';
  document.getElementById('overlay-sl').textContent = levels.sl ? rupiah(levels.sl) : '-';
  document.getElementById('overlay-tp').textContent = levels.tp ? rupiah(levels.tp) : '-';
  document.getElementById('overlay-signal').textContent = levels.signal?.recommendation || 'WAIT';
  document.getElementById('overlay-confidence').textContent = levels.signal?.ml_confidence ? percent(Number(levels.signal.ml_confidence) * 100) : '-';
  document.getElementById('overlay-pnl').textContent = levels.pnl === null ? '-' : percent(levels.pnl); // PnL
  document.getElementById('overlay-pnl').className = levels.pnl >= 0 ? 'positive' : 'negative';
}

function applyBotPriceLines(series, closeData = []) {
  if (!series || !selectedPair) return;
  const levels = botLevels(selectedPair, closeData.at(-1)?.value || null);
  if (levels.entry) {
    chartEntryLine = series.createPriceLine({ price: levels.entry, color: '#facc15', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true, title: 'Entry' }); // entry-line
  }
  if (levels.sl) {
    chartSlLine = series.createPriceLine({ price: levels.sl, color: '#ef5350', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: 'SL' }); // sl-line
  }
  if (levels.tp) {
    chartTpLine = series.createPriceLine({ price: levels.tp, color: '#26a69a', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: 'TP' }); // tp-line
  }
}

function selectPosition(position) {
  const normalized = normalizePair(position.pair);
  if (!latestPairs.some((pair) => normalizePair(pair.pair) === normalized)) {
    return;
  }
  selectedPair = normalized;
  selectedPairTitle = position.display_pair || String(position.pair || '').toUpperCase();
  renderLocalPairChart(selectedPair, selectedPairTitle).catch(renderChartError);
}

function renderPositions(payload) {
  const positions = payload.data?.positions || [];
  latestPositions = positions;
  const table = document.getElementById('positions-table');
  const count = document.getElementById('positions-count');
  count.textContent = `${positions.length} posisi`;

  if (!positions.length) {
    table.innerHTML = '<tr><td colspan="6">Tidak ada posisi trading/scalping yang sedang OPEN.</td></tr>';
    document.getElementById('chart-title').textContent = selectedPairTitle || 'Pilih pair Top 33 Volume Indodax';
    document.getElementById('chart-symbol').textContent = selectedPair ? normalizeTradingViewSymbol('', selectedPair) : 'INDODAX';
    if (selectedPair) {
      renderLocalPairChart(selectedPair, selectedPairTitle).catch(renderChartError);
    } else {
      document.getElementById('tradingview-chart').innerHTML = '<div class="empty-chart">Pilih pair di Top 33 Volume Indodax untuk menampilkan chart.</div>';
    }
    return;
  }

  table.innerHTML = positions
    .map((position, index) => `
      <tr data-index="${index}" tabindex="0">
        <td><strong>${String(position.pair || '-').toUpperCase()}</strong><br><small>${position.tradingview_symbol || ''}</small></td>
        <td>${position.type || '-'}</td>
        <td>${rupiah(position.entry_price)}</td>
        <td>${number(position.amount)}</td>
        <td>${rupiah(position.total)}</td>
        <td><span class="mode-pill">${position.mode || 'DRY_RUN'}</span></td>
      </tr>
    `)
    .join('');

  Array.from(table.querySelectorAll('tr[data-index]')).forEach((row) => {
    const handler = () => selectPosition(positions[Number(row.dataset.index)]);
    row.addEventListener('click', handler);
    row.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') handler();
    });
  });

  const selectedOpenPosition = positions.find((position) => normalizePair(position.pair) === selectedPair);
  if (selectedOpenPosition) selectPosition(selectedOpenPosition);
}

async function refreshDashboard() {
  const [safety, health, sources, pairs, positions, signals, trades] = await Promise.all([
    getJson('/api/v1/safety/status'),
    getJson('/api/v1/health'),
    getJson('/api/v1/system/data-sources'),
    getJson('/api/v1/pairs/top-volume'),
    getJson('/api/v1/positions/open'),
    getJson('/api/v1/signals/latest?limit=20'),
    getJson('/api/v1/trades/history?limit=50'),
  ]);
  renderSafetyStatus(safety);
  renderHealthStatus(health, sources);
  renderPairs(pairs);
  renderPositions(positions);
  if (selectedPair && !(positions.data?.positions || []).some((position) => normalizePair(position.pair) === selectedPair)) {
    renderLocalPairChart(selectedPair, selectedPairTitle).catch(renderChartError);
  }
  renderSignals(signals);
  renderTrades(trades);
  renderBotOverlay(selectedPair);
}

function renderError(error) {
  document.getElementById('safety-status').innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
  document.getElementById('health-status').innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
  document.getElementById('pairs-list').innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
  document.getElementById('positions-table').innerHTML = `<tr><td colspan="6">${escapeHtml(error.message)}</td></tr>`;
  document.getElementById('signals-list').innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
  document.getElementById('trades-table').innerHTML = `<tr><td colspan="6">${escapeHtml(error.message)}</td></tr>`;
}

document.getElementById('refresh-button').addEventListener('click', () => {
  refreshDashboard().catch(renderError);
});

document.getElementById('chart-model-select').addEventListener('change', (event) => {
  setChartModel(event.target.value);
});

Array.from(document.querySelectorAll('.timeframe-button')).forEach((button) => {
  button.addEventListener('click', () => {
    activeTimeframe = button.dataset.timeframe || '1m';
    activeChartLimit = Number(button.dataset.limit || 120);
    document.querySelectorAll('.timeframe-button').forEach((item) => item.classList.remove('active'));
    button.classList.add('active');
    if (selectedPair) renderLocalPairChart(selectedPair, selectedPairTitle).catch(renderChartError);
  });
});

refreshDashboard().catch(renderError);

let dashboardEvents;
try {
  dashboardEvents = new EventSource(`${API_BASE}/api/v1/events/stream`);
  dashboardEvents.addEventListener('heartbeat', () => {
    setTimeout(() => refreshDashboard().catch(renderError), 250);
  });
  dashboardEvents.onerror = () => {
    dashboardEvents.close();
    setInterval(() => refreshDashboard().catch(renderError), 10000);
  };
} catch (error) {
  setInterval(() => refreshDashboard().catch(renderError), 10000);
}
