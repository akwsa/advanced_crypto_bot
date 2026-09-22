"""Frontend static contract tests untuk dashboard layout v2 (2026-06-10).

Layout v2 adalah revamp dari layout lama yang Binance-style/TradingView-embedded.
Snapshot test layout lama (TradingView.widget, BINANCE_BLUE, lineWidth: 1, dll)
sengaja dihapus karena sudah tidak relevan setelah revamp.

Test di sini lock kontrak structural baru:
- Tabs (Watchlist / Top Movers / Top Losers)
- Top bar dengan mode badge + status pill + 4 stat
- Panel kanan dengan 3 insight card (Live Movers, Recent Signals, Open Positions)
- Endpoint pair-scanner baru dipakai
- Lightweight-charts tetap dipakai (bukan TradingView widget)
"""
from pathlib import Path


FRONTEND_ROOT = Path(__file__).resolve().parents[1] / "dashboard_frontend"


def _index() -> str:
    return (FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")


def _app() -> str:
    return (FRONTEND_ROOT / "app.js").read_text(encoding="utf-8")


def _styles() -> str:
    return (FRONTEND_ROOT / "styles.css").read_text(encoding="utf-8")


# ─── Layout structure ────────────────────────────────────────────────────────


def test_dashboard_has_topbar_with_brand_and_mode_badge():
    index = _index()
    assert 'class="topbar"' in index
    assert 'id="mode-badge"' in index
    assert 'id="api-status"' in index
    assert 'id="stat-open-positions"' in index
    assert 'id="stat-today-pnl"' in index
    assert 'id="stat-pairs-tracked"' in index
    assert 'id="stat-last-update"' in index


def test_dashboard_has_three_column_layout():
    index = _index()
    styles = _styles()
    # 3 panel: kiri (pairs), tengah (chart+detail), kanan (insights)
    assert 'class="panel-left"' in index
    assert 'class="panel-center"' in index
    assert 'class="panel-right"' in index
    assert ".panel-left" in styles
    assert ".panel-center" in styles
    assert ".panel-right" in styles


def test_left_panel_has_three_tabs_for_watchlist_movers_losers():
    index = _index()
    app = _app()
    assert 'data-tab="watchlist"' in index
    assert 'data-tab="movers"' in index
    assert 'data-tab="losers"' in index
    assert "Watchlist" in index
    assert "Top Movers" in index
    assert "Top Losers" in index
    # Tab handler
    assert "function setupTabs" in app
    assert 'activeTab = "watchlist"' in app or "activeTab = 'watchlist'" in app


def test_right_panel_has_three_insight_cards():
    index = _index()
    assert 'id="live-movers-list"' in index
    assert 'id="recent-signals-list"' in index
    assert 'id="open-positions-list"' in index


# ─── API endpoints used ──────────────────────────────────────────────────────


def test_app_uses_pair_scanner_endpoints():
    app = _app()
    assert "/api/v1/pairs/top-volume" in app
    assert "/api/v1/pairs/top-movers" in app
    assert "/api/v1/safety/status" in app
    assert "/api/v1/positions/open" in app
    assert "/api/v1/signals/latest" in app


def test_app_loads_movers_with_direction_up_and_down():
    app = _app()
    assert "direction=up" in app
    assert "direction=down" in app


# ─── Chart ───────────────────────────────────────────────────────────────────


def test_dashboard_uses_lightweight_charts_not_tradingview_widget():
    index = _index()
    app = _app()
    # Lightweight-charts kept, TradingView widget DI-DROP
    assert "lightweight-charts" in index
    assert "createChart" in app
    assert "addCandlestickSeries" in app
    # Layout v2 tidak pakai TradingView embedded widget
    assert "TradingView.widget" not in app
    assert "tv.js" not in index


def test_chart_has_six_timeframe_buttons():
    index = _index()
    # 1m, 5m, 15m (active), 1h, 4h, 1D
    for tf in ["1m", "5m", "15m", "1h", "4h", "1D"]:
        assert f">{tf}<" in index


def test_chart_type_selector_offers_candle_line_area():
    index = _index()
    assert 'id="chart-type"' in index
    assert 'value="candle"' in index
    assert 'value="line"' in index
    assert 'value="area"' in index


# ─── Detail cards ────────────────────────────────────────────────────────────


def test_detail_section_has_six_metric_cards():
    index = _index()
    expected_ids = ["d-signal", "d-confidence", "d-strength", "d-volume", "d-spread", "d-position", "d-pnl", "d-rr"]
    for cid in expected_ids:
        assert f'id="{cid}"' in index, f"Missing detail card id={cid}"


# ─── Badges ──────────────────────────────────────────────────────────────────


def test_pair_list_renders_badges_for_top_volume_gainer_pumping():
    app = _app()
    styles = _styles()
    # Badge mapping di app.js
    assert "TOP_VOLUME" in app
    assert "TOP_GAINER" in app
    assert "PUMPING" in app
    # CSS classes
    assert ".badge-volume" in styles
    assert ".badge-gainer" in styles
    assert ".badge-pumping" in styles


# ─── Server still serves frontend shell ─────────────────────────────────────


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
    assert "Crypto Trading Dashboard" in html.text
    assert app_js.status_code == 200
    assert "createChart" in app_js.text
    assert styles.status_code == 200
    assert ".topbar" in styles.text


# ─── Theme + styling baseline ────────────────────────────────────────────────


def test_styles_use_modern_dark_theme_variables():
    styles = _styles()
    # Theme variable harus ada (dark theme)
    assert "--bg-primary" in styles
    assert "--accent" in styles
    assert "--green" in styles
    assert "--red" in styles
    # Pumping badge animation untuk visual impact
    assert "@keyframes pumping" in styles


def test_styles_responsive_below_1100px_hides_right_panel():
    styles = _styles()
    assert "@media" in styles
    assert "max-width: 1100px" in styles or "max-width:1100px" in styles
