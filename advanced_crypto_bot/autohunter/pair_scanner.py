#!/usr/bin/env python3
# Tujuan: Scan Indodax pairs untuk identifikasi top volume + top movers
#         supaya bot bisa auto-promote pair yang lagi aktif/momentum tinggi
#         ke watchlist tanpa user perlu manually add.
# Caller: bot.AdvancedCryptoBot (background loop) + Telegram commands
#         + dashboard_api/main.py (read-only endpoint).
# Dependensi: api.indodax_api.IndodaxAPI.get_all_tickers (public endpoint),
#             core.config.Config.
# Main Functions: scan_top_volume, scan_top_movers, build_watchlist_recommendation.
# Side Effects: HTTP call ke Indodax /api/summaries (public, no auth).
"""Pair scanner untuk auto-watchlist.

Indodax `/api/summaries` mengembalikan SEMUA pair dengan ticker (last, high,
low, bid, ask, vol_idr, change_percent). Module ini memberi 2 view:

1. **TOP VOLUME** — pair dengan volume IDR 24 jam terbesar. Mencerminkan
   "pair yang sedang banyak diperdagangkan" — biasanya likuid, spread tipis,
   relatif aman untuk autotrade.

2. **TOP MOVERS** — pair dengan momentum harga tinggi. Scoring kombinasi:
   - `change_percent` 24h (signed) — base score
   - Filter volume minimum (default 500jt IDR) — exclude shitcoin tipis
   - Bonus untuk pair yang dekat dengan high 24h (sedang trending up,
     bukan pump-and-dump yang sudah collapse)
   - Penalty untuk spread besar (proxy illiquidity)

Output kedua-duanya di-cache 60 detik supaya tidak hammering API.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("crypto_bot")


# ─── Cache ───────────────────────────────────────────────────────────────────

_CACHE: dict[str, dict] = {}
_CACHE_TTL_SEC = 60


def _cache_get(key: str) -> Any:
    entry = _CACHE.get(key)
    if not entry:
        return None
    if time.time() - entry["t"] > _CACHE_TTL_SEC:
        return None
    return entry["v"]


def _cache_set(key: str, value: Any) -> None:
    _CACHE[key] = {"t": time.time(), "v": value}


def _cache_invalidate() -> None:
    _CACHE.clear()


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _is_idr_market(pair: str) -> bool:
    raw = str(pair or "").strip().lower()
    if not raw:
        return False
    return raw.replace("/", "").replace("_", "").replace("-", "").endswith("idr")


def _normalize_pair(pair: str) -> str:
    return str(pair or "").replace("/", "").replace("_", "").replace("-", "").lower()


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


# ─── Data classes ────────────────────────────────────────────────────────────


@dataclass
class PairSnapshot:
    pair: str  # normalized lowercase, e.g. "btcidr"
    last: float
    high: float
    low: float
    bid: float
    ask: float
    volume_idr: float
    change_percent: float | None
    score: float = 0.0
    rank: int = 0
    badges: list[str] = field(default_factory=list)

    @property
    def display_pair(self) -> str:
        norm = self.pair.upper()
        if norm.endswith("IDR") and len(norm) > 3:
            return f"{norm[:-3]}/IDR"
        return norm

    @property
    def spread_pct(self) -> float | None:
        """Spread (ask - bid) / mid in percentage. None kalau bid/ask 0."""
        if self.bid > 0 and self.ask > 0 and self.ask >= self.bid:
            mid = (self.bid + self.ask) / 2
            if mid > 0:
                return ((self.ask - self.bid) / mid) * 100
        return None

    @property
    def distance_from_high_pct(self) -> float | None:
        """Persen jarak harga sekarang dari high 24h. 0 = di puncak, 5 = 5% di bawah."""
        if self.high > 0 and self.last > 0:
            return max(0.0, ((self.high - self.last) / self.high) * 100)
        return None

    @property
    def distance_from_low_pct(self) -> float | None:
        """Persen jarak harga sekarang dari low 24h. 0 = di lantai, 5 = 5% di atas."""
        if self.low > 0 and self.last > 0:
            return max(0.0, ((self.last - self.low) / self.last) * 100)
        return None

    def to_dict(self) -> dict:
        return {
            "pair": self.pair,
            "display_pair": self.display_pair,
            "last": self.last,
            "high": self.high,
            "low": self.low,
            "bid": self.bid,
            "ask": self.ask,
            "volume_idr": self.volume_idr,
            "change_percent": self.change_percent,
            "spread_pct": self.spread_pct,
            "distance_from_high_pct": self.distance_from_high_pct,
            "distance_from_low_pct": self.distance_from_low_pct,
            "score": round(self.score, 4),
            "rank": self.rank,
            "badges": list(self.badges),
        }


# ─── Core fetch ──────────────────────────────────────────────────────────────


def _fetch_tickers(indodax_api) -> list[dict]:
    """Wrapper supaya gampang di-mock di test.

    `indodax_api` harus punya method `get_all_tickers()` yang return list of
    dict dengan key: pair, last, high, low, bid, ask, volume, change_percent.
    """
    if indodax_api is None:
        from api.indodax_api import IndodaxAPI

        indodax_api = IndodaxAPI(api_key="", secret_key="")
    return indodax_api.get_all_tickers()


def _build_snapshots(raw_tickers: list[dict]) -> list[PairSnapshot]:
    """Convert list raw ticker dict ke PairSnapshot (filter IDR-only & valid)."""
    snapshots: list[PairSnapshot] = []
    seen: set[str] = set()
    for t in raw_tickers or []:
        raw_pair = str(t.get("pair", ""))
        if not _is_idr_market(raw_pair):
            continue
        pair = _normalize_pair(raw_pair)
        if not pair or pair in seen:
            continue
        seen.add(pair)
        snap = PairSnapshot(
            pair=pair,
            last=_safe_float(t.get("last")),
            high=_safe_float(t.get("high")),
            low=_safe_float(t.get("low")),
            bid=_safe_float(t.get("bid", t.get("buy"))),
            ask=_safe_float(t.get("ask", t.get("sell"))),
            volume_idr=_safe_float(t.get("volume", t.get("vol_idr"))),
            change_percent=_safe_float(t.get("change_percent"), default=None)
            if t.get("change_percent") is not None
            else None,
        )
        # Skip pair tanpa harga atau volume valid
        if snap.last <= 0 or snap.volume_idr <= 0:
            continue
        snapshots.append(snap)
    return snapshots


# ─── Scanners ────────────────────────────────────────────────────────────────


def scan_top_volume(
    indodax_api=None,
    limit: int = 30,
    min_volume_idr: float = 100_000_000,
    use_cache: bool = True,
) -> list[PairSnapshot]:
    """Top N pair berdasarkan volume IDR 24 jam.

    Args:
        indodax_api: instance IndodaxAPI (atau None → inisialisasi otomatis).
        limit: jumlah pair yang dikembalikan (default 30).
        min_volume_idr: filter volume minimum IDR untuk exclude pair tipis.
        use_cache: kalau True, return cached result kalau masih fresh (60 detik).

    Returns:
        List PairSnapshot, sudah di-rank, badge "TOP_VOLUME" untuk semua entry.
    """
    cache_key = f"top_volume:{limit}:{min_volume_idr}"
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
    try:
        tickers = _fetch_tickers(indodax_api)
        snapshots = _build_snapshots(tickers)
        # Filter volume minimum
        snapshots = [s for s in snapshots if s.volume_idr >= min_volume_idr]
        # Sort by volume desc
        snapshots.sort(key=lambda s: s.volume_idr, reverse=True)
        result = snapshots[: max(1, int(limit))]
        for i, s in enumerate(result, start=1):
            s.rank = i
            s.score = s.volume_idr  # score = volume
            s.badges.append("TOP_VOLUME")
        _cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.error(f"❌ scan_top_volume failed: {e}")
        return []


def _momentum_score(snap: PairSnapshot) -> float:
    """Score momentum gabungan untuk satu snapshot.

    Komponen:
    - **base** = `change_percent` (24h). Negatif → score negatif (penalty).
    - **trend_alive** = bonus kalau harga dekat high 24h (masih trending).
      Skala 0..5 (semakin dekat puncak semakin tinggi).
    - **volume_factor** = `log10(volume_idr)` × 0.5. Bonus untuk likuiditas.
    - **liquidity_penalty** = -2 kalau spread > 1%, -5 kalau spread > 2%.

    Score akhir adalah jumlah komponen. Pair dengan change negatif tetap
    bisa masuk top movers tapi di urutan bawah; downside-mover tidak ditarget
    autotrade BUY tapi tetap berguna untuk dashboard.
    """
    if snap.change_percent is None:
        return -999  # exclude pair tanpa data 24h
    base = snap.change_percent
    # Bonus dekat high (5% jauh = 0 bonus, 0% jauh = 5 bonus)
    dist_high = snap.distance_from_high_pct
    trend_alive = max(0.0, 5.0 - dist_high) if dist_high is not None else 0.0
    # Volume factor
    volume_factor = 0.5 * math.log10(max(1.0, snap.volume_idr))
    # Liquidity penalty (proxy: spread besar = pair tipis)
    spread = snap.spread_pct
    if spread is None:
        liquidity_penalty = -3  # tidak bisa hitung spread = suspicious
    elif spread > 2.0:
        liquidity_penalty = -5
    elif spread > 1.0:
        liquidity_penalty = -2
    else:
        liquidity_penalty = 0
    return base + trend_alive + volume_factor + liquidity_penalty


def scan_top_movers(
    indodax_api=None,
    limit: int = 30,
    min_volume_idr: float = 500_000_000,
    use_cache: bool = True,
    direction: str = "up",
) -> list[PairSnapshot]:
    """Top N pair berdasarkan momentum harga.

    Args:
        indodax_api: instance IndodaxAPI.
        limit: jumlah pair.
        min_volume_idr: filter volume minimum (default 500jt IDR — exclude
            pair yang gerak liar tapi tipis = pump-and-dump risk).
        use_cache: gunakan cache 60 detik.
        direction: "up" → sort score desc (gainers), "down" → asc (losers),
            "both" → return sort by absolute change.

    Returns:
        List PairSnapshot dengan badge yang sesuai (TOP_GAINER/TOP_LOSER).
    """
    cache_key = f"top_movers:{limit}:{min_volume_idr}:{direction}"
    if use_cache:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached
    try:
        tickers = _fetch_tickers(indodax_api)
        snapshots = _build_snapshots(tickers)
        snapshots = [s for s in snapshots if s.volume_idr >= min_volume_idr]
        # Hitung score untuk semua
        for s in snapshots:
            s.score = _momentum_score(s)
        # Drop pair dengan score sentinel (-999 = tidak ada change_percent)
        snapshots = [s for s in snapshots if s.score > -100]
        # Sort sesuai direction
        if direction == "down":
            snapshots.sort(key=lambda s: s.score)
            badge = "TOP_LOSER"
        elif direction == "both":
            snapshots.sort(key=lambda s: abs(s.change_percent or 0), reverse=True)
            badge = "TOP_MOVER"
        else:
            snapshots.sort(key=lambda s: s.score, reverse=True)
            badge = "TOP_GAINER"
        result = snapshots[: max(1, int(limit))]
        for i, s in enumerate(result, start=1):
            s.rank = i
            s.badges.append(badge)
            # Bonus badge "PUMPING" kalau dekat puncak + change > 5%
            if (
                s.distance_from_high_pct is not None
                and s.distance_from_high_pct < 1.5
                and (s.change_percent or 0) > 5
            ):
                s.badges.append("PUMPING")
        _cache_set(cache_key, result)
        return result
    except Exception as e:
        logger.error(f"❌ scan_top_movers failed: {e}")
        return []


# ─── Watchlist recommendation ────────────────────────────────────────────────


def build_watchlist_recommendation(
    indodax_api=None,
    top_volume_limit: int = 20,
    top_mover_limit: int = 10,
    min_volume_for_movers: float = 500_000_000,
    exclude: set[str] | None = None,
) -> list[PairSnapshot]:
    """Build rekomendasi watchlist gabungan: top volume + top movers.

    Logic:
    1. Ambil top N volume (likuid, aman) — biasanya BTC/ETH/SOL/USDT/XRP/BNB.
    2. Ambil top M movers (momentum), exclude yang sudah ada di top volume.
    3. Merge — hasil maksimal `top_volume_limit + top_mover_limit` pair unik.

    Args:
        exclude: set normalized pair yang harus di-skip (misal blacklist user).
    Returns:
        List PairSnapshot ready untuk auto-promote.
    """
    exclude = exclude or set()
    tv = scan_top_volume(indodax_api, limit=top_volume_limit)
    tm = scan_top_movers(indodax_api, limit=top_mover_limit, min_volume_idr=min_volume_for_movers)

    seen: set[str] = set(exclude)
    merged: list[PairSnapshot] = []
    for s in tv:
        if s.pair in seen:
            continue
        seen.add(s.pair)
        merged.append(s)
    for s in tm:
        if s.pair in seen:
            continue
        seen.add(s.pair)
        merged.append(s)
    # Re-rank gabungan (urutan: top volume dulu, lalu top movers)
    for i, s in enumerate(merged, start=1):
        s.rank = i
    return merged
