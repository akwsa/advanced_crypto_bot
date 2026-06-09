/**
 * Crypto Trading Dashboard — 3-Panel Layout
 * Left: Watchlist | Right-Top: Chart | Right-Bottom: Pair Detail
 */

const API_BASE = window.location.origin;
let chart = null;
let candleSeries = null;
let selectedPair = null;
let pairsData = [];
let positionsData = [];
let signalsData = [];

// ─── INIT ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await loadWatchlist();
  await loadPositions();
  await loadSignals();
  setupSearch();
  setupTimeframes();
  setupChartType();
  startAutoRefresh();
});

// ─── WATCHLIST ────────────────────────────────────────────────────────────────
async function loadWatchlist() {
  try {
    const res = await fetch(`${API_BASE}/api/v1/pairs/top-volume`);
    const json = await res.json();
    if (json.success) {
      pairsData = json.data.pairs || [];
      renderWatchlist(pairsData);
      document.getElementById('pairs-count').textContent = pairsData.length;
      document.getElementById('last-update').textContent = new Date().toLocaleTimeString('id-ID');
    }
  } catch (e) {
    console.error('Failed to load watchlist:', e);
  }
}

function renderWatchlist(pairs) {
  const list = document.getElementById('pairs-list');
  if (!pairs.length) {
    list.innerHTML = '<li class="loading">Tidak ada pair aktif</li>';
    return;
  }
  list.innerHTML = pairs.map(p => {
    const change = p.change_percent || 0;
    const changeClass = change > 0 ? 'up' : change < 0 ? 'down' : '';
    const changeText = change > 0 ? `+${change.toFixed(1)}%` : `${change.toFixed(1)}%`;
    const price = p.last_price ? formatPrice(p.last_price) : '—';
    return `
      <li data-pair="${p.pair}" onclick="selectPair('${p.pair}')">
        <div>
          <span class="pair-name">${p.pair.replace('idr','').toUpperCase()}</span>
          <span class="pair-price">${price}</span>
        </div>
        <span class="pair-change ${changeClass}">${changeText}</span>
      </li>
    `;
  }).join('');
}

function selectPair(pair) {
  selectedPair = pair;
  // Highlight active
  document.querySelectorAll('.pairs-list li').forEach(li => {
    li.classList.toggle('active', li.dataset.pair === pair);
  });
  // Update chart title
  const pairInfo = pairsData.find(p => p.pair === pair);
  const displayName = pair.replace('idr', '').toUpperCase() + '/IDR';
  document.getElementById('chart-pair').textContent = displayName;
  if (pairInfo && pairInfo.last_price) {
    document.getElementById('chart-price').textContent = formatPrice(pairInfo.last_price);
    const change = pairInfo.change_percent || 0;
    const changeEl = document.getElementById('chart-change');
    changeEl.textContent = (change >= 0 ? '+' : '') + change.toFixed(2) + '%';
    changeEl.className = 'chart-change ' + (change > 0 ? 'up' : change < 0 ? 'down' : 'neutral');
  }
  // Load chart + detail
  loadChart(pair);
  loadPairDetail(pair);
}

// ─── CHART ────────────────────────────────────────────────────────────────────
async function loadChart(pair) {
  const container = document.getElementById('chart-container');
  const activeBtn = document.querySelector('.tf-btn.active');
  const limit = activeBtn ? activeBtn.dataset.limit : 200;

  try {
    const res = await fetch(`${API_BASE}/api/v1/pairs/${pair}/chart?limit=${limit}`);
    const json = await res.json();
    if (!json.success || !json.data.candles.length) {
      container.innerHTML = '<div class="loading">Tidak ada data chart</div>';
      return;
    }
    renderChart(json.data.candles);
  } catch (e) {
    container.innerHTML = `<div class="loading">Error: ${e.message}</div>`;
  }
}

function renderChart(candles) {
  const container = document.getElementById('chart-container');
  container.innerHTML = '';

  const chartType = document.getElementById('chart-type').value;

  chart = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: container.clientHeight,
    layout: {
      background: { type: 'solid', color: '#1a1d29' },
      textColor: '#9aa0a6',
    },
    grid: {
      vertLines: { color: '#2d3142' },
      horzLines: { color: '#2d3142' },
    },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    timeScale: { timeVisible: true, secondsVisible: false },
    rightPriceScale: { borderColor: '#2d3142' },
  });

  const data = candles.map(c => ({
    time: Math.floor(new Date(c.timestamp).getTime() / 1000),
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
    value: c.close,
  })).sort((a, b) => a.time - b.time);

  if (chartType === 'candle') {
    candleSeries = chart.addCandlestickSeries({
      upColor: '#00c853',
      downColor: '#ff1744',
      borderUpColor: '#00c853',
      borderDownColor: '#ff1744',
      wickUpColor: '#00c853',
      wickDownColor: '#ff1744',
    });
    candleSeries.setData(data);
  } else if (chartType === 'line') {
    candleSeries = chart.addLineSeries({ color: '#448aff', lineWidth: 2 });
    candleSeries.setData(data.map(d => ({ time: d.time, value: d.close })));
  } else {
    candleSeries = chart.addAreaSeries({
      topColor: 'rgba(68,138,255,0.3)',
      bottomColor: 'rgba(68,138,255,0.0)',
      lineColor: '#448aff',
      lineWidth: 1,
    });
    candleSeries.setData(data.map(d => ({ time: d.time, value: d.close })));
  }

  chart.timeScale().fitContent();

  // Resize observer
  new ResizeObserver(() => {
    chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
  }).observe(container);
}

