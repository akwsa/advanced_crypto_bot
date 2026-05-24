from pathlib import Path


FRONTEND_ROOT = Path(__file__).resolve().parents[1] / "dashboard_frontend"


def test_frontend_embeds_tradingview_widget_for_positions_dashboard():
    index = (FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
    app = (FRONTEND_ROOT / "app.js").read_text(encoding="utf-8")

    assert "s3.tradingview.com/tv.js" in index
    assert "TradingView.widget" in app
    assert "/api/v1/positions/open" in app
    assert "tradingview_symbol" in app


def test_frontend_shows_dry_run_safety_banner():
    index = (FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
    app = (FRONTEND_ROOT / "app.js").read_text(encoding="utf-8")

    assert "DRY RUN LOCKED" in index
    assert "/api/v1/safety/status" in app
    assert "real_trading_locked" in app


def test_dashboard_api_serves_frontend_shell(monkeypatch, tmp_path):
    import importlib.util

    api_test_path = Path(__file__).resolve().parent / "test_dashboard_api_phase1.py"
    spec = importlib.util.spec_from_file_location("dashboard_api_phase1_test_helpers", api_test_path)
    helpers = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(helpers)

    client = helpers._create_client(monkeypatch, tmp_path)

    html = client.get("/")
    app_js = client.get("/app.js")
    styles = client.get("/styles.css")

    assert html.status_code == 200
    assert "DRY RUN LOCKED" in html.text
    assert app_js.status_code == 200
    assert "TradingView.widget" in app_js.text
    assert styles.status_code == 200
    assert "safety-banner" in styles.text


def test_frontend_compacts_detail_fonts_and_table_density():
    styles = (FRONTEND_ROOT / "styles.css").read_text(encoding="utf-8")

    assert "font-size: 14px;" in styles
    assert "td {\n  font-size: 0.84rem;" in styles
    assert "small { color: var(--muted); font-size: 0.72rem; }" in styles
    assert "padding: 0.55rem 0.65rem;" in styles


def test_frontend_uses_precise_local_lightweight_chart_for_selected_active_pair():
    index = (FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
    app = (FRONTEND_ROOT / "app.js").read_text(encoding="utf-8")

    assert "unpkg.com/lightweight-charts" in index
    assert "function renderLocalPairChart" in app
    assert "/api/v1/pairs/${encodeURIComponent(pair)}/chart" in app
    assert "selectedPair" in app
    assert "chartCandlestickSeries" in app
    assert "Pair Aktif Terpilih" in app
    assert "allow_symbol_change: false" in app


def test_frontend_exposes_custom_chart_model_selector_for_clearer_graphics():
    index = (FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
    app = (FRONTEND_ROOT / "app.js").read_text(encoding="utf-8")
    styles = (FRONTEND_ROOT / "styles.css").read_text(encoding="utf-8")

    assert "chart-model-select" in index
    assert "Garis Tegas" in index
    assert "Candle Jelas" in index
    assert "Area Trend" in index
    assert "TradingView" in index
    assert "let chartModel = 'clear-candles'" in app
    assert "function setChartModel" in app
    assert "addLineSeries" in app
    assert "addAreaSeries" in app
    assert "chart-model-select" in styles


def test_frontend_indodax_reference_chart_shows_all_pairs_above_min_volume_and_safe_visual_actions():
    index = (FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
    app = (FRONTEND_ROOT / "app.js").read_text(encoding="utf-8")
    styles = (FRONTEND_ROOT / "styles.css").read_text(encoding="utf-8")

    assert "Top Volume Indodax" in index
    assert "Volume > 500.000.000 IDR" in index
    assert "chart-timeframes" in index
    assert "trade-action-row" in index
    assert "READ-ONLY BUY" in index
    assert "READ-ONLY SELL" in index
    assert "/api/v1/pairs/top-volume" in app
    assert "?limit=33" not in app
    assert "renderTopVolumePairs" in app
    assert "wallet_status" in app
    assert "wallet-ready-pill" in app
    assert "SIAP JUAL" in app
    assert "SIAP BELI" in app
    assert "top_volume_rank" in app
    assert "function renderBotOverlay" in app
    assert "entry-line" in app
    assert "sl-line" in app
    assert "tp-line" in app
    assert "PnL" in app
    assert "signal" in app
    assert "addCandlestickSeries" in app
    assert "timeframe-button" in styles
    assert "wallet-ready-pill" in styles
    assert "sell-ready" in styles
    assert "buy-ready" in styles
    assert "action-buy" in styles
    assert "action-sell" in styles


def test_frontend_moves_status_groups_to_compact_footer_area():
    index = (FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
    styles = (FRONTEND_ROOT / "styles.css").read_text(encoding="utf-8")

    trades_pos = index.index('class="panel trades-panel"')
    status_pos = index.index('class="dashboard-status-footer"')
    footer_pos = index.index("<footer>")

    assert trades_pos < status_pos < footer_pos
    assert 'class="panel safety-panel compact-status-panel"' in index
    assert 'class="panel health-panel compact-status-panel"' in index
    assert ".dashboard-status-footer" in styles
    assert ".compact-status-panel" in styles
    assert "grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));" in styles
    assert "minmax(130px, 1fr)" in styles


def test_frontend_binance_style_chart_uses_red_blue_palette_and_requested_timeframes():
    index = (FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
    app = (FRONTEND_ROOT / "app.js").read_text(encoding="utf-8")
    styles = (FRONTEND_ROOT / "styles.css").read_text(encoding="utf-8")

    expected_timeframes = ['1m', '5m', '15m', '30m', '1h', '4h', '1D', '1Week']
    for timeframe in expected_timeframes:
        assert f'data-timeframe="{timeframe}"' in index
    assert 'data-timeframe="1d"' not in index

    assert "BINANCE_BLUE" in app
    assert "BINANCE_RED" in app
    assert "#2f6bff" in app
    assert "#f6465d" in app
    assert "rgba(47, 107, 255, 0.32)" in app
    assert "rgba(246, 70, 93, 0.32)" in app
    assert "#0b0e11" in app
    assert "#1e2329" in app
    assert "box-shadow: 0 0 0 1px rgba(47, 107, 255" in styles


def test_frontend_chart_graphics_use_clean_thin_high_contrast_lines():
    app = (FRONTEND_ROOT / "app.js").read_text(encoding="utf-8")

    assert "lineWidth: 1" in app
    assert "priceLineWidth: 1" in app
    assert "crosshairMarkerRadius: 2" in app
    assert "lastValueVisible: true" in app
    assert "#2f6bff" in app
    assert "#f6465d" in app
    # Guard against regressing back to thicker line styles from earlier iterations.
    assert "lineWidth: 4" not in app
    assert "lineWidth: 3" not in app
    assert "lineWidth: 2" not in app
    assert "priceLineWidth: 3" not in app
    assert "priceLineWidth: 2" not in app
    assert "crosshairMarkerRadius: 6" not in app
    assert "crosshairMarkerRadius: 4" not in app
    assert "crosshairMarkerRadius: 3" not in app
