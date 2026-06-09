# Tujuan: Sentiment analysis dari berita crypto untuk augment signal pipeline.
# Caller: signal_pipeline.py (generate_signal_for_pair).
# Dependensi: requests, core.config (SENTIMENT_*).
# Main Functions: get_sentiment_for_pair, SentimentAnalyzer.
# Side Effects: HTTP GET ke CryptoPanic API; in-memory cache.
#
# Konsep diadaptasi dari Meridian-main/agent.py get_crypto_sentiment().
# Diimplementasikan ulang untuk arsitektur bot utama:
# - Keyword-based scoring (tanpa LLM) supaya ringan & deterministic
# - In-memory cache per pair (TTL 15 menit) untuk hindari API spam
# - Graceful failure: selalu return NEUTRAL jika API error
# - Mapping pair Indodax → simbol CryptoPanic (btcidr → BTC, dll)
"""Sentiment analysis module for crypto trading signals.

Fetches recent news headlines from CryptoPanic API and scores them
using keyword-based analysis. Returns BULLISH/BEARISH/NEUTRAL with
a numeric score (-10 to +10).

Integration points:
- signal_pipeline.py: enriches signal dict with sentiment data
- signal_decision_layer.py: sentiment can boost/downgrade BUY classification
- autotrade/runtime.py: sentiment can augment Market Intelligence filter

Adapted from Meridian-main/agent.py get_crypto_sentiment() — concept only,
reimplemented with keyword scoring (no LLM dependency) for speed and
determinism in the main bot's signal pipeline.
"""

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

import requests

from core.config import Config

logger = logging.getLogger("crypto_bot")

# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass(frozen=True)
class SentimentResult:
    """Hasil analisis sentimen untuk satu pair/token.

    Attributes:
        sentiment: Label sentimen — "BULLISH", "BEARISH", atau "NEUTRAL"
        score: Skor numerik dari -10 (sangat bearish) sampai +10 (sangat bullish)
        summary: Ringkasan satu kalimat tentang mood market
        headline_count: Jumlah berita yang dianalisis
        source: Sumber data ("cryptopanic", "cache", "fallback")
        timestamp: Waktu analisis dilakukan
    """
    sentiment: str
    score: float
    summary: str
    headline_count: int
    source: str
    timestamp: datetime


# ============================================================
# PAIR MAPPING — Indodax symbol → CryptoPanic/CryptoCompare symbol
# ============================================================

_PAIR_TO_CRYPTO_SYMBOL: Dict[str, str] = {
    "btcidr": "BTC",
    "ethidr": "ETH",
    "dogeidr": "DOGE",
    "shibidr": "SHIB",
    "pepeidr": "PEPE",
    "solidr": "SOL",
    "solvidr": "SOL",
    "xrpidr": "XRP",
    "bnbidr": "BNB",
    "adaidr": "ADA",
    "flokiidr": "FLOKI",
    "wifidr": "WIF",
    "fartcoinidr": "FARTCOIN",
    "metisidr": "METIS",
    "pippinidr": "PIPPIN",
    "drxidr": "DRX",
    "pixelidr": "PIXEL",
    "apexidr": "APEX",
    "vvvidr": "VVV",
    "maticidr": "MATIC",
    "wrxidr": "WRX",
}

# ============================================================
# KEYWORD LEXICON — untuk scoring tanpa LLM
# ============================================================

_BULLISH_KEYWORDS = [
    "bullish", "surge", "rally", "pump", "breakout", "all-time high", "ath",
    "moon", "soar", "gain", "jump", "spike", "uptrend", "upgrade", "buy",
    "adoption", "partnership", "approval", "etf approved", "institutional",
    "accumulate", "support", "recovery", "rebound", "positive", "optimistic",
    "growth", "profit", "milestone", "launch", "halving",
]

_BEARISH_KEYWORDS = [
    "bearish", "crash", "dump", "plunge", "sell-off", "selloff", "drop",
    "decline", "fall", "loss", "downtrend", "downgrade", "ban", "hack",
    "exploit", "vulnerability", "fraud", "scam", "sec lawsuit", "regulation",
    "crackdown", "fear", "panic", "liquidation", "bankruptcy", "collapse",
    "rug pull", "ponzi", "warning", "risk", "overbought", "correction",
]


# ============================================================
# CACHE
# ============================================================

