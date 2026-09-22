/**
 * Crypto Trading Dashboard — Modern Layout
 * Top bar (status + stats) + 3-column (pairs | chart+detail | insights)
 *
 * Tabs di kiri: Watchlist (top volume), Top Movers (gainers), Top Losers
 * Panel kanan: live movers, recent signals, open positions
 */

const API_BASE = window.location.origin;
const REFRESH_INTERVAL_MS = 30000;

let chart = null;
let candleSeries = null;
let selectedPair = null;
let activeTab = "watchlist"; // watchlist | movers | losers

// Caches
let watchlistData = [];
let moversData = [];
let losersData = [];
let positionsData = [];
let signalsData = [];

// ─── INIT ─────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  setupTabs();
  setupSearch();
  setupTimeframes();
  setupChartType();
  await refreshAll();
  startAutoRefresh();
});

async function refreshAll() {
  await Promise.all([
    loadWatchlist(),
    loadMovers(),
    loadLosers(),
    loadSignals(),
    loadPositions(),
    loadSafetyStatus(),
  ]);
  renderActiveList();
  renderInsights();
  updateTopbarStats();
  document.getElementById("stat-last-update").textContent = new Date().toLocaleTimeString("id-ID");
}

// ─── TABS ─────────────────────────────────────────────────────────────────────

function setupTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeTab = btn.dataset.tab;
      renderActiveList();
    });
  });
}

function activeTabData() {
  if (activeTab === "movers") return moversData;
  if (activeTab === "losers") return losersData;
  return watchlistData;
}

function renderActiveList() {
  const data = activeTabData();
  renderPairsList(data, activeTab);
  document.getElementById("count-watchlist").textContent = watchlistData.length;
  document.getElementById("count-movers").textContent = moversData.length;
  document.getElementById("count-losers").textContent = losersData.length;
}

// ─── DATA LOADERS ─────────────────────────────────────────────────────────────

async function loadWatchlist() {
  try {
    const res = await fetch(`${API_BASE}/api/v1/pairs/top-volume?limit=30`);
    const json = await res.json();
    if (json.success) {
      watchlistData = (json.data.pairs || []).map((p) => ({
        ...p,
        _badges: ["TOP_VOLUME"],
      }));
    }
  } catch (e) {
    console.error("Watchlist error:", e);
  }
}

async function loadMovers() {
  try {
    const res = await fetch(`${API_BASE}/api/v1/pairs/top-movers?limit=30&direction=up`);
    const json = await res.json();
    if (json.success) {
      moversData = (json.data.pairs || []).map((p) => ({
        ...p,
        _badges: p.badges || [],
      }));
    }
  } catch (e) {
    console.error("Movers error:", e);
  }
}

async function loadLosers() {
  try {
    const res = await fetch(`${API_BASE}/api/v1/pairs/top-movers?limit=20&direction=down`);
    const json = await res.json();
    if (json.success) {
      losersData = (json.data.pairs || []).map((p) => ({
        ...p,
        _badges: p.badges || [],
      }));
    }
  } catch (e) {
    console.error("Losers error:", e);
  }
}

async function loadSignals() {
  try {
    const res = await fetch(`${API_BASE}/api/v1/signals/latest?limit=20`);
    const json = await res.json();
    if (json.success) {
      signalsData = json.data.signals || [];
    }
  } catch (e) {
    console.error("Signals error:", e);
  }
}

async function loadPositions() {
  try {
    const res = await fetch(`${API_BASE}/api/v1/positions/open`);
    const json = await res.json();
    if (json.success) {
      positionsData = json.data.positions || [];
    }
  } catch (e) {
    console.error("Positions error:", e);
  }
}

async function loadSafetyStatus() {
  try {
    const res = await fetch(`${API_BASE}/api/v1/safety/status`);
    const json = await res.json();
    if (json.success) {
      const isDryRun = !!json.data.auto_trade_dry_run;
      const badge = document.getElementById("mode-badge");
      badge.textContent = isDryRun ? "DRY RUN" : "REAL TRADING";
      badge.classList.toggle("real", !isDryRun);
    }
  } catch (e) {
    document.getElementById("api-status").textContent = "● API OFFLINE";
    document.getElementById("api-status").classList.replace("online", "offline");
  }
}

// ─── RENDER PAIRS LIST ────────────────────────────────────────────────────────