// ─── PAIR DETAIL ──────────────────────────────────────────────────────────────
async function loadPairDetail(pair) {
  // Get signal data
  try {
    const res = await fetch(`${API_BASE}/api/v1/signals/latest?pair=${pair}&limit=1`);
    const json = await res.json();
    if (json.success && json.data.signals.length) {
      const sig = json.data.signals[0];
      setDetail('d-confidence', sig.ml_confidence ? (sig.ml_confidence * 100).toFixed(0) + '%' : '—');
      setDetail('d-signal', sig.recommendation || '—', signalClass(sig.recommendation));
      setDetail('d-strength', sig.combined_strength ? sig.combined_strength.toFixed(2) : '—');
    } else {
      setDetail('d-confidence', '—');
      setDetail('d-signal', '—');
      setDetail('d-strength', '—');
    }
  } catch (e) {
    console.error('Signal fetch error:', e);
  }

  // Get pair market data
  const pairInfo = pairsData.find(p => p.pair === pair);
  if (pairInfo) {
    setDetail('d-volume', formatVolume(pairInfo.volume_idr));
    setDetail('d-volatility', '—'); // Will be from GARCH when available
  }

  // Get position data
  const pos = positionsData.find(p => p.pair === pair);
  if (pos) {
    setDetail('d-position', `${pos.type} @ ${formatPrice(pos.entry_price)}`);
    const pnl = pos.profit_loss || 0;
    setDetail('d-pnl', formatPrice(pnl) + ' IDR', pnl >= 0 ? 'buy' : 'sell');
  } else {
    setDetail('d-position', 'No Position');
    setDetail('d-pnl', '—');
  }

  // S/R from signal (if available)
  setDetail('d-support', '—');
  setDetail('d-resistance', '—');
  setDetail('d-rr', '—');
}

function setDetail(id, value, cls) {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = value;
    el.className = 'detail-value' + (cls ? ' ' + cls : '');
  }
}

function signalClass(rec) {
  if (!rec) return '';
  if (rec.includes('BUY')) return 'buy';
  if (rec.includes('SELL')) return 'sell';
  return 'hold';
}

// ─── POSITIONS ────────────────────────────────────────────────────────────────
async function loadPositions() {
  try {
    const res = await fetch(`${API_BASE}/api/v1/positions/open`);
    const json = await res.json();
    if (json.success) {
      positionsData = json.data.positions || [];
    }
  } catch (e) {
    console.error('Positions error:', e);
  }
}

// ─── SIGNALS ──────────────────────────────────────────────────────────────────
async function loadSignals() {
  try {
    const res = await fetch(`${API_BASE}/api/v1/signals/latest?limit=50`);
    const json = await res.json();
    if (json.success) {
      signalsData = json.data.signals || [];
    }
  } catch (e) {
    console.error('Signals error:', e);
  }
}

// ─── SEARCH ───────────────────────────────────────────────────────────────────
function setupSearch() {
  document.getElementById('pair-search').addEventListener('input', (e) => {
    const query = e.target.value.toLowerCase();
    const filtered = pairsData.filter(p => p.pair.includes(query) || p.display_pair.toLowerCase().includes(query));
    renderWatchlist(filtered);
  });
}

// ─── TIMEFRAMES ───────────────────────────────────────────────────────────────
function setupTimeframes() {
  document.querySelectorAll('.tf-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tf-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      if (selectedPair) loadChart(selectedPair);
    });
  });
}

// ─── CHART TYPE ───────────────────────────────────────────────────────────────
function setupChartType() {
  document.getElementById('chart-type').addEventListener('change', () => {
    if (selectedPair) loadChart(selectedPair);
  });
}

// ─── AUTO REFRESH ─────────────────────────────────────────────────────────────
function startAutoRefresh() {
  setInterval(async () => {
    await loadWatchlist();
    await loadPositions();
    if (selectedPair) await loadPairDetail(selectedPair);
  }, 30000); // 30 seconds
}

// ─── HELPERS ──────────────────────────────────────────────────────────────────
function formatPrice(value) {
  if (value === null || value === undefined) return '—';
  const num = Number(value);
  if (num >= 1000000) return num.toLocaleString('id-ID', { maximumFractionDigits: 0 });
  if (num >= 1000) return num.toLocaleString('id-ID', { maximumFractionDigits: 0 });
  if (num >= 1) return num.toLocaleString('id-ID', { maximumFractionDigits: 2 });
  return num.toFixed(6);
}

function formatVolume(value) {
  if (!value || value <= 0) return '—';
  if (value >= 1e9) return `Rp${(value / 1e9).toFixed(1)}B`;
  if (value >= 1e6) return `Rp${(value / 1e6).toFixed(0)}M`;
  if (value >= 1e3) return `Rp${(value / 1e3).toFixed(0)}K`;
  return `Rp${value.toFixed(0)}`;
}