_sentiment_cache: Dict[str, dict] = {}
"""In-memory cache: { "BTC": {"result": SentimentResult, "ts": timestamp} }"""

_CACHE_TTL_SECONDS = 900  # 15 menit — configurable via Config.SENTIMENT_CACHE_TTL


def _get_cache_ttl() -> int:
    """Return cache TTL from config, fallback to 900s (15 min)."""
    return getattr(Config, "SENTIMENT_CACHE_TTL", _CACHE_TTL_SECONDS)


def _get_cached(symbol: str) -> Optional[SentimentResult]:
    """Return cached result if still valid, else None."""
    entry = _sentiment_cache.get(symbol)
    if not entry:
        return None
    age = time.time() - entry.get("ts", 0)
    if age > _get_cache_ttl():
        return None
    return entry.get("result")


def _set_cache(symbol: str, result: SentimentResult):
    """Store result in cache."""
    _sentiment_cache[symbol] = {"result": result, "ts": time.time()}


# ============================================================
# PAIR → SYMBOL RESOLVER
# ============================================================

def pair_to_symbol(pair: str) -> Optional[str]:
    """Convert Indodax pair name (e.g. 'btcidr') to crypto symbol (e.g. 'BTC').

    Returns None if pair cannot be mapped.
    """
    pair_lower = str(pair or "").strip().lower()
    return _PAIR_TO_CRYPTO_SYMBOL.get(pair_lower)


# ============================================================
# KEYWORD SCORING
# ============================================================

def _score_headline(title: str, votes_bullish: int = 0, votes_bearish: int = 0) -> float:
    """Score a single headline from -1.0 to +1.0 using keyword matching + community votes."""
    title_lower = title.lower()
    bull_count = sum(1 for kw in _BULLISH_KEYWORDS if kw in title_lower)
    bear_count = sum(1 for kw in _BEARISH_KEYWORDS if kw in title_lower)

    # Keyword score: -1 to +1
    total_kw = bull_count + bear_count
    if total_kw > 0:
        kw_score = (bull_count - bear_count) / total_kw
    else:
        kw_score = 0.0

    # Community vote score: -1 to +1
    total_votes = votes_bullish + votes_bearish
    if total_votes > 0:
        vote_score = (votes_bullish - votes_bearish) / total_votes
    else:
        vote_score = 0.0

    # Weighted: 60% keyword, 40% community votes
    return 0.6 * kw_score + 0.4 * vote_score


def _aggregate_sentiment(headlines: list) -> SentimentResult:
    """Aggregate scored headlines into final SentimentResult.

    Args:
        headlines: list of dicts with 'title', 'bullish', 'bearish' keys

    Returns:
        SentimentResult with aggregated score and label
    """
    if not headlines:
        return SentimentResult(
            sentiment="NEUTRAL", score=0.0,
            summary="Tidak ada berita terbaru", headline_count=0,
            source="fallback", timestamp=datetime.now(),
        )

    scores = []
    for h in headlines:
        s = _score_headline(
            h.get("title", ""),
            h.get("bullish", 0),
            h.get("bearish", 0),
        )
        scores.append(s)

    avg_score = sum(scores) / len(scores)
    # Scale from (-1..+1) to (-10..+10)
    final_score = round(avg_score * 10, 1)
    final_score = max(-10.0, min(10.0, final_score))

    if final_score >= 2.0:
        label = "BULLISH"
    elif final_score <= -2.0:
        label = "BEARISH"
    else:
        label = "NEUTRAL"

    # Build summary
    bull_headlines = sum(1 for s in scores if s > 0.1)
    bear_headlines = sum(1 for s in scores if s < -0.1)
    neutral_headlines = len(scores) - bull_headlines - bear_headlines
    summary = f"{bull_headlines} bullish, {bear_headlines} bearish, {neutral_headlines} neutral dari {len(scores)} berita"

    return SentimentResult(
        sentiment=label,
        score=final_score,
        summary=summary,
        headline_count=len(headlines),
        source="cryptopanic",
        timestamp=datetime.now(),
    )


# ============================================================
# CRYPTOPANIC API FETCHER
# ============================================================