function renderPairsList(pairs, tab) {
  const list = document.getElementById("pairs-list");
  if (!pairs.length) {
    list.innerHTML = '<li class="loading">Tidak ada data</li>';
    return;
  }
  list.innerHTML = pairs.map((p) => {
    const change = p.change_percent != null ? p.change_percent : 0;
    const changeClass = change > 0 ? "up" : change < 0 ? "down" : "";
    const changeText = change > 0 ? `+${change.toFixed(2)}%` : `${change.toFixed(2)}%`;
    const price = (p.last_price ?? p.last) ? formatPrice(p.last_price ?? p.last) : "—";
    const volume = formatVolume(p.volume_idr);
    const sym = p.pair.replace("idr", "").toUpperCase();
    const badges = (p._badges || p.badges || []).map(badgeHtml).join("");
    return `
      <li data-pair="${p.pair}" onclick="selectPair('${p.pair}')">
        <div class="pair-row">
          <div class="pair-info">
            <span class="pair-name">${sym}</span>
            <span class="pair-price">${price}</span>
          </div>
          <div class="pair-meta">
            <span class="pair-change ${changeClass}">${changeText}</span>
            <span class="pair-volume">${volume}</span>
          </div>
        </div>
        ${badges ? `<div class="badges">${badges}</div>` : ""}
      </li>
    `;
  }).join("");
}

function badgeHtml(badge) {
  const map = {
    TOP_VOLUME: { cls: "badge-volume", label: "VOL" },
    TOP_GAINER: { cls: "badge-gainer", label: "GAIN" },
    TOP_LOSER: { cls: "badge-loser", label: "LOSS" },
    TOP_MOVER: { cls: "badge-mover", label: "MOVE" },
    PUMPING: { cls: "badge-pumping", label: "🚀 PUMP" },
  };
  const meta = map[badge] || { cls: "badge-volume", label: badge };
  return `<span class="badge ${meta.cls}">${meta.label}</span>`;
}

// ─── PAIR SELECTION ───────────────────────────────────────────────────────────

function selectPair(pair) {
  selectedPair = pair;
  document.querySelectorAll(".pairs-list li").forEach((li) => {
    li.classList.toggle("active", li.dataset.pair === pair);
  });

  const all = [...watchlistData, ...moversData, ...losersData];
  const info = all.find((p) => p.pair === pair);
  const sym = pair.replace("idr", "").toUpperCase() + "/IDR";
  document.getElementById("chart-pair").textContent = sym;

  if (info) {
    const lastPrice = info.last_price ?? info.last;
    document.getElementById("chart-price").textContent = lastPrice ? formatPrice(lastPrice) : "—";
    const change = info.change_percent || 0;
    const changeEl = document.getElementById("chart-change");
    changeEl.textContent = (change >= 0 ? "+" : "") + change.toFixed(2) + "%";
    changeEl.className = "chart-change " + (change > 0 ? "up" : change < 0 ? "down" : "neutral");
  }

  loadChart(pair);
  loadPairDetail(pair);
}

// ─── CHART ────────────────────────────────────────────────────────────────────

async function loadChart(pair) {
  const container = document.getElementById("chart-container");
  const activeBtn = document.querySelector(".tf-btn.active");
  const limit = activeBtn ? activeBtn.dataset.limit : 200;

  try {
    const res = await fetch(`${API_BASE}/api/v1/pairs/${pair}/chart?limit=${limit}`);
    const json = await res.json();
    if (!json.success || !json.data.candles.length) {
      container.innerHTML = '<div class="loading">Tidak ada data chart untuk pair ini</div>';
      return;
    }
    renderChart(json.data.candles);
  } catch (e) {
    container.innerHTML = `<div class="loading">Error memuat chart: ${e.message}</div>`;
  }
}

function renderChart(candles) {
  const container = document.getElementById("chart-container");
  container.innerHTML = "";

  const chartType = document.getElementById("chart-type").value;

  chart = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: container.clientHeight,
    layout: {
      background: { type: "solid", color: "#161b22" },
      textColor: "#8b949e",
      fontFamily: "-apple-system, BlinkMacSystemFont, Inter, sans-serif",
    },
    grid: {
      vertLines: { color: "#21262d" },
      horzLines: { color: "#21262d" },
    },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    timeScale: { timeVisible: true, secondsVisible: false, borderColor: "#30363d" },
    rightPriceScale: { borderColor: "#30363d" },
  });

  const data = candles.map((c) => ({
    time: Math.floor(new Date(c.timestamp).getTime() / 1000),
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
    value: c.close,
  })).sort((a, b) => a.time - b.time);

  if (chartType === "candle") {
    candleSeries = chart.addCandlestickSeries({
      upColor: "#3fb950",
      downColor: "#f85149",
      borderUpColor: "#3fb950",
      borderDownColor: "#f85149",
      wickUpColor: "#3fb950",
      wickDownColor: "#f85149",
    });
    candleSeries.setData(data);
  } else if (chartType === "line") {
    candleSeries = chart.addLineSeries({ color: "#58a6ff", lineWidth: 2 });
    candleSeries.setData(data.map((d) => ({ time: d.time, value: d.close })));
  } else {
    candleSeries = chart.addAreaSeries({
      topColor: "rgba(88, 166, 255, 0.3)",
      bottomColor: "rgba(88, 166, 255, 0.0)",
      lineColor: "#58a6ff",
      lineWidth: 2,
    });
    candleSeries.setData(data.map((d) => ({ time: d.time, value: d.close })));
  }

  chart.timeScale().fitContent();

  new ResizeObserver(() => {
    if (chart) {
      chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
    }
  }).observe(container);
}

