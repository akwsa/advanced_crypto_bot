# Tujuan: Layer akses SQLite dan persistence state bot trading.
# Caller: bot.py, autotrade, signal pipeline, scalper, maintenance scripts.
# Dependensi: sqlite3, Config, thread-local connections, filesystem database.
# Main Functions: class Database; get_connection; save/update/read helpers.
# Side Effects: DB schema migration, DB read/write, connection lifecycle.
import sqlite3
import logging
from datetime import datetime, date, timedelta
from contextlib import contextmanager
import pandas as pd
import json
from core.config import Config
import threading

logger = logging.getLogger('crypto_bot')

# Python 3.12 deprecates the default datetime adapter for sqlite3.
# Register explicit ISO 8601 adapters so callers can keep passing datetime/date
# objects directly without triggering DeprecationWarning.
def _adapt_datetime_iso(value):
    return value.isoformat(sep=' ')


def _adapt_date_iso(value):
    return value.isoformat()


sqlite3.register_adapter(datetime, _adapt_datetime_iso)
sqlite3.register_adapter(date, _adapt_date_iso)

class Database:
    """SQLite database wrapper with connection pooling per thread."""

    def __init__(self, db_path=None):
        self.db_path = db_path or Config.DATABASE_PATH
        # Thread-local storage for connection pooling
        self._local = threading.local()
        self._lock = threading.Lock()
        self._closed = False
        self._create_tables()

    def close(self):
        """Close the database connection for the current thread."""
        if getattr(self, '_closed', False):
            return
        self._closed = True
        try:
            self.close_thread_connection()
            logger.info("💾 Database connection closed for current thread")
        except Exception as e:
            logger.warning(f"⚠️ Error closing database connection: {e}")

    def _get_thread_connection(self):
        """Get or create connection for current thread."""
        if getattr(self, '_closed', False):
            raise RuntimeError("Database connection has been closed")
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            with self._lock:
                # Double-check after acquiring lock
                if not hasattr(self._local, 'connection') or self._local.connection is None:
                    self._local.connection = sqlite3.connect(
                        self.db_path, check_same_thread=False, timeout=30.0
                    )
                    self._local.connection.row_factory = sqlite3.Row
                    # Enable WAL mode for better concurrency
                    self._local.connection.execute('PRAGMA journal_mode=WAL')
                    self._local.connection.execute('PRAGMA synchronous=NORMAL')  # Faster writes in WAL
                    self._local.connection.execute('PRAGMA busy_timeout=30000')  # 30 second timeout
                    self._local.connection.execute('PRAGMA wal_autocheckpoint=1000')
        return self._local.connection

    def close_thread_connection(self):
        """Close connection for current thread (call on cleanup)."""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None

    def _vacuum_database(self):
        """Run VACUUM outside transaction using a dedicated autocommit connection.
        FIX: Tidak pakai self._lock — VACUUM butuh exclusive DB lock sendiri,
        dan self._lock bisa deadlock jika thread lain sedang hold lock untuk
        membuat koneksi baru.
        """
        vacuum_conn = None
        try:
            vacuum_conn = sqlite3.connect(
                self.db_path, timeout=30.0, isolation_level=None, check_same_thread=False
            )
            vacuum_conn.execute('PRAGMA journal_mode=WAL')
            vacuum_conn.execute('PRAGMA busy_timeout=30000')
            vacuum_conn.execute('VACUUM')
            logger.debug("🗜️ Database vacuumed to reclaim disk space")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Database VACUUM skipped: {e}")
            return False
        finally:
            if vacuum_conn is not None:
                vacuum_conn.close()

    @contextmanager
    def get_connection(self):
        """Get database connection with auto-cleanup.

        Uses thread-local connection pooling for efficiency.
        """
        conn = None
        try:
            conn = self._get_thread_connection()
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise e
    
    def _create_tables(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Users
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    balance REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP
                )
            ''')

            # NEW: Watchlist (persistent storage for /watch pairs)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    pair TEXT NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1,
                    UNIQUE(user_id, pair),
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')

            # Create index for faster queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_watchlist_user_pair 
                ON watchlist(user_id, pair)
            ''')

            # Price History
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pair TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    UNIQUE(pair, timestamp)
                )
            ''')
            
            # Trades
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    pair TEXT,
                    type TEXT,
                    price REAL,
                    amount REAL,
                    total REAL,
                    fee REAL,
                    signal_source TEXT,
                    ml_confidence REAL,
                    status TEXT DEFAULT 'OPEN',
                    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMP,
                    profit_loss REAL,
                    profit_loss_pct REAL,
                    realized_profit_loss REAL DEFAULT 0,
                    original_total REAL,
                    notes TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')

            # Trade table migrations
            for ddl in (
                'ALTER TABLE trades ADD COLUMN notes TEXT',
                'ALTER TABLE trades ADD COLUMN realized_profit_loss REAL DEFAULT 0',
                'ALTER TABLE trades ADD COLUMN original_total REAL',
            ):
                try:
                    cursor.execute(ddl)
                except sqlite3.OperationalError:
                    pass  # Column already exists
            
            # Signals
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pair TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    signal_type TEXT,
                    price REAL,
                    confidence REAL,
                    indicators TEXT,
                    ml_prediction TEXT,
                    recommendation TEXT
                )
            ''')
            
            # Portfolio
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS portfolio (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    pair TEXT,
                    amount REAL,
                    avg_buy_price REAL,
                    current_value REAL,
                    unrealized_pnl REAL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # Performance Metrics
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS performance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    date DATE,
                    total_trades INTEGER,
                    winning_trades INTEGER,
                    losing_trades INTEGER,
                    total_profit_loss REAL,
                    win_rate REAL,
                    sharpe_ratio REAL,
                    max_drawdown REAL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # Drawdown State (for circuit breaker)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS drawdown_state (
                    user_id INTEGER PRIMARY KEY,
                    equity_peak REAL NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Pair Performance Tracker
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pair_performance (
                    pair TEXT PRIMARY KEY,
                    total_trades INTEGER DEFAULT 0,
                    win_count INTEGER DEFAULT 0,
                    loss_count INTEGER DEFAULT 0,
                    avg_profit_pct REAL DEFAULT 0,
                    avg_loss_pct REAL DEFAULT 0,
                    total_profit_pct REAL DEFAULT 0,
                    total_loss_pct REAL DEFAULT 0,
                    profit_factor REAL DEFAULT 0,
                    last_trade_at TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Trade Reviews (post-trade analysis)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trade_reviews (
                    trade_id INTEGER PRIMARY KEY,
                    pair TEXT,
                    entry_price REAL,
                    exit_price REAL,
                    pnl_pct REAL,
                    hold_duration_minutes INTEGER,
                    max_profit_pct REAL,
                    max_loss_pct REAL,
                    ml_confidence REAL,
                    v4_prediction TEXT,
                    v4_confidence REAL,
                    exit_reason TEXT,
                    lesson TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (trade_id) REFERENCES trades(id)
                )
            ''')
            
            # ML Model Metadata
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS ml_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_name TEXT,
                    version TEXT,
                    accuracy REAL,
                    trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    features TEXT,
                    parameters TEXT
                )
            ''')

            # Pending Limit Orders (execution tracking)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pending_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT NOT NULL,
                    pair TEXT NOT NULL,
                    user_id INTEGER,
                    trade_type TEXT NOT NULL,
                    limit_price REAL NOT NULL,
                    amount REAL NOT NULL,
                    total REAL,
                    status TEXT DEFAULT 'PENDING',
                    placed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    filled_at TIMESTAMP,
                    cancelled_at TIMESTAMP,
                    fill_price REAL,
                    trade_id INTEGER,
                    notes TEXT,
                    UNIQUE(order_id, pair)
                )
            ''')
            try:
                cursor.execute('ALTER TABLE pending_orders ADD COLUMN trade_id INTEGER')
            except sqlite3.OperationalError:
                pass

            # Telegram Access Control (whitelist + invite registration)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS telegram_users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    role TEXT DEFAULT 'user',
                    is_active INTEGER DEFAULT 1,
                    invite_code TEXT,
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TIMESTAMP,
                    blocked_reason TEXT
                )
            ''')

            # App Settings (for persisting bot configuration)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Adaptive Learning Tables
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS adaptive_thresholds (
                    pair TEXT PRIMARY KEY,
                    confidence_threshold_buy REAL DEFAULT 0.65,
                    confidence_threshold_strong_buy REAL DEFAULT 0.80,
                    min_rr_ratio REAL DEFAULT 1.5,
                    position_size_multiplier REAL DEFAULT 1.0,
                    skip_pair INTEGER DEFAULT 0,
                    win_rate_7d REAL DEFAULT 0.0,
                    profit_factor_7d REAL DEFAULT 0.0,
                    total_trades_7d INTEGER DEFAULT 0,
                    last_analyzed TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS regime_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pair TEXT NOT NULL,
                    regime TEXT NOT NULL,
                    volatility REAL DEFAULT 0.0,
                    trend_direction TEXT,
                    duration_minutes INTEGER DEFAULT 0,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trade_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id INTEGER,
                    pair TEXT NOT NULL,
                    entry_price REAL,
                    exit_price REAL,
                    ml_confidence REAL,
                    v4_prediction TEXT,
                    v4_confidence REAL,
                    recommendation TEXT,
                    pnl_pct REAL,
                    hold_duration_minutes INTEGER,
                    outcome_label TEXT,
                    market_regime TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (trade_id) REFERENCES trades(id)
                )
            ''')

            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_price_pair_time ON price_history(pair, timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_user ON trades(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_signals_pair_time ON signals(pair, timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_regime_pair ON regime_history(pair, started_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_outcomes_pair ON trade_outcomes(pair, created_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_outcomes_label ON trade_outcomes(outcome_label)')
    
    # User methods
    def add_user(self, user_id, username, first_name):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO users (user_id, username, first_name, balance, last_active)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, Config.INITIAL_BALANCE, datetime.now()))
    
    def update_balance(self, user_id, balance):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET balance = ? WHERE user_id = ?', (balance, user_id))
    
    def get_balance(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return result['balance'] if result else Config.INITIAL_BALANCE
    
    # Price history
    def save_price(self, pair, ohlcv):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO price_history (pair, timestamp, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (pair, ohlcv['timestamp'], ohlcv['open'], ohlcv['high'], 
                  ohlcv['low'], ohlcv['close'], ohlcv['volume']))
    
    def get_price_history(self, pair, limit=100, interval='15m'):
        with self.get_connection() as conn:
            df = pd.read_sql_query('''
                SELECT * FROM price_history
                WHERE pair = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', conn, params=(pair, limit))
            if not df.empty:
                # Normalize timestamps: replace 'T' with space to handle mixed formats
                df['timestamp'] = df['timestamp'].astype(str).str.replace('T', ' ', regex=False)
                df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
                df = df.dropna(subset=['timestamp'])
            return df.sort_values('timestamp')

    def cleanup_old_price_data(self, days=30):
        """Delete old price history data to save storage space"""
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=days)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Count records before deletion
            cursor.execute('SELECT COUNT(*) as cnt FROM price_history WHERE timestamp < ?', (cutoff_date,))
            old_count = cursor.fetchone()['cnt']
            
            if old_count > 0:
                cursor.execute('DELETE FROM price_history WHERE timestamp < ?', (cutoff_date,))
                conn.commit()
                logger.info(f"🗑️ Cleaned up {old_count} old price records (older than {days} days)")
            else:
                logger.debug(f"✅ No old price data to cleanup (keeping last {days} days)")
        
        # VACUUM must run outside active transaction.
        self._vacuum_database()

    def save_price_history(self, pair, df):
        """Save historical price data (candles) to database using batch insert.

        OPTIMIZED: Uses executemany for better performance.
        """
        if df.empty:
            return 0

        # Prepare data for batch insert
        records = []

        # Check if DataFrame has timestamp column or is datetime index
        df_copy = df.copy()
        if isinstance(df_copy.index, pd.DatetimeIndex):
            df_copy = df_copy.reset_index()
            df_copy.rename(columns={'index': 'timestamp'}, inplace=True)

        for idx, row in df_copy.iterrows():
            try:
                timestamp = row.get('timestamp', row.get('date'))
                if isinstance(timestamp, str):
                    timestamp = pd.to_datetime(timestamp)
                elif isinstance(timestamp, (int, float)):
                    timestamp = pd.to_datetime(timestamp, unit='s')

                records.append((
                    pair,
                    timestamp,
                    float(row.get('open', 0)),
                    float(row.get('high', 0)),
                    float(row.get('low', 0)),
                    float(row.get('close', 0)),
                    float(row.get('volume', 0))
                ))
            except Exception as e:
                logger.debug(f"Skipping invalid row in save_price_history: {e}")
                continue

        if not records:
            return 0

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Batch insert for better performance
                cursor.executemany('''
                    INSERT OR REPLACE INTO price_history
                    (pair, timestamp, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', records)
                logger.debug(f"Batch inserted {len(records)} price records for {pair}")
                return len(records)
        except Exception as e:
            logger.error(f"Error batch saving price history: {e}")
            return 0

    # Trades
    def add_trade(self, user_id, pair, trade_type, price, amount, total, fee, signal_source, ml_confidence, notes=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO trades (user_id, pair, type, price, amount, total, fee,
                                   signal_source, ml_confidence, status, original_total, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, pair, trade_type, price, amount, total, fee,
                  signal_source, ml_confidence, 'OPEN', total, notes))
            return cursor.lastrowid

    def get_trade(self, trade_id):
        """Get single trade by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM trades WHERE id = ?', (trade_id,))
            return cursor.fetchone()

    def update_trade_stop_loss(self, trade_id, stop_loss_price):
        """Update stop loss price for an open trade."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE trades
                SET notes = COALESCE(notes, '') || ' | Breakeven SL: ' || ?
                WHERE id = ? AND status = 'OPEN'
            ''', (stop_loss_price, trade_id))
            return cursor.rowcount > 0

    def _upsert_performance_for_date(self, conn, user_id, date):
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN profit_loss <= 0 THEN 1 ELSE 0 END) as losing_trades,
                SUM(profit_loss) as total_pnl,
                AVG(profit_loss_pct) as avg_pnl_pct
            FROM trades
            WHERE user_id = ? AND DATE(closed_at) = ?
        ''', (user_id, date))

        stats = cursor.fetchone()
        total_trades = stats['total_trades'] or 0
        winning_trades = stats['winning_trades'] or 0
        losing_trades = stats['losing_trades'] or 0
        total_pnl = stats['total_pnl'] or 0

        if total_trades > 0:
            win_rate = (winning_trades / total_trades) * 100
        else:
            win_rate = 0

        existing = cursor.execute(
            'SELECT id FROM performance WHERE user_id = ? AND date = ?',
            (user_id, date)
        ).fetchone()
        if existing:
            cursor.execute('''
                UPDATE performance
                SET total_trades = ?,
                    winning_trades = ?,
                    losing_trades = ?,
                    total_profit_loss = ?,
                    win_rate = ?
                WHERE id = ?
            ''', (total_trades, winning_trades, losing_trades, total_pnl, win_rate, existing['id']))
        else:
            cursor.execute('''
                INSERT INTO performance
                (user_id, date, total_trades, winning_trades, losing_trades,
                 total_profit_loss, win_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, date, total_trades, winning_trades,
                  losing_trades, total_pnl, win_rate))

    def close_trade(self, trade_id, close_price=None, pnl=None, pnl_pct=None, sell_price=None, sell_amount=None, order_id=None, reason=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM trades WHERE id = ?', (trade_id,))
            trade = cursor.fetchone()
            if not trade:
                logger.warning(f"Trade not found for close_trade: {trade_id}")
                return False

            raw_close_price = close_price if close_price is not None else sell_price
            try:
                effective_close_price = float(raw_close_price) if raw_close_price is not None else None
            except (TypeError, ValueError):
                effective_close_price = None
            try:
                entry_price = float(trade['price']) if trade['price'] is not None else None
            except (TypeError, ValueError):
                entry_price = None
            current_amount = float(trade['amount'] or 0)
            effective_amount = float(sell_amount if sell_amount is not None else current_amount)
            if current_amount <= 0 or effective_amount <= 0:
                logger.warning(f"Invalid close amount for trade {trade_id}: current={current_amount}, sell={effective_amount}")
                return False
            if effective_amount > current_amount:
                logger.warning(f"Sell amount exceeds open amount for trade {trade_id}; clamping {effective_amount} -> {current_amount}")
                effective_amount = current_amount

            if pnl is None:
                if effective_close_price is None or entry_price is None:
                    logger.warning(
                        f"Cannot close trade {trade_id}: missing valid price data "
                        f"(entry={trade['price']}, close={raw_close_price})"
                    )
                    return False
                pnl = (effective_close_price - entry_price) * effective_amount
            invested = (entry_price or 0) * effective_amount
            exit_pnl_pct = ((pnl / invested) * 100) if invested > 0 and pnl is not None else 0

            previous_realized = trade['realized_profit_loss'] if 'realized_profit_loss' in trade.keys() and trade['realized_profit_loss'] is not None else 0
            total_realized = previous_realized + (pnl or 0)
            remaining_amount = max(0.0, current_amount - effective_amount)
            closed_at = datetime.now()
            is_full_close = remaining_amount <= max(current_amount * 1e-8, 1e-12)
            original_total = (
                trade['original_total']
                if 'original_total' in trade.keys() and trade['original_total'] is not None
                else trade['total']
            )
            total_pnl_pct = ((total_realized / original_total) * 100) if original_total and original_total > 0 else exit_pnl_pct
            close_price_label = f"{effective_close_price:.8f}" if effective_close_price is not None else "N/A"

            if is_full_close:
                cursor.execute('''
                    UPDATE trades
                    SET status = 'CLOSED',
                        amount = ?,
                        total = ?,
                        closed_at = ?,
                        profit_loss = ?,
                        profit_loss_pct = ?,
                        realized_profit_loss = ?,
                        notes = COALESCE(notes, '') || ?
                    WHERE id = ?
                ''', (0.0, 0.0, closed_at, total_realized, total_pnl_pct, total_realized,
                      f" | Close {effective_amount:.8f} @ {close_price_label} ({reason or 'close'}) order={order_id or 'N/A'}", trade_id))
            else:
                remaining_total = remaining_amount * (entry_price or 0)
                cursor.execute('''
                    UPDATE trades
                    SET amount = ?,
                        total = ?,
                        realized_profit_loss = ?,
                        profit_loss = ?,
                        profit_loss_pct = ?,
                        notes = COALESCE(notes, '') || ?
                    WHERE id = ? AND status = 'OPEN'
                ''', (remaining_amount, remaining_total, total_realized, total_realized, total_pnl_pct,
                      f" | Partial close {effective_amount:.8f} @ {close_price_label} pnl={pnl or 0:.0f} ({reason or 'partial'}) order={order_id or 'N/A'}", trade_id))
                logger.info(
                    f"✅ Partial close trade {trade_id}: sold {effective_amount:.8f}, remaining {remaining_amount:.8f}, realized={total_realized:,.0f}"
                )

            if trade['user_id'] is not None:
                self._upsert_performance_for_date(conn, trade['user_id'], closed_at.date())
            
            # Update pair performance stats only after the position is fully closed,
            # otherwise one trade can be counted multiple times by partial exits.
            if is_full_close:
                self._update_pair_performance(conn, trade['pair'], total_pnl_pct)
            
            if is_full_close:
                # Create automatic trade review
                self.create_trade_review(conn, trade, effective_close_price, total_pnl_pct, reason)

            # Record trade outcome for adaptive learning (V4 training data)
            if is_full_close:
                try:
                    self._record_trade_outcome(
                        conn, trade_id, trade['pair'], trade['price'],
                        effective_close_price, trade['ml_confidence'] if trade['ml_confidence'] is not None else 0.5,
                        trade['type'], total_pnl_pct, trade['opened_at'] if 'opened_at' in trade.keys() else None, closed_at
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Failed to record trade outcome: {e}")

            return True

    def _record_trade_outcome(self, conn, trade_id, pair, entry_price, exit_price,
                              ml_confidence, trade_type, pnl_pct, opened_at, closed_at):
        """Record trade outcome for adaptive learning / V4 training."""
        cursor = conn.cursor()
        
        hold_duration = 0
        if opened_at and closed_at:
            try:
                if isinstance(opened_at, str):
                    opened_dt = datetime.fromisoformat(opened_at.replace('Z', '+00:00'))
                else:
                    opened_dt = opened_at
                hold_duration = int((closed_at - opened_dt).total_seconds() / 60)
            except Exception:
                pass
        
        rec_upper = (trade_type or 'HOLD').upper()
        if 'BUY' in rec_upper:
            label = 'GOOD_BUY' if pnl_pct > 0 else 'BAD_BUY'
        elif 'SELL' in rec_upper:
            label = 'GOOD_SELL' if pnl_pct > 0 else 'BAD_SELL'
        else:
            label = 'NEUTRAL'
        
        cursor.execute('''
            INSERT OR REPLACE INTO trade_outcomes (
                trade_id, pair, entry_price, exit_price, ml_confidence,
                recommendation, pnl_pct, hold_duration_minutes, outcome_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (trade_id, pair, entry_price, exit_price, ml_confidence,
              rec_upper, pnl_pct, hold_duration, label))

    def add_indodax_trade(self, user_id, pair, trade_type, price, amount, total, fee, indodax_order_id, timestamp, notes=None):
        """Add trade from Indodax API (synced trade)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Check if trade already exists
            cursor.execute('SELECT id FROM trades WHERE pair = ? AND price = ? AND amount = ? AND opened_at = ?',
                          (pair, price, amount, timestamp))
            if cursor.fetchone():
                return None  # Already exists

            cursor.execute('''
                INSERT INTO trades (user_id, pair, type, price, amount, total, fee,
                                   signal_source, ml_confidence, status, opened_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, pair, trade_type, price, amount, total, fee,
                  'INDODAX', 0, 'OPEN' if trade_type == 'BUY' else 'CLOSED', timestamp, notes))
            return cursor.lastrowid

    def get_open_trades(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM trades
                WHERE user_id = ? AND status = 'OPEN'
                ORDER BY opened_at DESC
            ''', (user_id,))
            return cursor.fetchall()

    def get_trades_for_pair(self, user_id, pair):
        """Get all trades (OPEN and CLOSED) for a specific pair, sorted by date DESC"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM trades
                WHERE user_id = ? AND pair = ?
                ORDER BY 
                    CASE WHEN status = 'OPEN' THEN 0 ELSE 1 END,
                    opened_at DESC
            ''', (user_id, pair))
            return cursor.fetchall()

    def get_trade_history(self, user_id, limit=20):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM trades
                WHERE user_id = ? AND status = 'CLOSED'
                ORDER BY closed_at DESC
                LIMIT ?
            ''', (user_id, limit))
            return cursor.fetchall()

    def count_trades_today(self, user_id):
        """Count trades opened today (for daily trade limit)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) as cnt FROM trades
                WHERE user_id = ? AND DATE(opened_at) = DATE('now')
            ''', (user_id,))
            result = cursor.fetchone()
            return result['cnt'] if result else 0
    
    # Performance
    def update_performance(self, user_id, date):
        with self.get_connection() as conn:
            self._upsert_performance_for_date(conn, user_id, date)

    def _update_pair_performance(self, conn, pair, pnl_pct):
        """Update pair performance stats when a trade is closed."""
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM pair_performance WHERE pair = ?', (pair,))
            row = cursor.fetchone()

            is_win = pnl_pct > 0 if pnl_pct is not None else False
            is_loss = pnl_pct < 0 if pnl_pct is not None else False

            if row:
                total = row['total_trades'] + 1
                wins = row['win_count'] + (1 if is_win else 0)
                losses = row['loss_count'] + (1 if is_loss else 0)
                total_profit = row['total_profit_pct'] + (pnl_pct if is_win else 0)
                total_loss = row['total_loss_pct'] + (abs(pnl_pct) if is_loss else 0)
                avg_profit = total_profit / wins if wins > 0 else 0
                avg_loss = total_loss / losses if losses > 0 else 0
                pf = total_profit / total_loss if total_loss > 0 else (float('inf') if total_profit > 0 else 0)

                cursor.execute('''
                    UPDATE pair_performance
                    SET total_trades = ?, win_count = ?, loss_count = ?,
                        avg_profit_pct = ?, avg_loss_pct = ?,
                        total_profit_pct = ?, total_loss_pct = ?,
                        profit_factor = ?, last_trade_at = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE pair = ?
                ''', (total, wins, losses, avg_profit, avg_loss, total_profit, total_loss, pf, datetime.now(), pair))
            else:
                profit = pnl_pct if is_win else 0
                loss = abs(pnl_pct) if is_loss else 0
                pf = float('inf') if profit > 0 and loss == 0 else (profit / loss if loss > 0 else 0)
                cursor.execute('''
                    INSERT INTO pair_performance
                    (pair, total_trades, win_count, loss_count, avg_profit_pct, avg_loss_pct,
                     total_profit_pct, total_loss_pct, profit_factor, last_trade_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (pair, 1, 1 if is_win else 0, 1 if is_loss else 0,
                      profit, loss, profit, loss, pf, datetime.now()))
        except Exception as e:
            logger.error(f"❌ Error updating pair performance for {pair}: {e}")

    def get_pair_performance(self, pair):
        """Get performance stats for a single pair."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM pair_performance WHERE pair = ?', (pair,))
            return cursor.fetchone()

    def get_all_pair_performance(self, min_trades=5):
        """Get all pair performance stats, optionally filtered by min trades."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM pair_performance
                WHERE total_trades >= ?
                ORDER BY profit_factor DESC, win_count DESC
            ''', (min_trades,))
            return cursor.fetchall()

    # =====================================================================
    # TRADE REVIEWS (Post-Trade Analysis)
    # =====================================================================

    def create_trade_review(self, conn, trade, exit_price, pnl_pct, exit_reason=None):
        """Create automatic trade review when a trade is closed.
        Requires an active connection (conn) because it's called inside close_trade.
        """
        try:
            cursor = conn.cursor()
            pair = trade['pair']
            entry_price = float(trade['price'] or 0)
            opened_at = trade['opened_at']
            closed_at = datetime.now()

            # Hold duration
            try:
                if isinstance(opened_at, str):
                    opened_dt = datetime.fromisoformat(opened_at.replace('Z', '+00:00'))
                else:
                    opened_dt = opened_at
                hold_duration = int((closed_at - opened_dt).total_seconds() / 60)
            except Exception:
                hold_duration = 0

            # Max profit / max loss during hold (from price_history)
            max_profit_pct = 0.0
            max_loss_pct = 0.0
            try:
                cursor.execute('''
                    SELECT MAX(high) as max_high, MIN(low) as min_low
                    FROM price_history
                    WHERE pair = ? AND timestamp >= ? AND timestamp <= ?
                ''', (pair, opened_at, closed_at))
                hist = cursor.fetchone()
                if hist and hist['max_high'] and hist['min_low'] and entry_price > 0:
                    max_profit_pct = (float(hist['max_high']) - entry_price) / entry_price * 100
                    max_loss_pct = (float(hist['min_low']) - entry_price) / entry_price * 100
            except Exception:
                pass

            # Lesson learned (auto-generated)
            lesson_parts = []
            if pnl_pct is not None:
                if pnl_pct > 0:
                    lesson_parts.append(f"✅ Trade profitable (+{pnl_pct:.2f}%)")
                else:
                    lesson_parts.append(f"❌ Trade loss ({pnl_pct:.2f}%)")
                    if max_profit_pct > 1.0:
                        lesson_parts.append(f"Had chance for +{max_profit_pct:.2f}% profit but didn't exit")
                    elif max_profit_pct <= 0:
                        lesson_parts.append("Never reached profit zone")
            if hold_duration > 240:  # > 4 hours
                lesson_parts.append(f"Held very long ({hold_duration // 60}h {hold_duration % 60}m)")
            elif hold_duration > 60:  # > 1 hour
                lesson_parts.append(f"Held {hold_duration // 60}h {hold_duration % 60}m")

            lesson = " | ".join(lesson_parts) if lesson_parts else "No specific lesson"

            # V4 prediction: try to find from signal history near entry time
            v4_pred = None
            v4_conf = None
            try:
                cursor.execute('''
                    SELECT analysis FROM signals
                    WHERE pair = ? AND timestamp <= ?
                    ORDER BY timestamp DESC LIMIT 1
                ''', (pair, opened_at))
                sig = cursor.fetchone()
                if sig and sig['analysis']:
                    import json
                    try:
                        analysis = json.loads(sig['analysis'])
                        v4_pred = analysis.get('v4_prediction')
                        v4_conf = analysis.get('v4_confidence')
                    except Exception:
                        pass
            except Exception:
                pass

            cursor.execute('''
                INSERT OR REPLACE INTO trade_reviews
                (trade_id, pair, entry_price, exit_price, pnl_pct,
                 hold_duration_minutes, max_profit_pct, max_loss_pct,
                 ml_confidence, v4_prediction, v4_confidence, exit_reason, lesson)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                trade['id'], pair, entry_price, exit_price,
                pnl_pct, hold_duration, max_profit_pct, max_loss_pct,
                trade['ml_confidence'], v4_pred, v4_conf,
                exit_reason, lesson
            ))
            logger.info(f"📝 Trade review created for trade {trade['id']} ({pair}): {lesson}")
        except Exception as e:
            logger.error(f"❌ Error creating trade review for trade {trade['id']}: {e}")

    def get_trade_review(self, trade_id):
        """Get trade review by trade ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM trade_reviews WHERE trade_id = ?', (trade_id,))
            return cursor.fetchone()

    def get_recent_trade_reviews(self, pair=None, limit=10):
        """Get recent trade reviews, optionally filtered by pair."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if pair:
                cursor.execute('''
                    SELECT * FROM trade_reviews
                    WHERE pair = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                ''', (pair, limit))
            else:
                cursor.execute('''
                    SELECT * FROM trade_reviews
                    ORDER BY created_at DESC
                    LIMIT ?
                ''', (limit,))
            return cursor.fetchall()

    # =====================================================================
    # PENDING LIMIT ORDERS (Execution Tracking)
    # =====================================================================

    def add_pending_order(self, order_id, pair, user_id, trade_type, limit_price, amount, total=None, notes=None, trade_id=None):
        """Register a newly placed limit order."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO pending_orders (order_id, pair, user_id, trade_type, limit_price, amount, total, trade_id, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (order_id, pair, user_id, trade_type, limit_price, amount, total, trade_id, notes))
            return cursor.lastrowid

    def get_pending_orders(self, pair=None, status='PENDING'):
        """Get pending limit orders."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if pair:
                cursor.execute('''
                    SELECT * FROM pending_orders WHERE pair = ? AND status = ? ORDER BY placed_at ASC
                ''', (pair, status))
            else:
                cursor.execute('''
                    SELECT * FROM pending_orders WHERE status = ? ORDER BY placed_at ASC
                ''', (status,))
            return cursor.fetchall()

    def update_pending_order_filled(self, db_id, fill_price, notes=None):
        """Mark pending order as filled."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE pending_orders
                SET status = 'FILLED', filled_at = CURRENT_TIMESTAMP, fill_price = ?, notes = COALESCE(?, notes)
                WHERE id = ?
            ''', (fill_price, notes, db_id))

    def update_pending_order_cancelled(self, db_id, notes=None):
        """Mark pending order as cancelled."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE pending_orders
                SET status = 'CANCELLED', cancelled_at = CURRENT_TIMESTAMP, notes = COALESCE(?, notes)
                WHERE id = ?
            ''', (notes, db_id))

    def get_pending_order_by_order_id(self, order_id, pair):
        """Get a specific pending order by exchange order_id and pair."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM pending_orders WHERE order_id = ? AND pair = ?
            ''', (order_id, pair))
            return cursor.fetchone()

    def get_performance(self, user_id, days=30):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM performance
                WHERE user_id = ? AND date >= date('now', ?)
                ORDER BY date DESC
            ''', (user_id, f'-{days} days'))
            return cursor.fetchall()

    # =====================================================================
    # WATCHLIST MANAGEMENT (Persistent Storage)
    # =====================================================================
    
    def add_to_watchlist(self, user_id: int, pair: str):
        """Add pair to user's watchlist"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO watchlist (user_id, pair, is_active)
                VALUES (?, ?, 1)
            ''', (user_id, pair.lower().strip()))
            logger.info(f"✅ Added {pair} to watchlist for user {user_id}")

    def remove_from_watchlist(self, user_id: int, pair: str):
        """Remove pair from user's watchlist"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM watchlist
                WHERE user_id = ? AND pair = ?
            ''', (user_id, pair.lower().strip()))
            logger.info(f"🗑️ Removed {pair} from watchlist for user {user_id}")

    def get_watchlist(self, user_id: int) -> list:
        """Get all active pairs in user's watchlist"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT pair FROM watchlist
                WHERE user_id = ? AND is_active = 1
                ORDER BY added_at ASC
            ''', (user_id,))
            return [row['pair'] for row in cursor.fetchall()]

    def get_all_pairs(self) -> list:
        """Get all unique pairs that have price data"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT pair FROM price_history')
            return [row['pair'] for row in cursor.fetchall()]
    
    def get_all_watchlists(self) -> dict:
        """Get all watchlists: {user_id: [pairs]}"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, pair FROM watchlist
                WHERE is_active = 1
                ORDER BY user_id, added_at ASC
            ''')
            
            watchlists = {}
            for row in cursor.fetchall():
                user_id = row['user_id']
                pair = row['pair']
                if user_id not in watchlists:
                    watchlists[user_id] = []
                watchlists[user_id].append(pair)
            
            return watchlists

    def remove_watchlist_for_pair(self, pair: str):
        """Remove a pair from ALL users' watchlists (used when pair is delisted/invalid)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            pair_clean = pair.lower().strip()
            cursor.execute('''
                DELETE FROM watchlist
                WHERE pair = ?
            ''', (pair_clean,))
            logger.info(f"🗑️ Removed {pair_clean} from all watchlists (invalid/delisted)")

    def clear_watchlist(self, user_id: int):
        """Clear all pairs from user's watchlist"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM watchlist
                WHERE user_id = ?
            ''', (user_id,))
            logger.info(f"🗑️ Cleared watchlist for user {user_id}")

    def clear_all_watchlists(self):
        """Clear ALL pairs from ALL users' watchlists (for /s_pair reset)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM watchlist')
            count = cursor.rowcount
            logger.info(f"🗑️ Cleared ALL watchlists: {count} records deleted")
            return count

    def is_watching(self, user_id: int, pair: str) -> bool:
        """Check if user is watching a specific pair"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) as cnt FROM watchlist
                WHERE user_id = ? AND pair = ? AND is_active = 1
            ''', (user_id, pair.lower().strip()))
            return cursor.fetchone()['cnt'] > 0

    def get_watchlist_count(self, user_id: int) -> int:
        """Get number of pairs in user's watchlist"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) as cnt FROM watchlist
                WHERE user_id = ? AND is_active = 1
            ''', (user_id,))
            return cursor.fetchone()['cnt']

    # Auto-trade mode persistence
    def upsert_telegram_user(self, user_id: int, username: str = None, first_name: str = None, role: str = 'user', is_active: int = 1, invite_code: str = None, blocked_reason: str = None):
        """Create or update a registered Telegram user."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO telegram_users
                (user_id, username, first_name, role, is_active, invite_code, last_seen_at, blocked_reason)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = COALESCE(excluded.username, telegram_users.username),
                    first_name = COALESCE(excluded.first_name, telegram_users.first_name),
                    role = COALESCE(excluded.role, telegram_users.role),
                    is_active = excluded.is_active,
                    invite_code = COALESCE(excluded.invite_code, telegram_users.invite_code),
                    last_seen_at = CURRENT_TIMESTAMP,
                    blocked_reason = COALESCE(excluded.blocked_reason, telegram_users.blocked_reason)
            ''', (user_id, username, first_name, role, is_active, invite_code, blocked_reason))

    def get_telegram_user(self, user_id: int):
        """Fetch a registered Telegram user by user ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM telegram_users WHERE user_id = ?', (user_id,))
            return cursor.fetchone()

    def get_active_telegram_users(self):
        """Return all active Telegram user IDs."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM telegram_users WHERE is_active = 1')
            return [row['user_id'] for row in cursor.fetchall()]

    def register_telegram_user(self, user_id: int, username: str = None, first_name: str = None, role: str = 'user', invite_code: str = None):
        """Register a Telegram user as active."""
        self.upsert_telegram_user(user_id, username=username, first_name=first_name, role=role, is_active=1, invite_code=invite_code)

    def deactivate_telegram_user(self, user_id: int, reason: str = None):
        """Deactivate a Telegram user."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE telegram_users
                SET is_active = 0,
                    blocked_reason = COALESCE(?, blocked_reason),
                    last_seen_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            ''', (reason, user_id))


    def get_auto_trade_mode(self):
        """Load auto-trade mode from database, default to dry-run if not set"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM app_settings WHERE key = ?', ('auto_trade_dry_run',))
            result = cursor.fetchone()
            if result:
                return result['value'].lower() == 'true'
            return True  # Default to dry-run for safety

    def set_signal_notifications_enabled(self, enabled):
        """Persist whether automatic signal notifications are sent to Telegram."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO app_settings (key, value)
                VALUES ('signal_notifications_enabled', ?)
            ''', (str(bool(enabled)).lower(),))

    def get_signal_notifications_enabled(self):
        """Load signal notification toggle, default enabled for backward compatibility."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM app_settings WHERE key = ?', ('signal_notifications_enabled',))
            result = cursor.fetchone()
            if result:
                return result['value'].lower() == 'true'
            return True

    # Signal Notification Filter
    # Allowed modes:
    #   "all"        -> kirim semua sinyal (default, sama seperti perilaku lama)
    #   "buy"        -> hanya BUY/STRONG_BUY
    #   "sell"       -> hanya SELL/STRONG_SELL
    #   "actionable" -> hanya BUY/STRONG_BUY + SELL/STRONG_SELL (skip HOLD)
    SIGNAL_NOTIFICATION_FILTERS = ('all', 'buy', 'sell', 'actionable')

    def set_signal_notification_filter(self, mode):
        """Persist signal notification filter mode."""
        mode = (mode or 'all').lower()
        if mode not in self.SIGNAL_NOTIFICATION_FILTERS:
            raise ValueError(f"Invalid signal notification filter: {mode}")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO app_settings (key, value)
                VALUES ('signal_notification_filter', ?)
            ''', (mode,))

    def get_signal_notification_filter(self):
        """Load signal notification filter mode (default 'all')."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM app_settings WHERE key = ?', ('signal_notification_filter',))
            result = cursor.fetchone()
            if result:
                value = (result['value'] or '').lower()
                if value in self.SIGNAL_NOTIFICATION_FILTERS:
                    return value
            return 'all'

    # Drawdown / Circuit Breaker State
    def get_equity_peak(self, user_id):
        """Get stored equity peak for user. Returns None if not set."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT equity_peak FROM drawdown_state WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return result['equity_peak'] if result else None

    def set_equity_peak(self, user_id, peak):
        """Persist equity peak for user."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO drawdown_state (user_id, equity_peak, last_updated)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    equity_peak = excluded.equity_peak,
                    last_updated = CURRENT_TIMESTAMP
            ''', (user_id, peak))

    # =====================================================================
    # DATABASE HEALTH & OPTIMIZATION
    # =====================================================================

    def health_check(self) -> dict:
        """Check database health and return status report."""
        report = {
            'status': 'healthy',
            'errors': [],
            'table_counts': {},
            'db_size_mb': 0
        }

        try:
            # Check connection
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Get table counts
                tables = ['users', 'watchlist', 'price_history', 'trades', 'signals', 'portfolio', 'performance']
                for table in tables:
                    try:
                        cursor.execute(f'SELECT COUNT(*) as cnt FROM {table}')
                        count = cursor.fetchone()['cnt']
                        report['table_counts'][table] = count
                    except Exception as e:
                        report['errors'].append(f"Error counting {table}: {e}")

                # Get database size
                try:
                    cursor.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
                    size_bytes = cursor.fetchone()['size']
                    report['db_size_mb'] = round(size_bytes / (1024 * 1024), 2)
                except Exception as e:
                    report['errors'].append(f"Error getting DB size: {e}")

                # Check for corruption
                try:
                    cursor.execute('PRAGMA integrity_check')
                    integrity = cursor.fetchone()[0]
                    if integrity != 'ok':
                        report['status'] = 'corrupted'
                        report['errors'].append(f"Integrity check failed: {integrity}")
                except Exception as e:
                    report['errors'].append(f"Integrity check error: {e}")

        except Exception as e:
            report['status'] = 'error'
            report['errors'].append(f"Database connection failed: {e}")

        return report

    def optimize_database(self) -> bool:
        """Optimize database: VACUUM and analyze tables."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Analyze tables for query optimization
                cursor.execute('ANALYZE')
            self._vacuum_database()
            logger.info("✅ Database optimized successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Database optimization failed: {e}")
            return False

    def get_performance_stats(self) -> dict:
        """Get database performance statistics."""
        stats = {
            'slow_queries': [],
            'index_usage': {},
            'cache_hit_ratio': None
        }

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Get index usage stats (if available)
                try:
                    cursor.execute('SELECT * FROM sqlite_stat1 LIMIT 10')
                    rows = cursor.fetchall()
                    for row in rows:
                        stats['index_usage'][row[0]] = row[1]
                except Exception:
                    pass  # sqlite_stat1 might not exist

        except Exception as e:
            logger.error(f"Error getting performance stats: {e}")

        return stats
