import sqlite3
import logging
from datetime import datetime, timedelta
from contextlib import contextmanager
import pandas as pd
import json
from core.config import Config
import threading

logger = logging.getLogger('crypto_bot')

class Database:
    """SQLite database wrapper with connection pooling per thread."""

    def __init__(self, db_path=None):
        self.db_path = db_path or Config.DATABASE_PATH
        # Thread-local storage for connection pooling
        self._local = threading.local()
        self._lock = threading.Lock()
        self._create_tables()

    def _get_thread_connection(self):
        """Get or create connection for current thread."""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.connection.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            self._local.connection.execute('PRAGMA journal_mode=WAL')
            self._local.connection.execute('PRAGMA busy_timeout=5000')  # 5 second timeout
        return self._local.connection

    def close_thread_connection(self):
        """Close connection for current thread (call on cleanup)."""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None

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
                    notes TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')

            # Add notes column if it doesn't exist (migration)
            try:
                cursor.execute('ALTER TABLE trades ADD COLUMN notes TEXT')
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

            # App Settings (for persisting bot configuration)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_price_pair_time ON price_history(pair, timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_trades_user ON trades(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_signals_pair_time ON signals(pair, timestamp)')
    
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
        
        # Also vacuum the database to reclaim disk space
        with self.get_connection() as conn:
            conn.execute('VACUUM')
            logger.debug("🗜️ Database vacuumed to reclaim disk space")

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
                                   signal_source, ml_confidence, status, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, pair, trade_type, price, amount, total, fee,
                  signal_source, ml_confidence, 'OPEN', notes))
            return cursor.lastrowid

    def get_trade(self, trade_id):
        """Get single trade by ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM trades WHERE id = ?', (trade_id,))
            return cursor.fetchone()

    def close_trade(self, trade_id, close_price, pnl, pnl_pct):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE trades
                SET status = 'CLOSED',
                    closed_at = ?,
                    profit_loss = ?,
                    profit_loss_pct = ?
                WHERE id = ?
            ''', (datetime.now(), pnl, pnl_pct, trade_id))

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
    
    # Performance
    def update_performance(self, user_id, date):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Calculate metrics
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
            
            if stats['total_trades'] > 0:
                win_rate = (stats['winning_trades'] / stats['total_trades']) * 100
            else:
                win_rate = 0
            
            cursor.execute('''
                INSERT OR REPLACE INTO performance
                (user_id, date, total_trades, winning_trades, losing_trades,
                 total_profit_loss, win_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, date, stats['total_trades'], stats['winning_trades'],
                  stats['losing_trades'], stats['total_pnl'], win_rate))

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
    def set_auto_trade_mode(self, is_dry_run):
        """Persist auto-trade mode (dry-run or real) to database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO app_settings (key, value)
                VALUES ('auto_trade_dry_run', ?)
            ''', (str(is_dry_run).lower(),))

    def get_auto_trade_mode(self):
        """Load auto-trade mode from database, default to dry-run if not set"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM app_settings WHERE key = ?', ('auto_trade_dry_run',))
            result = cursor.fetchone()
            if result:
                return result['value'].lower() == 'true'
            return True  # Default to dry-run for safety

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

                # Vacuum to reclaim space
                cursor.execute('VACUUM')

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