// ─── PAIR DETAIL ──────────────────────────────────────────────────────────────

async function loadPairDetail(pair) {
  // Get latest signal for this pair
  try {
    const res = await fetch(`${API_BASE}/api/v1/signals/latest?pair=${pair}&limit=1`);
    const json = await res.json();
    if (json.success && json.data.signals.length) {
      const sig = json.data.signals[0];
      setDetail("d-signal", sig.recommendation || "—", signalClass(sig.recommendation));
      setDetail("d-confidence", sig.ml_confidence ? "Conf: " + (sig.ml_confidence * 100).toFixed(0) + "%" : "—");
      setDetail("d-strength", sig.combined_strength != null ? sig.combined_strength.toFixed(2) : "—");
    } else {
      setDetail("d-signal", "—");
      setDetail("d-confidence", "—");
      setDetail("d-strength", "—");
    }
  } catch (e) {
    console.error("Signal fetch error:", e);
  }

  // Market data from cached pair info
  const all = [...watchlistData, ...moversData, ...losersData];
  const info = all.find((p) => p.pair === pair);
  if (info) {
    setDetail("d-volume", formatVolume(info.volume_idr));
    if (info.rank || info.top_volume_rank) {
      setDetail("d-volume-rank", `Rank #${info.rank || info.top_volume_rank}`);
    } else {
      setDetail("d-volume-rank", "—");
    }
    if (info.spread_pct != null) {
      setDetail("d-spread", info.spread_pct.toFixed(3) + "%");
    } else if (info.bid && info.ask && info.ask >= info.bid) {
      const sp = ((info.ask - info.bid) / ((info.ask + info.bid) / 2)) * 100;
      setDetail("d-spread", sp.toFixed(3) + "%");
    } else {
      setDetail("d-spread", "—");
    }
  }

  // Position data
  const pos = positionsData.find((p) => p.pair === pair);
  if (pos) {
    setDetail("d-position", `${pos.type} @ ${formatPrice(pos.entry_price)}`);
    const pnl = pos.profit_loss || 0;
    const pnlPct = pos.profit_loss_pct || 0;
    setDetail("d-pnl", `${formatPrice(pnl)} IDR (${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(2)}%)`, pnl >= 0 ? "buy" : "sell");
  } else {
    setDetail("d-position", "No Position");
    setDetail("d-pnl", "—");
  }

  // R/R + S/R from latest signal analysis
  setDetail("d-rr", "—");
  setDetail("d-sr", "S/R");
}

function setDetail(id, value, cls) {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = value;
    if (cls !== undefined) {
      el.className = el.className.split(" ")[0] + (cls ? " " + cls : "");
    }
  }
}

function signalClass(rec) {
  if (!rec) return "";
  if (rec.includes("BUY")) return "buy";
  if (rec.includes("SELL")) return "sell";
  return "hold";
}

// ─── INSIGHTS PANEL ───────────────────────────────────────────────────────────

