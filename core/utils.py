import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from core.config import Config
import logging

logger = logging.getLogger(__name__)

class Utils:
    @staticmethod
    def format_price(price, decimals=None):
        """
        Format price with appropriate decimals
        Auto-detect decimals based on price magnitude:
        - price >= 1000: 0 decimals (e.g., 1,209,385,000)
        - price >= 1: 2 decimals (e.g., 4,254.50)
        - price >= 0.01: 4 decimals (e.g., 0.0034)
        - price < 0.01: 8 decimals (e.g., 0.00000123 for PEPE, SHIB)
        """
        if price is None:
            return "0"
        
        # Auto-detect decimals if not specified
        if decimals is None:
            abs_price = abs(price)
            if abs_price >= 1000:
                decimals = 0      # High price: 1,200,000
            elif abs_price >= 10:
                decimals = 4      # Mid-High price: 45.5000
            elif abs_price >= 1:
                decimals = 4      # Mid price: 9.2100
            elif abs_price >= 0.01:
                decimals = 6      # Low price: 0.550000
            else:
                decimals = 6      # Micro price (PEPE/SHIB): 0.000012
        
        return f"{price:,.{decimals}f}"
    
    @staticmethod
    def format_percentage(value, decimals=2):
        """Format percentage with sign"""
        if value is None:
            return "0.00%"
        sign = "+" if value > 0 else ""
        return f"{sign}{value:.{decimals}f}%"
    
    @staticmethod
    def format_currency(amount, currency='IDR'):
        """Format currency"""
        if amount is None:
            return f"0 {currency}"
        return f"{amount:,.0f} {currency}"
    
    @staticmethod
    def parse_pair(pair):
        """Parse pair string to symbol"""
        return pair.replace('/', '').lower()
    
    @staticmethod
    def unparse_pair(symbol):
        """Parse symbol back to pair string"""
        if 'idr' in symbol.lower():
            base = symbol.lower().replace('idr', '')
            return f"{base.upper()}/IDR"
        return symbol.upper()
    
    @staticmethod
    def calculate_position_size(balance, price, risk_percentage=0.25):
        """Calculate optimal position size"""
        max_position = balance * risk_percentage
        amount = max_position / price if price > 0 else 0
        return amount, max_position
    
    @staticmethod
    def calculate_stop_loss_take_profit(entry_price, trade_type, stop_loss_pct=2.0, take_profit_pct=5.0):
        """Calculate SL and TP levels"""
        if trade_type.upper() == 'BUY':
            stop_loss = entry_price * (1 - stop_loss_pct / 100)
            take_profit = entry_price * (1 + take_profit_pct / 100)
        else:  # SELL
            stop_loss = entry_price * (1 + stop_loss_pct / 100)
            take_profit = entry_price * (1 - take_profit_pct / 100)
        
        return stop_loss, take_profit
    
    @staticmethod
    def calculate_pnl(entry_price, exit_price, amount, trade_type):
        """Calculate profit/loss"""
        if trade_type.upper() == 'BUY':
            pnl = (exit_price - entry_price) * amount
        else:  # SELL
            pnl = (entry_price - exit_price) * amount
        
        pnl_pct = (pnl / (entry_price * amount)) * 100 if entry_price > 0 else 0
        
        return pnl, pnl_pct
    
    @staticmethod
    def time_diff_formatted(time1, time2=None):
        """Calculate time difference"""
        if time2 is None:
            time2 = datetime.now()
        
        if isinstance(time1, str):
            time1 = datetime.fromisoformat(time1)
        if isinstance(time2, str):
            time2 = datetime.fromisoformat(time2)
        
        diff = time2 - time1
        
        days = diff.days
        hours = diff.seconds // 3600
        minutes = (diff.seconds % 3600) // 60
        seconds = diff.seconds % 60
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    @staticmethod
    def is_market_open():
        """Check if market is open (Indodax is 24/7)"""
        return True
    
    @staticmethod
    def get_trading_hours():
        """Get trading hours"""
        return "24/7"
    
    @staticmethod
    def save_to_json(data, filepath):
        """Save data to JSON file"""
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=4, default=str)
            logger.info(f"💾 Data saved to {filepath}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to save JSON: {e}")
            return False
    
    @staticmethod
    def load_from_json(filepath):
        """Load data from JSON file"""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            logger.info(f"📂 Data loaded from {filepath}")
            return data
        except Exception as e:
            logger.error(f"❌ Failed to load JSON: {e}")
            return None
    
    @staticmethod
    def export_to_csv(df, filepath):
        """Export DataFrame to CSV"""
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            df.to_csv(filepath, index=False)
            logger.info(f"📊 Data exported to {filepath}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to export CSV: {e}")
            return False
    
    @staticmethod
    def import_from_csv(filepath):
        """Import DataFrame from CSV"""
        try:
            df = pd.read_csv(filepath)
            logger.info(f"📂 Data imported from {filepath}")
            return df
        except Exception as e:
            logger.error(f"❌ Failed to import CSV: {e}")
            return None
    
    @staticmethod
    def normalize_price(price):
        """Normalize price to proper decimals"""
        if price >= 1000000:
            return round(price, 0)
        elif price >= 1000:
            return round(price, 2)
        else:
            return round(price, 6)
    
    @staticmethod
    def round_to_tick(price, tick_size=1):
        """Round price to tick size"""
        return round(price / tick_size) * tick_size
    
    @staticmethod
    def get_timestamp():
        """Get current timestamp"""
        return datetime.now().strftime('%Y%m%d_%H%M%S')
    
    @staticmethod
    def date_range(start_date, end_date, freq='D'):
        """Generate date range"""
        return pd.date_range(start=start_date, end=end_date, freq=freq)
    
    @staticmethod
    def chunk_list(lst, chunk_size):
        """Split list into chunks"""
        return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]
    
    @staticmethod
    def safe_divide(a, b, default=0):
        """Safe division"""
        try:
            return a / b if b != 0 else default
        except Exception:
            return default
    
    @staticmethod
    def format_confidence_emoji(confidence):
        """Get emoji based on confidence level.
        
        Args:
            confidence: Float 0.0 to 1.0
            
        Returns:
            str: Emoji representation
        """
        if confidence >= 0.75:
            return "🔵"  # Very high
        elif confidence >= 0.55:
            return "🟢"  # High
        elif confidence >= 0.45:
            return "🟡"  # Medium
        elif confidence >= 0.25:
            return "🟠"  # Low
        else:
            return "🔴"  # Very low
    
    @staticmethod
    def format_confidence_text(confidence):
        """Get text description of confidence level.
        
        Args:
            confidence: Float 0.0 to 1.0
            
        Returns:
            str: Text description
        """
        if confidence >= 0.75:
            return "SANGAT_TINGGI"
        elif confidence >= 0.55:
            return "TINGGI"
        elif confidence >= 0.45:
            return "SEDANG"
        elif confidence >= 0.25:
            return "RENDAH"
        else:
            return "SANGAT_RENDAH"
    
    @staticmethod
    def format_signal_badge(recommendation, confidence):
        """Format signal as badge.
        
        Args:
            recommendation: 'BUY', 'SELL', 'HOLD', etc.
            confidence: Float 0.0 to 1.0
            
        Returns:
            str: Formatted badge
        """
        emoji = Utils.format_confidence_emoji(confidence)
        level = Utils.format_confidence_text(confidence)
        
        if recommendation in ['BUY', 'STRONG_BUY']:
            return f"🟢 {recommendation} {emoji}"
        elif recommendation in ['SELL', 'STRONG_SELL']:
            return f"🔴 {recommendation} {emoji}"
        else:
            return f"⚪ {recommendation} {emoji}"
    
    @staticmethod
    def clean_price_data(df):
        """Clean and validate price data, removing invalid entries.
        
        Args:
            df: DataFrame with 'open', 'high', 'low', 'close', 'volume'
            
        Returns:
            DataFrame: Cleaned data
        """
        if df is None or df.empty:
            return df
        
        original_len = len(df)
        
        df = df.copy()
        
        df = df.dropna(subset=['close'])
        
        df = df[df['close'] > 0]
        df = df[df['volume'] > 0]
        
        df = df[(df['high'] >= df['low'])]
        df = df[(df['high'] >= df['close'])]
        df = df[(df['close'] >= df['low'])]
        
        df = df.replace([np.inf, -np.inf], np.nan)
        df = df.dropna()
        
        logger.debug(f"Cleaned price data: {original_len} -> {len(df)} rows")
        
        return df
    
    @staticmethod
    def detect_outliers(series, z_threshold=3.0):
        """Detect outliers using z-score method.
        
        Args:
            series: pandas Series of values
            z_threshold: Z-score threshold (default 3.0)
            
        Returns:
            list: Index positions of outliers
        """
        if len(series) < 10:
            return []
        
        mean = series.mean()
        std = series.std()
        
        if std == 0:
            return []
        
        z_scores = np.abs((series - mean) / std)
        
        outliers = z_scores[z_scores > z_threshold].index.tolist()
        
        return outliers


