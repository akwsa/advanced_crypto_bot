import os
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()

class Config:
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]

    # Indodax API (OPSIONAL)
    # Tidak perlu diisi jika bot hanya untuk baca market data
    INDODAX_API_KEY = os.getenv('INDODAX_API_KEY')  # Optional
    INDODAX_SECRET_KEY = os.getenv('INDODAX_SECRET_KEY')  # Optional
    INDODAX_WS_URL = "wss://ws3.indodax.com/ws/"  # Updated WebSocket URL
    INDODAX_REST_URL = "https://indodax.com"  # Base URL for REST API
    
    # Auto-Trading Control
    AUTO_TRADING_ENABLED = os.getenv('AUTO_TRADING_ENABLED', 'false').lower() == 'true'
    AUTO_TRADE_DRY_RUN = os.getenv('AUTO_TRADE_DRY_RUN', 'true').lower() == 'true'  # True = simulation mode
    
    # Manual Trading
    MANUAL_TRADING_ENABLED = os.getenv('MANUAL_TRADING_ENABLED', 'false').lower() == 'true'
    CANCEL_TRADE_ENABLED = os.getenv('CANCEL_TRADE_ENABLED', 'false').lower() == 'true'
    
    # Cek apakah API key dikonfigurasi
    IS_API_KEY_CONFIGURED = bool(INDODAX_API_KEY and INDODAX_SECRET_KEY)
    
    # Trading Pairs - LOWERCASE NO SLASH (e.g. pippinidr, btcidr)
    WATCH_PAIRS = os.getenv('WATCH_PAIRS', 'btcidr,ethidr,bridr,pippinidr,solidr,dogeidr,xrpidr,adaidr').split(',')
    
    # Trading Settings
    INITIAL_BALANCE = float(os.getenv('INITIAL_BALANCE', 10000000))  # 10 juta IDR
    MAX_POSITION_SIZE = 0.20  # Max 20% per trade (was 25%)
    
    # Stop Loss & Take Profit (dari .env)
    STOP_LOSS_PCT = float(os.getenv('STOP_LOSS_PCT', 2.0))      # Cut Loss %
    TAKE_PROFIT_PCT = float(os.getenv('TAKE_PROFIT_PCT', 4.0))  # Take Profit % (was 5%)
    
    # Trailing Stop - MORE AGGRESSIVE
    TRAILING_STOP_ENABLED = True
    TRAILING_STOP_PCT = 1.0  # Trail by 1% (tighter, was 1.5%)
    TRAILING_ACTIVATION_PCT = 1.0  # Activate after +1% profit (was 2%)
    
    # Risk Management - ADDITIONAL
    BREAK_EVEN_AFTER_PCT = 2.0  # Move stop to breakeven after +2% profit
    PARTIAL_TAKE_PROFIT_1 = 2.0  # Take 50% profit at +2%
    PARTIAL_TAKE_PROFIT_2 = 5.0  # Take remaining 50% profit at +5%
    MAX_DAILY_LOSS_PCT = 3.0  # Stop trading if loss >3% (was 5%)
    
    # NEW: Market Regime-Based Position Sizing
    REGIME_TRENDING_UP = 1    # Full position allowed
    REGIME_TRENDING_DOWN = 1  # Full position allowed
    REGIME_RANGING = 0.5       # Half position in ranging market
    REGIME_VOLATILE = 0.0     # No trading in volatile market
    
    # Regime Detection
    REGIME_VOLATILITY_THRESHOLD = 0.02  # High vol if std > 2%
    REGIME_TREND_THRESHOLD = 0.01  # Trend if change > 1%
    
    # Market Intelligence Entry Filter
    MI_VOLUME_SPIKE_MIN = 1.3  # Min volume ratio to pass filter
    MI_ORDERBOOK_BULLISH_MIN = 1.2  # Min bid/ask ratio to pass filter
    MI_REQUIRE_BULLISH_FOR_ENTRY = False  # If True, only enter when MI is BULLISH
    MI_ALLOW_MODERATE_ENTRY = True  # If True, also allow MODERATE MI signal
    
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
    SLIPPAGE_CANCEL_ENABLED = True  # Cancel order if slippage > threshold
    ELITE_SIGNAL_PROB_THRESHOLD = 0.6  # Elite signal: prob > 0.6 = BUY
    ELITE_SIGNAL_IMBALANCE_DISTANCE = 0.002  # Zone proximity threshold (0.2%)
    
    # Trade Amount Limits
    MIN_TRADE_AMOUNT = float(os.getenv('MIN_TRADE_AMOUNT', 100000))    # 100k IDR
    MAX_TRADE_AMOUNT = float(os.getenv('MAX_TRADE_AMOUNT', 5000000))   # 5 juta IDR
    
    MAX_DAILY_TRADES = 10
    
    # ML Settings
    ML_MODEL_PATH = os.getenv('ML_MODEL_PATH', 'models/trading_model.pkl')
    ML_SEQUENCE_LENGTH = 60  # 60 candles
    ML_RETRAIN_INTERVAL = timedelta(hours=24)
    CONFIDENCE_THRESHOLD = 0.35  # Lower for more signals
    
    # Risk Management
    MAX_DAILY_LOSS_PCT = 5.0  # Stop trading jika loss >5% sehari
    MAX_DRAWDOWN_PCT = 10.0  # Max drawdown
    RISK_REWARD_RATIO = 2.0  # Minimal RR ratio
    
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
    
    # Trading Hours (WIB timezone - UTC+7)
    # Low liquidity: 00:00-06:00 WIB (17:00-23:00 UTC)
    # High liquidity: 08:00-22:00 WIB
    TRADING_HOURS_ENABLED = True
    TRADING_HOURS_START = 8   # Start allowing trades at 8 AM WIB
    TRADING_HOURS_END = 22  # Stop allowing trades at 10 PM WIB
    
    # WebSocket
    WS_RECONNECT_DELAY = 5
    WS_HEARTBEAT = 30
    
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
        'ETH': ['ethidr', 'maticidr', 'soliddr'],
        'ALT': ['dogeidr', 'xrpidr', 'adaidr', 'shibidr'],
    }
    
    @staticmethod
    def get_pair_symbol(pair):
        """Convert BTC/IDR to btcidr"""
        return pair.replace('/', '').lower()