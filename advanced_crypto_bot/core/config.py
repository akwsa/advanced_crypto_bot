# Tujuan: Central runtime configuration for Telegram bot, market access, risk, and profit optimization.
# Caller: bot orchestrator, autotrade modules, autohunter modules, workers, API adapters.
# Dependensi: environment variables via dotenv.
# Main Functions: Config class constants, get_pair_symbol.
# Side Effects: reads .env during module import.

import os
import logging
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()
logger = logging.getLogger("crypto_bot")

def _normalize_pair_symbol(pair):
    """Normalize pair aliases to Indodax lowercase/no-separator symbol."""
    normalized = str(pair or '').strip().lower().replace('/', '').replace('_', '').replace('-', '')
    aliases = {
        'solvidr': 'solidr',
        'soliddr': 'solidr',
    }
    return aliases.get(normalized, normalized)

def _parse_watch_pairs(value):
    pairs = []
    seen = set()
    for raw_pair in str(value or '').split(','):
        pair = _normalize_pair_symbol(raw_pair)
        if pair and pair not in seen:
            pairs.append(pair)
            seen.add(pair)
    return pairs


def _safe_float_env(key, default):
    """Parse float env var with safe fallback."""
    raw = os.getenv(key)
    if raw is None or str(raw).strip() == "":
        return float(default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        logger.warning(f"Invalid float for {key}={raw!r}; using default {default}")
        return float(default)


def _safe_int_env(key, default):
    """Parse int env var with safe fallback."""
    raw = os.getenv(key)
    if raw is None or str(raw).strip() == "":
        return int(default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning(f"Invalid int for {key}={raw!r}; using default {default}")
        return int(default)


def _parse_id_list(value, env_name):
    ids = []
    for item in str(value or "").split(","):
        raw = item.strip()
        if not raw:
            continue
        try:
            ids.append(int(raw))
        except ValueError:
            logger.warning(f"Invalid {env_name} entry={raw!r}; skipping")
    return ids


def _parse_admin_ids(value):
    return _parse_id_list(value, "ADMIN_IDS")

class Config:
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    ADMIN_IDS = _parse_admin_ids(os.getenv('ADMIN_IDS', ''))
    ALLOWED_USER_IDS = _parse_id_list(os.getenv('ALLOWED_USER_IDS', ''), "ALLOWED_USER_IDS")
    TELEGRAM_INVITE_CODE = os.getenv('TELEGRAM_INVITE_CODE', '').strip()
    TELEGRAM_COMMAND_RATE_LIMIT_SECONDS = _safe_float_env('TELEGRAM_COMMAND_RATE_LIMIT_SECONDS', 2.0)

    # Indodax API (OPSIONAL)
    # Tidak perlu diisi jika bot hanya untuk baca market data
    INDODAX_API_KEY = os.getenv('INDODAX_API_KEY')  # Optional
    INDODAX_SECRET_KEY = os.getenv('INDODAX_SECRET_KEY')  # Optional
    INDODAX_WS_URL = "wss://ws3.indodax.com/ws/"  # Updated WebSocket URL
    INDODAX_REST_URL = "https://indodax.com"  # Base URL for REST API
    
    # Auto-Trading Control
    AUTO_TRADING_ENABLED = os.getenv('AUTO_TRADING_ENABLED', 'false').lower() == 'true'
    AUTO_TRADE_DRY_RUN = os.getenv('AUTO_TRADE_DRY_RUN', 'true').lower() == 'true'  # True = simulation mode
    AUTOTRADE_LIQUIDITY_WHITELIST = _parse_watch_pairs(os.getenv('AUTOTRADE_LIQUIDITY_WHITELIST', ''))
    AUTOTRADE_LIQUIDITY_BLACKLIST_TTL_MINUTES = _safe_int_env('AUTOTRADE_LIQUIDITY_BLACKLIST_TTL_MINUTES', 180)
    AUTOTRADE_LIQUIDITY_PROMOTE_MAX_SPREAD_PCT = _safe_float_env('AUTOTRADE_LIQUIDITY_PROMOTE_MAX_SPREAD_PCT', 0.03)
    AUTOTRADE_LIQUIDITY_PROMOTE_REQUIRE_BIDASK = os.getenv('AUTOTRADE_LIQUIDITY_PROMOTE_REQUIRE_BIDASK', 'true').lower() == 'true'
    
    # DRY RUN Exploration Mode: allow PANTAU signals with high confluence to enter
    # with reduced position size (data collection for tuning)
    DRYRUN_EXPLORATION_ENABLED = os.getenv('DRYRUN_EXPLORATION_ENABLED', 'true').lower() == 'true'
    DRYRUN_EXPLORATION_POSITION_FACTOR = _safe_float_env('DRYRUN_EXPLORATION_POSITION_FACTOR', 0.20)
    # Exploration thresholds (relaxed to generate more sample trades for evaluation)
    DRYRUN_EXPLORATION_MIN_CONFIDENCE = _safe_float_env('DRYRUN_EXPLORATION_MIN_CONFIDENCE', 0.40)  # 2026-06-29: 0.60→0.40
    DRYRUN_EXPLORATION_MIN_STRENGTH = _safe_float_env('DRYRUN_EXPLORATION_MIN_STRENGTH', 0.05)
    DRYRUN_EXPLORATION_MIN_RR = _safe_float_env('DRYRUN_EXPLORATION_MIN_RR', 1.2)
    
    # Manual Trading
    MANUAL_TRADING_ENABLED = os.getenv('MANUAL_TRADING_ENABLED', 'false').lower() == 'true'
    CANCEL_TRADE_ENABLED = os.getenv('CANCEL_TRADE_ENABLED', 'false').lower() == 'true'
    
    # Cek apakah API key dikonfigurasi
    IS_API_KEY_CONFIGURED = bool(INDODAX_API_KEY and INDODAX_SECRET_KEY)
    
    # Trading Pairs - normalized lowercase/no separator (e.g. pippinidr, btcidr)
    WATCH_PAIRS = _parse_watch_pairs(os.getenv(
        'WATCH_PAIRS',
        'btcidr,ethidr,dogeidr,pepeidr,shibidr,solidr,xrpidr,bnbidr,adaidr,flokiidr,wifidr,fartcoinidr,metisidr,pippinidr,drxidr,pixelidr,apexidr,vvvidr'
    ))
    
    # Trading Settings
    INITIAL_BALANCE = _safe_float_env('INITIAL_BALANCE', 10000000)  # 10 juta IDR
    MAX_POSITION_SIZE = 0.20  # Max 20% per trade (was 25%)
    
    # Stop Loss & Take Profit (dari .env)
    STOP_LOSS_PCT = _safe_float_env('STOP_LOSS_PCT', 2.5)      # Cut Loss %
    TAKE_PROFIT_PCT = _safe_float_env('TAKE_PROFIT_PCT', 6.0)  # Take Profit % (was 5%)
    
    # Trailing Stop - MORE AGGRESSIVE
    TRAILING_STOP_ENABLED = True
    TRAILING_STOP_PCT = 1.8  # Trail by 1.8% (17-Jun tuning)
    TRAILING_ACTIVATION_PCT = 2.5  # Activate after +2.5% profit (17-Jun tuning)
    
    # Risk Management - ADDITIONAL
    BREAK_EVEN_AFTER_PCT = 2.0  # Move stop to breakeven after +2% profit
    PARTIAL_TAKE_PROFIT_1 = 3.0  # Take 50% profit at +2%
    PARTIAL_TAKE_PROFIT_2 = 8.0  # Take remaining 50% profit at +5%
    MAX_DAILY_LOSS_PCT = 3.0  # Stop trading if loss >3% (was 5%)
    MAX_DRAWDOWN_PCT = 0.10  # Circuit breaker drawdown ratio (0.10 = 10%)
    
    # NEW: Market Regime-Based Position Sizing
    REGIME_TRENDING_UP = 1    # Full position allowed
    REGIME_TRENDING_DOWN = 1  # Full position allowed
    REGIME_RANGING = 0.5       # Half position in ranging market
    REGIME_VOLATILE = 0.5     # Reduced position in volatile market (was 0.0 = no trading)
    
    # Regime Detection
    REGIME_VOLATILITY_THRESHOLD = 0.02  # High vol if std > 2%
    REGIME_TREND_THRESHOLD = 0.01  # Trend if change > 1%
    
    # Market Intelligence Entry Filter
    MI_VOLUME_SPIKE_MIN = 1.1  # Min volume ratio to pass filter (2026-06-09: relaxed 1.3→1.1; 26/48 scan di VM (54%) di-block MI=NEUTRAL meskipun signal STRONG_BUY. Threshold 1.3x terlalu tinggi untuk pair low-cap Indodax — volume spike 30% jarang terjadi tanpa news event. 1.1x masih filter pair yang volumenya turun dari rata-rata, tetap proteksi tapi tidak block entry yang valid).
    MI_ORDERBOOK_BULLISH_MIN = 1.05  # Min bid/ask ratio to pass filter (2026-06-09: relaxed 1.2→1.05; pair sideways konsolidasi normal ratio 0.95-1.10. Threshold 1.2 minta bid pressure 20% lebih kuat dari ask — terlalu strict untuk pair low-cap. 1.05 = bid pressure 5% cukup untuk MODERATE, masih filter pair benar-benar bearish/sideways heavy).
    MI_SPREAD_MAX_PCT = 0.02  # Max spread % before entry is blocked (2% default)
    MI_REQUIRE_BULLISH_FOR_ENTRY = False  # If True, only enter when MI is BULLISH
    MI_ALLOW_MODERATE_ENTRY = True  # If True, also allow MODERATE MI signal
    MI_ALLOW_NEUTRAL_ENTRY = False  # Block NEUTRAL MI (17-Jun tuning)
    
    # Portfolio Allocation Dinamis
    PORTFOLIO_MAX_EXPOSURE_PCT = 0.75  # Max 75% of balance in open positions
    PORTFOLIO_MAX_PER_PAIR_PCT = 0.30  # Max 30% per single pair
    PORTFOLIO_RISK_ADJUSTED = True  # Use risk-adjusted allocation
    
    # Reinforcement Learning (Q-Learning)
    RL_ENABLED = True
    RL_LEARNING_RATE = 0.1
    RL_DISCOUNT_FACTOR = 0.9
    RL_EPSILON = 0.15  # Exploration rate
    RL_UPDATE_REWARD = True  # Update Q-table after each trade
    
    # Spoofing Detection
    SPOOFING_ENABLED = True
    SPOOFING_MIN_PERSISTENCE = 3  # Min snapshots to consider real
    SPOOFING_LARGE_ORDER_THRESHOLD = 5.0  # Volume multiplier for large orders
    
    # Smart Order Routing
    SMART_ROUTING_ENABLED = True
    SMART_ROUTING_CHUNKS = 3  # Split order into N chunks
    SMART_ROUTING_PRICE_IMPROVEMENT = 0.001  # 0.1% better price attempt
    SMART_ROUTING_DELAY = 1  # Seconds between chunks
    
    # Heatmap Liquidity
    HEATMAP_ENABLED = True
    HEATMAP_MAX_SNAPSHOTS = 50  # Keep last N snapshots
    HEATMAP_PRICE_ROUNDING = 1000  # Round to nearest N for grouping
    HEATMAP_TOP_ZONES = 5  # Return top N liquidity zones
    
    # Fee-aware P&L Calculation
    TRADING_FEE_RATE = 0.003  # Indodax fee: 0.3%
    SLIPPAGE_MAX_PCT = 0.005  # Max 0.5% slippage allowed
    DRYRUN_SLIPPAGE_PCT = _safe_float_env('DRYRUN_SLIPPAGE_PCT', 0.001)
    SLIPPAGE_CANCEL_ENABLED = True  # Cancel order if slippage > threshold
    ELITE_SIGNAL_PROB_THRESHOLD = 0.6  # Elite signal: prob > 0.6 = BUY
    ELITE_SIGNAL_IMBALANCE_DISTANCE = 0.002  # Zone proximity threshold (0.2%)
    
    # Trade Amount Limits
    MIN_TRADE_AMOUNT = _safe_float_env('MIN_TRADE_AMOUNT', 100000)    # 100k IDR
    MAX_TRADE_AMOUNT = _safe_float_env('MAX_TRADE_AMOUNT', 5000000)   # 5 juta IDR
    
    MAX_DAILY_TRADES = 10
    
    # ML Settings
    ML_MODEL_PATH = os.getenv('ML_MODEL_PATH', 'models/trading_model.pkl')
    ML_SEQUENCE_LENGTH = 60  # 60 candles
    ML_RETRAIN_INTERVAL = timedelta(hours=24)
    CONFIDENCE_THRESHOLD = 0.50  # Global fallback; per-direction thresholds in signal_rules.py take priority
    
    # Risk Management
    # (MAX_DAILY_LOSS_PCT and MAX_DRAWDOWN_PCT defined earlier — kept as fractions for consistency)
    RISK_REWARD_RATIO = 2.0  # Minimal RR ratio for autotrade execution
    
    # S/R Validation Thresholds (unified across signal pipeline and autotrade)
    SR_MIN_RR_RATIO = 1.2  # Minimum risk/reward ratio for signal validation (Prioritas 1 2026-05-22: relaxed 1.5→1.2 supaya RR moderate setup tidak di-downgrade ke HOLD)
    SR_MIN_SL_PCT = 0.08  # Minimum stop loss distance (%) — relaxed to allow more signals
    SR_NEAR_SUPPORT_PCT = 2.5  # Reject BUY if price within N% of support
    SR_NEAR_RESISTANCE_PCT = 1.0  # Reject SELL if price within N% of resistance (2026-06-09: relaxed 2.5→1.0; 851/1103 BUY (77%) di-downgrade jadi HOLD oleh threshold lama untuk pair low-cap di mana 0.5%-2% di bawah R1 sudah dianggap "at resistance". Autotrade bypass via pre_sr_recommendation, threshold ini sekarang murni untuk filter notif Telegram.)
    ENABLE_SR_VALIDATION = True  # Enable/disable S/R validation gate

    # ML / Signal Pipeline — Historical Data Lookback
    # Berapa banyak tick (row price_history) yang di-load per pair untuk feed ML+TA.
    # Konteks: data di `price_history` adalah TICK polling Indodax dengan cadence
    # AKTUAL ~64 detik per tick (bukan 3-5 menit seperti asumsi awal). Diukur live
    # 2026-06-13 di VM: 500 tick → cuma 8.9 jam coverage → max 9 candle 1h →
    # SMA slow=10 (butuh 11+ candle) STUCK di INSUFFICIENT_DATA selamanya.
    # Naik dari 500 → 800 supaya 800 × 64s ≈ 14.2 jam → ~14 candle 1h, headroom
    # 3 candle di atas minimum SMA slow=10. Memory cost per pair ~38KB
    # (800 × 6 cols × 8 bytes). 50 pair tracked = ~1.9MB total — masih murah.
    HISTORICAL_DATA_LIMIT = _safe_int_env('HISTORICAL_DATA_LIMIT', 800)

    # Entry Quality
    AUTOTRADE_CHASE_THRESHOLD_PCT = 1.5  # Skip BUY if price moved >1.5% from signal price
    # FIX 2026-06-06: Entry zone distance relaxed from 0.5%→0.2% for more instant fills in trending markets
    ENTRY_ZONE_DISTANCE_PCT = _safe_float_env('ENTRY_ZONE_DISTANCE_PCT', 0.002)  # Default 0.2% below market (was 0.5%)
    LIMIT_ORDER_TIMEOUT_MINUTES = _safe_float_env('LIMIT_ORDER_TIMEOUT_MINUTES', 15.0)  # Cancel unfilled limit orders after N minutes (raised from 5→15 for DRY RUN realism)
    LIMIT_ORDER_MIN_EDGE_PCT = _safe_float_env('LIMIT_ORDER_MIN_EDGE_PCT', 0.10)  # Min discount vs market for maker BUY (relaxed 0.15→0.10 for more fills)
    LIMIT_ORDER_CANCEL_DISTANCE_PCT = _safe_float_env('LIMIT_ORDER_CANCEL_DISTANCE_PCT', 1.50)  # Cancel stale BUY if market runs too far above limit (relaxed 1.25→1.50)
    PARTIAL_TP_MOVE_SL_TO_BREAKEVEN = os.getenv('PARTIAL_TP_MOVE_SL_TO_BREAKEVEN', 'true').lower() == 'true'

    # Time-Based Exit
    HUNTER_MAX_HOLD_HOURS = 4.0  # Max hold duration for hunter positions (hours)

    # Dynamic Trailing Stop
    HUNTER_DYNAMIC_TRAILING_VOLATILITY_LOW = 5.0   # Below this = low vol (tighter trail)
    HUNTER_DYNAMIC_TRAILING_VOLATILITY_HIGH = 10.0 # Above this = high vol (wider trail)
    HUNTER_DYNAMIC_TRAILING_PCT_LOW_VOL = 1.0
    HUNTER_DYNAMIC_TRAILING_PCT_NORMAL = 1.5
    HUNTER_DYNAMIC_TRAILING_PCT_HIGH_VOL = 2.5

    # Portfolio Heat / Correlation
    PORTFOLIO_MAX_CORRELATED_EXPOSURE_PCT = 0.40  # Max 40% balance in correlated group

    # Profit Optimization
    PROFIT_AUTOTRADE_MIN_EDGE_SCORE = _safe_float_env('PROFIT_AUTOTRADE_MIN_EDGE_SCORE', 56)
    # Dry-run R/R floor (relaxed dari LIVE supaya observasi/kalibrasi tidak no-entry).
    # LIVE tetap pakai max(RISK_REWARD_RATIO*0.75, 1.35) = 1.50 di profit_optimizer.
    # 2026-06-10: ditambah supaya saharaidr-class setup (R/R ~1.2) bisa lolos di dry-run
    # tanpa melonggarkan floor real-trading.
    PROFIT_AUTOTRADE_DRYRUN_MIN_RR = _safe_float_env('PROFIT_AUTOTRADE_DRYRUN_MIN_RR', 1.20)
    PROFIT_AUTOTRADE_MAX_POSITION_BOOST = _safe_float_env('PROFIT_AUTOTRADE_MAX_POSITION_BOOST', 1.35)
    PROFIT_TP2_EXPANSION_MAX = _safe_float_env('PROFIT_TP2_EXPANSION_MAX', 0.35)
    PROFIT_HUNTER_MIN_EDGE_SCORE = _safe_float_env('PROFIT_HUNTER_MIN_EDGE_SCORE', 58)
    PROFIT_HUNTER_MIN_RR = _safe_float_env('PROFIT_HUNTER_MIN_RR', 2.2)
    PROFIT_HUNTER_MAX_POSITION_BOOST = _safe_float_env('PROFIT_HUNTER_MAX_POSITION_BOOST', 1.30)
    
    # Technical Analysis
    RSI_PERIOD = 14
    RSI_OVERBOUGHT = 70
    RSI_OVERSOLD = 30
    SMA_PERIODS = [9, 20, 50, 200]
    EMA_PERIODS = [9, 20, 50]
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9
    BB_PERIOD = 20
    BB_STD = 2
    ATR_PERIOD = 14
    
    # Trading Hours (default WIB / UTC+7)
    # Low liquidity: 00:00-06:00 WIB (17:00-23:00 UTC)
    # High liquidity: 08:00-22:00 WIB
    TRADING_HOURS_ENABLED = True
    TRADING_TIMEZONE_OFFSET = _safe_int_env('TRADING_TIMEZONE_OFFSET', 7)
    TRADING_TIMEZONE_LABEL = os.getenv('TRADING_TIMEZONE_LABEL', 'WIB')
    TRADING_HOURS_START = 8   # Start allowing trades at 8 AM local trading timezone
    TRADING_HOURS_END = 22  # Stop allowing trades at 10 PM local trading timezone
    
    # WebSocket
    WS_RECONNECT_DELAY = 5
    WS_HEARTBEAT = 30

    # Webhook Configuration (alternative to polling)
    WEBHOOK_ENABLED = os.getenv('WEBHOOK_ENABLED', 'false').lower() == 'true'
    WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')  # e.g. https://yourdomain.com/webhook
    WEBHOOK_LISTEN = os.getenv('WEBHOOK_LISTEN', '0.0.0.0')
    WEBHOOK_PORT = _safe_int_env('WEBHOOK_PORT', 8443)
    WEBHOOK_PATH = os.getenv('WEBHOOK_PATH', '/webhook')
    WEBHOOK_SECRET_TOKEN = os.getenv('WEBHOOK_SECRET_TOKEN', '')  # Optional secret for webhook validation

    # Dashboard URL (public URL for /dashboard command)
    DASHBOARD_URL = os.getenv('DASHBOARD_URL', '')  # e.g. https://yourdomain.com or http://your-vps-ip:8080
    
    # Database
    DATABASE_PATH = os.getenv('DATABASE_PATH', 'data/trading.db')
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = 'logs/trading_bot.log'
    
    # Performance
    UPDATE_INTERVAL = 5  # seconds
    PRICE_ALERT_THRESHOLD = 1.0  # 1% change
    
    # Pair Correlation - Avoid trading correlated pairs simultaneously
    # BTC is highly correlated with alts
    CORRELATION_AVOIDANCE_ENABLED = True
    CORRELATION_COOLDOWN_MINUTES = 30  # Wait N minutes after trade in correlated pair
    
    # Known correlation groups (pairs that move together)
    CORRELATION_GROUPS = {
        'BTC': ['btcidr', 'wrxidr'],
        'ETH': ['ethidr', 'maticidr', 'solidr'],
        'ALT': ['dogeidr', 'xrpidr', 'adaidr', 'shibidr'],
    }

    # ================================================================
    # Sentiment Analysis (NEW 2026-06-06 — adapted from Meridian-main)
    # ================================================================
    # Fetches crypto news from CryptoPanic API and scores sentiment.
    # Integrated into signal_pipeline.py as additional confidence factor.
    # Concept source: Meridian-main/agent.py get_crypto_sentiment()
    # ================================================================
    SENTIMENT_ENABLED = os.getenv('SENTIMENT_ENABLED', 'true').lower() == 'true'
    SENTIMENT_CACHE_TTL = _safe_int_env('SENTIMENT_CACHE_TTL', 900)  # Cache per pair: 15 menit
    SENTIMENT_MAX_HEADLINES = _safe_int_env('SENTIMENT_MAX_HEADLINES', 5)  # Max berita per fetch
    SENTIMENT_CONFIDENCE_BOOST = _safe_float_env('SENTIMENT_CONFIDENCE_BOOST', 0.05)  # Boost confidence jika sentimen searah sinyal
    SENTIMENT_CONFIDENCE_PENALTY = _safe_float_env('SENTIMENT_CONFIDENCE_PENALTY', 0.03)  # Penalty jika sentimen berlawanan
    
    @staticmethod
    def get_pair_symbol(pair):
        """Convert BTC/IDR, BTC_IDR, or known aliases to normalized btcidr format."""
        return _normalize_pair_symbol(pair)
