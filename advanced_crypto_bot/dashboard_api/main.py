import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from dashboard_api.config import get_settings, safety_status

app = FastAPI(
    title="Advanced Crypto Bot Dashboard API",
    version="1.0.0-phase1-readonly",
    description="Read-only dashboard API. No trading/write routes in Phase 1.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _response(data: Any, *, source: str = "runtime", source_path: str | None = None, freshness: str = "fresh") -> dict:
    meta = {"timestamp": _utc_now(), "source": source, "freshness": freshness}
    if source_path is not None:
        meta["source_path"] = source_path
    return {"success": True, "data": data, "meta": meta}


def _normalize_pair(pair: str) -> str:
    normalized = str(pair or "").replace("/", "").replace("_", "").replace("-", "").lower()
    if normalized and not normalized.endswith("idr"):
        normalized = f"{normalized}idr"
    return normalized


def _display_pair(pair: str) -> str:
    normalized = _normalize_pair(pair).upper()
    if normalized.endswith("IDR") and len(normalized) > 3:
        return f"{normalized[:-3]}/IDR"
    return normalized


def _tradingview_symbol(pair: str) -> str:
    return f"INDODAX:{_normalize_pair(pair).upper()}"


def _is_idr_market(pair: str) -> bool:
    raw = str(pair or "").strip().lower()
    if not raw:
        return False
    underscored = raw.replace("/", "_").replace("-", "_")
    compact = raw.replace("/", "").replace("_", "").replace("-", "")
    return underscored.endswith("_idr") or compact.endswith("idr")


def _number_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _fetch_indodax_tickers() -> list[dict]:
    """Fetch public Indodax summaries without private/authenticated API calls."""
    from api.indodax_api import IndodaxAPI

    return IndodaxAPI(api_key="", secret_key="").get_all_tickers()


def _fetch_indodax_balance() -> dict | None:
    """Fetch read-only Indodax getInfo balance when API credentials are configured."""
    from api.indodax_api import IndodaxAPI
    from core.config import Config

    if not Config.IS_API_KEY_CONFIGURED:
        return None
    return IndodaxAPI().get_balance()


def _asset_from_pair(pair: str) -> str:
    normalized = _normalize_pair(pair)
    return normalized[:-3] if normalized.endswith("idr") else normalized


def _balance_funds(balance: dict | None) -> dict:
    """Return normalized available-balance funds from Indodax balance payloads.

    Indodax `getInfo` returns available funds under `balance`, while some older
    wrappers/tests use `funds`.  Do not fall back to the full top-level payload:
    it also contains metadata such as `server_time` and `user_id`, which are not
    wallet assets.
    """
    if not isinstance(balance, dict):
        return {}
    raw_funds = balance.get("funds")
    if not isinstance(raw_funds, dict):
        raw_funds = balance.get("balance")
    if not isinstance(raw_funds, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, value in raw_funds.items():
        normalized_key = str(key or "").strip().lower().replace("/", "").replace("_", "").replace("-", "")
        if normalized_key:
            normalized[normalized_key] = value
    return normalized


def _wallet_status_for_pair(pair: str, last_price: Any, funds: dict) -> dict:
    asset = _asset_from_pair(pair)
    asset_balance = _number_or_none(funds.get(asset)) or 0.0
    idr_balance = _number_or_none(funds.get("idr")) or 0.0
    price = _number_or_none(last_price) or 0.0
    asset_value_idr = asset_balance * price if price > 0 else 0.0
    sell_ready = asset_balance > 0
    buy_ready = idr_balance > 0
    if sell_ready and buy_ready:
        status = "sell_and_buy_ready"
        label = "SIAP JUAL & BELI"
    elif sell_ready:
        status = "sell_ready"
        label = "SIAP JUAL"
    elif buy_ready:
        status = "buy_ready"
        label = "SIAP BELI"
    else:
        status = "watch_only"
        label = "PANTAU"
    return {
        "asset": asset,
        "asset_balance": asset_balance,
        "asset_value_idr": asset_value_idr,
        "idr_balance": idr_balance,
        "sell_ready": sell_ready,
        "buy_ready": buy_ready,
        "status": status,
        "label": label,
    }


def _annotate_wallet_status(pairs: list[dict], balance: dict | None) -> dict:
    funds = _balance_funds(balance)
    idr_balance = _number_or_none(funds.get("idr")) or 0.0
    wallet = {
        "available": bool(funds),
        "idr_balance": idr_balance,
        "source": "indodax_private_getInfo_readonly" if funds else "unavailable",
    }
    for pair in pairs:
        pair["wallet_status"] = _wallet_status_for_pair(pair.get("pair", ""), pair.get("last_price"), funds)
    return wallet


MIN_DASHBOARD_VOLUME_IDR = 500_000_000


def _top_volume_pairs(limit: int | None = None, min_volume_idr: float = MIN_DASHBOARD_VOLUME_IDR) -> list[dict]:
    safe_limit = None if limit is None else max(1, int(limit))
    tickers = _fetch_indodax_tickers()
    markets: list[dict] = []
    seen: set[str] = set()
    for ticker in tickers:
        raw_pair = str(ticker.get("pair", ""))
        if not _is_idr_market(raw_pair):
            continue
        pair = _normalize_pair(raw_pair)
        if not pair or pair in seen:
            continue
        seen.add(pair)
        volume_idr = _number_or_none(ticker.get("volume_idr", ticker.get("volume"))) or 0.0
        if volume_idr <= min_volume_idr:
            continue
        markets.append(
            {
                "pair": pair,
                "display_pair": _display_pair(pair),
                "tradingview_symbol": _tradingview_symbol(pair),
                "last_price": _number_or_none(ticker.get("last")),
                "high": _number_or_none(ticker.get("high")),
                "low": _number_or_none(ticker.get("low")),
                "bid": _number_or_none(ticker.get("bid")),
                "ask": _number_or_none(ticker.get("ask")),
                "change_percent": _number_or_none(ticker.get("change_percent")),
                "volume_idr": volume_idr,
                "volume_coin": _number_or_none(ticker.get("volume_coin")),
                "is_active": True,
                "price_freshness": "live-public",
            }
        )
    markets.sort(key=lambda item: item["volume_idr"], reverse=True)
    selected = markets if safe_limit is None else markets[:safe_limit]
    for index, market in enumerate(selected, start=1):
        market["top_volume_rank"] = index
    return selected


def _is_top_volume_pair(pair: str) -> bool:
    normalized = _normalize_pair(pair)
    return any(item["pair"] == normalized for item in _top_volume_pairs(33))


def _sql_normalized_pair(column: str = "pair") -> str:
    return f"LOWER(REPLACE(REPLACE(REPLACE({column}, '/', ''), '_', ''), '-', ''))"


def _is_active_pair(conn: sqlite3.Connection, pair: str) -> bool:
    row = conn.execute(
        f"""
        SELECT 1
        FROM watchlist
        WHERE COALESCE(is_active, 1) = 1
          AND {_sql_normalized_pair('pair')} = ?
        LIMIT 1
        """,
        (_normalize_pair(pair),),
    ).fetchone()
    return row is not None


def _connect_readonly(db_path: str) -> sqlite3.Connection:
    resolved = Path(db_path).expanduser().resolve()
    uri = f"file:{resolved}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def _row_get(row: sqlite3.Row, key: str, default: Any = None) -> Any:
    return row[key] if key in row.keys() else default


def _db_status(path: str) -> dict:
    try:
        resolved = str(Path(path).expanduser().resolve())
        with _connect_readonly(path) as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "online", "path": resolved, "read_only": True}
    except Exception as exc:
        return {"status": "offline", "path": path, "read_only": True, "error": str(exc)}


def _trade_payload(row: sqlite3.Row) -> dict:
    pair = _normalize_pair(str(_row_get(row, "pair", "") or ""))
    return {
        "id": _row_get(row, "id"),
        "user_id": _row_get(row, "user_id"),
        "pair": pair,
        "display_pair": _display_pair(pair),
        "type": _row_get(row, "type"),
        "entry_price": _row_get(row, "price"),
        "current_price": None,
        "amount": _row_get(row, "amount"),
        "total": _row_get(row, "total"),
        "fee": _row_get(row, "fee"),
        "signal_source": _row_get(row, "signal_source"),
        "ml_confidence": _row_get(row, "ml_confidence"),
        "status": _row_get(row, "status"),
        "opened_at": _row_get(row, "opened_at"),
        "closed_at": _row_get(row, "closed_at"),
        "profit_loss": _row_get(row, "profit_loss"),
        "profit_loss_pct": _row_get(row, "profit_loss_pct"),
        "unrealized_pnl": None,
        "unrealized_pnl_pct": None,
        "mode": "DRY_RUN" if safety_status()["auto_trade_dry_run"] else "REAL",
        "tradingview_symbol": _tradingview_symbol(pair),
        "source": "sqlite",
    }


_FRONTEND_ROOT = Path(__file__).resolve().parents[1] / "dashboard_frontend"


@app.get("/", include_in_schema=False)
def dashboard_index() -> FileResponse:
    return FileResponse(_FRONTEND_ROOT / "index.html")


@app.get("/app.js", include_in_schema=False)
def dashboard_app_js() -> FileResponse:
    return FileResponse(_FRONTEND_ROOT / "app.js", media_type="application/javascript")


@app.get("/styles.css", include_in_schema=False)
def dashboard_styles() -> FileResponse:
    return FileResponse(_FRONTEND_ROOT / "styles.css", media_type="text/css")


@app.get("/api/v1/health")
def health() -> dict:
    settings = get_settings()
    return _response(
        {
            "api_status": "online",
            "trading_db_path": settings.trading_db_path,
            "signals_db_path": settings.signals_db_path,
            "read_only": True,
        }
    )


@app.get("/api/v1/safety/status")
def get_safety_status() -> dict:
    return _response(safety_status(), source="config/runtime")


@app.get("/api/v1/system/data-sources")
def get_data_sources() -> dict:
    settings = get_settings()
    data = {
        "trading_db": _db_status(settings.trading_db_path),
        "signals_db": _db_status(settings.signals_db_path),
        "redis": {"status": "unknown", "read_only": True, "note": "Redis optional in Phase 1"},
        "dashboard_write_enabled": False,
    }
    freshness = "fresh" if data["trading_db"]["status"] == "online" and data["signals_db"]["status"] == "online" else "stale"
    return _response(data, source="mixed", freshness=freshness)


@app.get("/api/v1/pairs/active")
def get_active_pairs() -> dict:
    settings = get_settings()
    pairs: list[dict] = []
    with _connect_readonly(settings.trading_db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, pair, added_at, is_active
            FROM watchlist
            WHERE COALESCE(is_active, 1) = 1
            ORDER BY added_at ASC, id ASC
            """
        ).fetchall()
    for row in rows:
        pair = _normalize_pair(_row_get(row, "pair", ""))
        pairs.append(
            {
                "id": _row_get(row, "id"),
                "user_id": _row_get(row, "user_id"),
                "pair": pair,
                "display_pair": _display_pair(pair),
                "is_active": bool(_row_get(row, "is_active", 1)),
                "added_at": _row_get(row, "added_at"),
                "last_price": None,
                "price_freshness": "unknown",
                "tradingview_symbol": _tradingview_symbol(pair),
            }
        )
    return _response({"pairs": pairs, "count": len(pairs)}, source="sqlite", source_path=settings.trading_db_path, freshness="empty" if not pairs else "fresh")


@app.get("/api/v1/pairs/top-volume")
def get_top_volume_pairs(limit: int | None = None) -> dict:
    """Return all Indodax IDR markets above the dashboard's minimum 24h IDR volume threshold."""
    safe_limit = None if limit is None else max(1, int(limit))
    pairs = _top_volume_pairs(safe_limit)
    wallet = _annotate_wallet_status(pairs, _fetch_indodax_balance())
    return _response(
        {"pairs": pairs, "count": len(pairs), "limit": safe_limit, "min_volume_idr": MIN_DASHBOARD_VOLUME_IDR, "wallet": wallet},
        source="indodax_public_summaries",
        freshness="empty" if not pairs else "fresh",
    )


@app.get("/api/v1/pairs/top-movers")
def get_top_movers(limit: int = 30, direction: str = "up", min_volume_idr: float = 500_000_000) -> dict:
    """Return top momentum pairs (gainers/losers/both) with composite scoring.

    Args:
        limit: jumlah pair (1-50).
        direction: "up" (gainers, default), "down" (losers), "both" (absolute).
        min_volume_idr: filter volume minimum (default 500M IDR exclude shitcoin).

    Backed by autohunter.pair_scanner — Indodax public summaries, no auth.
    """
    from autohunter.pair_scanner import scan_top_movers

    safe_limit = max(1, min(int(limit), 50))
    safe_direction = direction.lower() if direction else "up"
    if safe_direction not in {"up", "down", "both"}:
        safe_direction = "up"
    snapshots = scan_top_movers(limit=safe_limit, min_volume_idr=min_volume_idr, direction=safe_direction)
    pairs = [s.to_dict() for s in snapshots]
    return _response(
        {"pairs": pairs, "count": len(pairs), "limit": safe_limit, "direction": safe_direction, "min_volume_idr": min_volume_idr},
        source="indodax_public_summaries",
        freshness="empty" if not pairs else "fresh",
    )


@app.get("/api/v1/pairs/watchlist-recommendation")
def get_watchlist_recommendation(top_volume: int = 20, top_movers: int = 10) -> dict:
    """Combined watchlist suggestion: top volume + top momentum movers.

    Useful for "should I watch this?" UI — returns merged unique list with
    badges (TOP_VOLUME, TOP_GAINER, PUMPING).
    """
    from autohunter.pair_scanner import build_watchlist_recommendation

    safe_volume = max(1, min(int(top_volume), 50))
    safe_movers = max(0, min(int(top_movers), 30))
    snapshots = build_watchlist_recommendation(top_volume_limit=safe_volume, top_mover_limit=safe_movers)
    pairs = [s.to_dict() for s in snapshots]
    return _response(
        {"pairs": pairs, "count": len(pairs), "top_volume_limit": safe_volume, "top_mover_limit": safe_movers},
        source="indodax_public_summaries",
        freshness="empty" if not pairs else "fresh",
    )


@app.get("/api/v1/signals/latest")
def get_latest_signals(limit: int = 50, pair: str | None = None) -> dict:
    settings = get_settings()
    safe_limit = max(1, min(int(limit), 500))
    clauses: list[str] = []
    params: list[Any] = []
    if pair:
        clauses.append("LOWER(REPLACE(symbol, '/', '')) = ?")
        params.append(_normalize_pair(pair))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect_readonly(settings.signals_db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT id, symbol, price, recommendation, ml_confidence,
                   combined_strength, analysis, signal_time, received_at,
                   received_date, source, created_at
            FROM signals
            {where}
            ORDER BY COALESCE(received_at, created_at) DESC, id DESC
            LIMIT ?
            """,
            [*params, safe_limit],
        ).fetchall()
    signals = []
    for row in rows:
        normalized = _normalize_pair(_row_get(row, "symbol", ""))
        signals.append(
            {
                "id": _row_get(row, "id"),
                "pair": normalized,
                "display_pair": _display_pair(normalized),
                "price": _row_get(row, "price"),
                "recommendation": _row_get(row, "recommendation"),
                "ml_confidence": _row_get(row, "ml_confidence"),
                "combined_strength": _row_get(row, "combined_strength"),
                "analysis": _row_get(row, "analysis"),
                "signal_time": _row_get(row, "signal_time"),
                "received_at": _row_get(row, "received_at"),
                "received_date": _row_get(row, "received_date"),
                "source": _row_get(row, "source"),
                "created_at": _row_get(row, "created_at"),
                "tradingview_symbol": _tradingview_symbol(normalized),
            }
        )
    return _response({"signals": signals, "count": len(signals)}, source="sqlite", source_path=settings.signals_db_path, freshness="empty" if not signals else "fresh")


@app.get("/api/v1/trades/history")
def get_trade_history(status: str = "all", limit: int = 100) -> dict:
    settings = get_settings()
    safe_limit = max(1, min(int(limit), 1000))
    clauses: list[str] = []
    params: list[Any] = []
    if status.lower() in {"open", "closed"}:
        clauses.append("UPPER(COALESCE(status, '')) = ?")
        params.append(status.upper())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _connect_readonly(settings.trading_db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT id, user_id, pair, type, price, amount, total, fee,
                   signal_source, ml_confidence, status, opened_at,
                   closed_at, profit_loss, profit_loss_pct
            FROM trades
            {where}
            ORDER BY COALESCE(opened_at, closed_at) DESC, id DESC
            LIMIT ?
            """,
            [*params, safe_limit],
        ).fetchall()
    trades = [_trade_payload(row) for row in rows]
    return _response({"trades": trades, "count": len(trades)}, source="sqlite", source_path=settings.trading_db_path, freshness="empty" if not trades else "fresh")


@app.get("/api/v1/pairs/{pair}/chart")
def get_pair_chart(pair: str, limit: int = 200) -> dict:
    """Return chart candles for one selected active pair using bot.py's DB history method semantics.

    bot.py::_get_chart_history_for_pair ultimately falls back to
    Database.get_price_history(pair, limit=N): read the latest N DB candles for
    the requested normalized pair and sort them oldest -> newest. The dashboard
    mirrors that behavior in read-only SQL so it can render an accurate local
    chart without importing or constructing the Telegram bot runtime.
    """
    settings = get_settings()
    normalized = _normalize_pair(pair)
    safe_limit = max(1, min(int(limit), 1000))
    with _connect_readonly(settings.trading_db_path) as conn:
        selected_from_active_pairs = _is_active_pair(conn, normalized)
        selected_from_top_volume = False if selected_from_active_pairs else _is_top_volume_pair(normalized)
        if not selected_from_active_pairs and not selected_from_top_volume:
            raise HTTPException(
                status_code=404,
                detail={"code": "pair_not_active", "pair": normalized, "message": "Chart hanya tersedia untuk pair aktif atau Top 33 Volume Indodax."},
            )
        rows = conn.execute(
            f"""
            SELECT timestamp, open, high, low, close, volume
            FROM (
                SELECT id, timestamp, open, high, low, close, volume
                FROM price_history
                WHERE {_sql_normalized_pair('pair')} = ?
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
            ) latest
            ORDER BY timestamp ASC, id ASC
            """,
            (normalized, safe_limit),
        ).fetchall()
    candles = [
        {
            "timestamp": _row_get(row, "timestamp"),
            "time": _row_get(row, "timestamp"),
            "open": _row_get(row, "open"),
            "high": _row_get(row, "high"),
            "low": _row_get(row, "low"),
            "close": _row_get(row, "close"),
            "value": _row_get(row, "close"),
            "volume": _row_get(row, "volume"),
        }
        for row in rows
    ]
    return _response(
        {
            "pair": normalized,
            "display_pair": _display_pair(normalized),
            "tradingview_symbol": _tradingview_symbol(normalized),
            "chart_renderer": "lightweight-charts",
            "chart_method": "bot._get_chart_history_for_pair/db.get_price_history",
            "selected_from_active_pairs": selected_from_active_pairs,
            "selected_from_top_volume": selected_from_top_volume,
            "candles": candles,
            "count": len(candles),
        },
        source="sqlite",
        source_path=settings.trading_db_path,
        freshness="empty" if not candles else "fresh",
    )


@app.get("/api/v1/events/stream")
def event_stream(once: bool = False) -> StreamingResponse:
    def generate():
        payload = {"timestamp": _utc_now(), "read_only": True, "type": "heartbeat"}
        yield f"event: heartbeat\ndata: {json.dumps(payload)}\n\n"
        if not once:
            return

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/v1/positions/open")
def get_open_positions() -> dict:
    settings = get_settings()
    positions: list[dict] = []
    with _connect_readonly(settings.trading_db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, pair, type, price, amount, total, fee,
                   signal_source, ml_confidence, status, opened_at,
                   closed_at, profit_loss, profit_loss_pct
            FROM trades
            WHERE UPPER(COALESCE(status, '')) = 'OPEN'
            ORDER BY opened_at DESC, id DESC
            """
        ).fetchall()

    for row in rows:
        positions.append(_trade_payload(row))

    freshness = "empty" if not positions else "fresh"
    return _response(
        {"positions": positions, "count": len(positions)},
        source="sqlite",
        source_path=settings.trading_db_path,
        freshness=freshness,
    )