class RateLimitedLogger:
    """Logger wrapper that rate limits repeated messages to reduce spam.

    Useful for polling loops and other high-frequency operations where
    you don't need to log every single iteration.
    """

    def __init__(self, logger_instance, default_interval=60):
        self.logger = logger_instance
        self.default_interval = default_interval
        self._last_log = {}  # message_key -> timestamp
        self._counters = {}  # message_key -> count

    def _should_log(self, key: str, interval: int = None) -> bool:
        """Check if enough time has passed since last log of this key."""
        interval = interval or self.default_interval
        now = datetime.now().timestamp()
        last = self._last_log.get(key, 0)

        if now - last >= interval:
            self._last_log[key] = now
            return True
        return False

    def info(self, msg: str, key: str = None, interval: int = None):
        """Log info message with rate limiting."""
        log_key = key or msg
        if self._should_log(log_key, interval):
            self.logger.info(msg)

    def debug(self, msg: str, key: str = None, interval: int = None):
        """Log debug message with rate limiting."""
        log_key = key or msg
        if self._should_log(log_key, interval):
            self.logger.debug(msg)

    def warning(self, msg: str, key: str = None, interval: int = None):
        """Log warning message with rate limiting."""
        log_key = key or msg
        if self._should_log(log_key, interval):
            self.logger.warning(msg)

    def error(self, msg: str, key: str = None, interval: int = None):
        """Log error message with rate limiting (errors use shorter default interval)."""
        log_key = key or msg
        error_interval = interval or max(10, self.default_interval // 6)
        if self._should_log(log_key, error_interval):
            self.logger.error(msg)

    def log_with_counter(self, level: str, msg: str, key: str, counter_threshold: int = 10):
        """Log message only every Nth occurrence.

        Args:
            level: 'info', 'debug', 'warning', or 'error'
            msg: Message to log
            key: Unique key for this message type
            counter_threshold: Log every Nth occurrence
        """
        self._counters[key] = self._counters.get(key, 0) + 1
        count = self._counters[key]

        if count % counter_threshold == 0:
            full_msg = f"{msg} (x{count})"
            if level == 'info':
                self.logger.info(full_msg)
            elif level == 'debug':
                self.logger.debug(full_msg)
            elif level == 'warning':
                self.logger.warning(full_msg)
            elif level == 'error':
                self.logger.error(full_msg)


# Create utils instance
utils = Utils()