function renderInsights() {
  // Live movers (top 5 momentum + 3 losers)
  const liveList = document.getElementById("live-movers-list");
  const liveData = [...moversData.slice(0, 5), ...losersData.slice(0, 3)];
  if (!liveData.length) {
    liveList.innerHTML = '<li class="loading">Loading...</li>';
  } else {
    liveList.innerHTML = liveData.map((p) => {
      const change = p.change_percent || 0;
      const cls = change > 0 ? "up" : "down";
      const sym = p.pair.replace("idr", "").toUpperCase();
      return `
        <li onclick="selectPair('${p.pair}')">
          <span class="mini-pair">${sym}</span>
          <span class="mini-detail ${cls}">${change >= 0 ? "+" : ""}${change.toFixed(1)}%</span>
        </li>
      `;
    }).join("");
  }

  // Recent signals (latest 8 with BUY/SELL recommendation)
  const sigList = document.getElementById("recent-signals-list");
  const actionable = signalsData.filter((s) => s.recommendation && s.recommendation !== "HOLD").slice(0, 8);
  if (!actionable.length) {
    sigList.innerHTML = '<li class="loading">Belum ada sinyal aksi</li>';
  } else {
    sigList.innerHTML = actionable.map((s) => {
      const sym = (s.pair || "").replace("idr", "").toUpperCase();
      const cls = "signal-" + signalClass(s.recommendation);
      const conf = s.ml_confidence ? `${(s.ml_confidence * 100).toFixed(0)}%` : "—";
      return `
        <li class="${cls}" onclick="selectPair('${s.pair}')">
          <span class="mini-pair">${sym}</span>
          <span class="mini-detail">${s.recommendation} · ${conf}</span>
        </li>
      `;
    }).join("");
  }

  // Open positions
  const posList = document.getElementById("open-positions-list");
  if (!positionsData.length) {
    posList.innerHTML = '<li class="loading">Tidak ada posisi terbuka</li>';
  } else {
    posList.innerHTML = positionsData.map((p) => {
      const sym = (p.pair || "").replace("idr", "").toUpperCase();
      const pnlPct = p.profit_loss_pct || 0;
      const cls = pnlPct >= 0 ? "up" : "down";
      const pnlText = `${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(2)}%`;
      return `
        <li onclick="selectPair('${p.pair}')">
          <span class="mini-pair">${sym} · ${p.type}</span>
          <span class="mini-detail ${cls}">${pnlText}</span>
        </li>
      `;
    }).join("");
  }
}

// ─── TOPBAR STATS ────────────────────────────────────────────────────────────

function updateTopbarStats() {
  document.getElementById("stat-open-positions").textContent = positionsData.length;
  const totalPnl = positionsData.reduce((sum, p) => sum + (p.profit_loss || 0), 0);
  const pnlEl = document.getElementById("stat-today-pnl");
  pnlEl.textContent = totalPnl !== 0 ? formatPrice(totalPnl) + " IDR" : "—";
  pnlEl.className = "stat-mini-value " + (totalPnl > 0 ? "up" : totalPnl < 0 ? "down" : "");
  document.getElementById("stat-pairs-tracked").textContent = watchlistData.length;
}

// ─── SEARCH ──────────────────────────────────────────────────────────────────

function setupSearch() {
  document.getElementById("pair-search").addEventListener("input", (e) => {
    const query = e.target.value.toLowerCase();
    const data = activeTabData();
    const filtered = data.filter(
      (p) =>
        p.pair.includes(query) ||
        (p.display_pair && p.display_pair.toLowerCase().includes(query))
    );
    renderPairsList(filtered, activeTab);
  });
}

// ─── TIMEFRAMES & CHART TYPE ─────────────────────────────────────────────────

function setupTimeframes() {
  document.querySelectorAll(".tf-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tf-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      if (selectedPair) loadChart(selectedPair);
    });
  });
}

function setupChartType() {
  document.getElementById("chart-type").addEventListener("change", () => {
    if (selectedPair) loadChart(selectedPair);
  });
}

// ─── AUTO REFRESH ────────────────────────────────────────────────────────────

function startAutoRefresh() {
  setInterval(async () => {
    await refreshAll();
    if (selectedPair) loadPairDetail(selectedPair);
  }, REFRESH_INTERVAL_MS);
}

// ─── HELPERS ─────────────────────────────────────────────────────────────────

function formatPrice(value) {
  if (value === null || value === undefined) return "—";
  const num = Number(value);
  if (Number.isNaN(num)) return "—";
  if (Math.abs(num) >= 1000) return num.toLocaleString("id-ID", { maximumFractionDigits: 0 });
  if (Math.abs(num) >= 1) return num.toLocaleString("id-ID", { maximumFractionDigits: 2 });
  return num.toFixed(6);
}

function formatVolume(value) {
  if (!value || value <= 0) return "—";
  if (value >= 1e12) return `Rp${(value / 1e12).toFixed(1)}T`;
  if (value >= 1e9) return `Rp${(value / 1e9).toFixed(1)}B`;
  if (value >= 1e6) return `Rp${(value / 1e6).toFixed(0)}M`;
  if (value >= 1e3) return `Rp${(value / 1e3).toFixed(0)}K`;
  return `Rp${value.toFixed(0)}`;
}