def _fetch_cryptopanic_headlines(symbol: str, max_items: int = 5) -> list:
    """Fetch recent news headlines from CryptoPanic API.

    Uses the free/public endpoint (no auth token required for basic access).
    Returns list of dicts: [{"title": str, "bullish": int, "bearish": int}]
    """
    try:
        url = (
            f"https://cryptopanic.com/api/free/v1/posts/"
            f"?auth_token=free&currencies={symbol}&kind=news&public=true"
        )
        response = requests.get(url, timeout=5)

        if response.status_code != 200:
            logger.debug(f"[SENTIMENT] CryptoPanic returned {response.status_code} for {symbol}")
            return []

        data = response.json()
        posts = data.get("results", [])[:max_items]

        headlines = []
        for post in posts:
            title = post.get("title", "")
            votes = post.get("votes", {})
            headlines.append({
                "title": title,
                "bullish": votes.get("positive", 0),
                "bearish": votes.get("negative", 0),
            })

        return headlines

    except requests.exceptions.Timeout:
        logger.debug(f"[SENTIMENT] CryptoPanic timeout for {symbol}")
        return []
    except requests.exceptions.ConnectionError:
        logger.debug(f"[SENTIMENT] CryptoPanic connection error for {symbol}")
        return []
    except Exception as e:
        logger.debug(f"[SENTIMENT] CryptoPanic fetch failed for {symbol}: {e}")
        return []


# ============================================================
# MAIN PUBLIC API
# ============================================================

_neutral_result = SentimentResult(
    sentiment="NEUTRAL", score=0.0,
    summary="Sentiment analysis tidak tersedia",
    headline_count=0, source="fallback",
    timestamp=datetime.now(),
)


def get_sentiment_for_pair(pair: str) -> SentimentResult:
    """Analyze news sentiment for a trading pair.

    This is the main entry point for the signal pipeline.

    Flow:
    1. Map pair → crypto symbol (e.g. btcidr → BTC)
    2. Check cache (TTL 15 menit)
    3. Fetch headlines from CryptoPanic API
    4. Score headlines using keyword analysis + community votes
    5. Aggregate into BULLISH/BEARISH/NEUTRAL with score (-10 to +10)
    6. Cache result and return

    Args:
        pair: Indodax pair name (e.g. "btcidr", "ethidr")

    Returns:
        SentimentResult — always returns a valid result (NEUTRAL on failure)

    Example:
        >>> result = get_sentiment_for_pair("btcidr")
        >>> result.sentiment
        'BULLISH'
        >>> result.score
        4.2
    """
    if not getattr(Config, "SENTIMENT_ENABLED", False):
        return _neutral_result

    symbol = pair_to_symbol(pair)
    if not symbol:
        logger.debug(f"[SENTIMENT] No symbol mapping for {pair}, returning NEUTRAL")
        return SentimentResult(
            sentiment="NEUTRAL", score=0.0,
            summary=f"Tidak ada mapping simbol untuk {pair}",
            headline_count=0, source="fallback",
            timestamp=datetime.now(),
        )

    # Check cache
    cached = _get_cached(symbol)
    if cached:
        logger.debug(f"[SENTIMENT] Cache hit for {symbol}: {cached.sentiment} ({cached.score:+.1f})")
        return cached

    # Fetch headlines
    max_items = getattr(Config, "SENTIMENT_MAX_HEADLINES", 5)
    headlines = _fetch_cryptopanic_headlines(symbol, max_items=max_items)

    if not headlines:
        logger.debug(f"[SENTIMENT] No headlines for {symbol}, returning NEUTRAL")
        result = SentimentResult(
            sentiment="NEUTRAL", score=0.0,
            summary=f"Tidak ada berita terbaru untuk {symbol}",
            headline_count=0, source="fallback",
            timestamp=datetime.now(),
        )
        _set_cache(symbol, result)
        return result

    # Analyze
    result = _aggregate_sentiment(headlines)
    result = SentimentResult(  # update source
        sentiment=result.sentiment,
        score=result.score,
        summary=result.summary,
        headline_count=result.headline_count,
        source="cryptopanic",
        timestamp=result.timestamp,
    )

    _set_cache(symbol, result)

    logger.info(
        f"📰 [SENTIMENT] {symbol}: {result.sentiment} ({result.score:+.1f}/10) "
        f"— {result.headline_count} headlines | {result.summary}"
    )

    return result


def clear_sentiment_cache():
    """Clear all cached sentiment data. Useful for testing or manual refresh."""
    global _sentiment_cache
    _sentiment_cache.clear()
    logger.info("[SENTIMENT] Cache cleared")
