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
import math

logger = logging.getLogger('crypto_bot')

AUTOTRADE_EXECUTED_STATUSES = frozenset({'FILLED', 'PENDING'})
AUTOTRADE_TERMINAL_STATUSES = frozenset({'FILLED', 'NO_ENTRY', 'REJECTED', 'CANCELLED', 'ERROR_TERMINAL'})
AUTOTRADE_GENERIC_REASON_CODES = frozenset({
    '', 'OTHER', 'NO_ORDER_CREATED', 'UNCLASSIFIED_INTERNAL_ERROR',
})


def build_autotrade_funnel_report(conn, *, user_id=None, start_at=None, end_at=None):
    """Aggregate durable intent outcomes without mutating the database."""
    clauses = []
    params = []
    if user_id is not None:
        clauses.append('user_id = ?')
        params.append(int(user_id))
    if start_at is not None:
        clauses.append('created_at >= ?')
        params.append(str(start_at))
    if end_at is not None:
        clauses.append('created_at < ?')
        params.append(str(end_at))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    rows = conn.execute(f'''
        SELECT status, COALESCE(reason_code, '') AS reason_code,
               lower(replace(replace(pair, '/', ''), '_', '')) AS pair,
               COUNT(*) AS count
        FROM autotrade_intents
        {where}
        GROUP BY status, COALESCE(reason_code, ''),
                 lower(replace(replace(pair, '/', ''), '_', ''))
        ORDER BY status, reason_code, pair
    ''', params).fetchall()

    status_counts = {}
    reason_counts = {}
    pair_counts = {}
    actionable_total = 0
    generic_total = 0
    for row in rows:
        status = str(row[0] or '')
        reason_code = str(row[1] or '').strip().upper()
        pair = str(row[2] or '')
        count = int(row[3])
        actionable_total += count
        status_counts[status] = status_counts.get(status, 0) + count
        reason_counts[reason_code] = reason_counts.get(reason_code, 0) + count
        pair_counts[pair] = pair_counts.get(pair, 0) + count
        if reason_code in AUTOTRADE_GENERIC_REASON_CODES:
            generic_total += count

    unattributed_total = 0
    if user_id is not None:
        attribution_clauses = ['user_id IS NULL']
        attribution_params = []
        if start_at is not None:
            attribution_clauses.append('created_at >= ?')
            attribution_params.append(str(start_at))
        if end_at is not None:
            attribution_clauses.append('created_at < ?')
            attribution_params.append(str(end_at))
        unattributed_total = int(conn.execute(
            f"SELECT COUNT(*) FROM autotrade_intents WHERE {' AND '.join(attribution_clauses)}",
            attribution_params,
        ).fetchone()[0])

    executed_total = sum(status_counts.get(status, 0) for status in AUTOTRADE_EXECUTED_STATUSES)
    terminal_total = sum(status_counts.get(status, 0) for status in AUTOTRADE_TERMINAL_STATUSES)
    return {
        'window': {'start_at': start_at, 'end_at': end_at, 'user_id': user_id},
        'totals': {
            'actionable_total': actionable_total,
            'executed_total': executed_total,
            'terminal_total': terminal_total,
            'conversion_rate': executed_total / actionable_total if actionable_total else 0.0,
            'terminal_coverage_rate': terminal_total / actionable_total if actionable_total else 1.0,
        },
        'integrity': {
            'generic_total': generic_total,
            'generic_rate': generic_total / actionable_total if actionable_total else 0.0,
            'excluded_unattributed_total': unattributed_total,
        },
        'by_status': dict(sorted(status_counts.items())),
        'by_reason': dict(sorted(reason_counts.items())),
        'by_pair': dict(sorted(pair_counts.items())),
    }

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
                    self._local.connection.execute('PRAGMA foreign_keys=ON')
                    self._local.connection.execute('PRAGMA synchronous=NORMAL')  # Faster writes in WAL
                    self._local.connection.execute('PRAGMA busy_timeout=30000')  # 30 second timeout
                    self._local.connection.execute('PRAGMA wal_autocheckpoint=1000')
        return self._local.connection

    def close_thread_connection(self):
        """Close connection for current thread (call on cleanup)."""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None

    def checkpoint_wal(self, mode: str = "PASSIVE") -> bool:
        """
        Force WAL checkpoint to flush all WAL frames into the main DB file.

        Bug HIGH #6 (audit 2026-06-07): `os._exit(3)` di health monitor
        skip cleanup → WAL bisa tertinggal frame yang belum di-checkpoint.
        Walau SQLite recovery biasanya menanganinya saat next open, panggil
        ini sebelum hard exit untuk meminimalkan window corruption risk.

        Modes (per SQLite docs):
        - PASSIVE: tidak block writer, mungkin tidak full-checkpoint.
        - FULL: tunggu sampai semua frame ter-checkpoint.
        - RESTART: FULL + restart WAL file dari awal.
        - TRUNCATE: RESTART + truncate WAL file ke 0 byte.

        Returns True on success, False on error.
        """
        try:
            conn = sqlite3.connect(self.db_path, timeout=5.0, check_same_thread=False)
            try:
                # PRAGMA wal_checkpoint returns (busy, log, checkpointed)
                row = conn.execute(f"PRAGMA wal_checkpoint({mode})").fetchone()
                logger.info(f"💾 WAL checkpoint ({mode}) for {self.db_path}: {row}")
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"⚠️ WAL checkpoint failed for {self.db_path}: {e}")
            return False

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

            def ensure_columns(table_name, column_ddls):
                existing = {
                    row["name"] if isinstance(row, sqlite3.Row) else row[1]
                    for row in conn.execute(f"PRAGMA table_info({table_name})")
                }
                for column_name, ddl in column_ddls:
                    if column_name not in existing:
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")
                        existing.add(column_name)

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

            # Additive AutoTrade journal.  Legacy ``trades`` remains a
            # compatibility projection while this normalized journal provides
            # deterministic replay and idempotency.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS autotrade_intents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    correlation_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    pair TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    signal_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'RECEIVED',
                    reason_code TEXT,
                    reason TEXT,
                    legacy_trade_id INTEGER,
                    user_id INTEGER,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            try: cursor.execute('ALTER TABLE autotrade_intents ADD COLUMN legacy_trade_id INTEGER')
            except sqlite3.OperationalError: pass
            try: cursor.execute('ALTER TABLE autotrade_intents ADD COLUMN user_id INTEGER')
            except sqlite3.OperationalError: pass
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_autotrade_intents_funnel
                ON autotrade_intents(user_id, created_at, status, reason_code, pair)''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS autotrade_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    intent_id INTEGER NOT NULL UNIQUE,
                    order_id TEXT NOT NULL UNIQUE,
                    pair TEXT NOT NULL,
                    user_id INTEGER NOT NULL DEFAULT 1,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    limit_price REAL NOT NULL CHECK(limit_price > 0),
                    quantity REAL NOT NULL CHECK(quantity > 0),
                    total REAL NOT NULL CHECK(total > 0),
                    status TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(intent_id) REFERENCES autotrade_intents(id)
                )
            ''')
            try: cursor.execute('ALTER TABLE autotrade_orders ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1')
            except sqlite3.OperationalError: pass
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS autotrade_fills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    fill_key TEXT NOT NULL UNIQUE,
                    price REAL NOT NULL CHECK(price > 0),
                    quantity REAL NOT NULL CHECK(quantity > 0),
                    total REAL NOT NULL CHECK(total > 0),
                    fee REAL NOT NULL CHECK(fee >= 0),
                    filled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(order_id) REFERENCES autotrade_orders(id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS autotrade_positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pair TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    quantity REAL NOT NULL CHECK(quantity >= 0),
                    avg_price REAL NOT NULL CHECK(avg_price >= 0),
                    cost_basis REAL NOT NULL CHECK(cost_basis >= 0),
                    fees REAL NOT NULL CHECK(fees >= 0),
                    status TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(pair, user_id)
                )
            ''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS autotrade_rejections(
                id INTEGER PRIMARY KEY AUTOINCREMENT, signal_id TEXT UNIQUE,
                reason_code TEXT NOT NULL, envelope_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

            # Strategy 2 Phase 1 uses an entirely separate journal/projection.
            # These additive tables are intentionally not wired into the
            # Strategy 1 runtime, users.balance, trades, or autotrade_* ledger.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS strategy2_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_version TEXT NOT NULL,
                    experiment_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    pair TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    evidence_json TEXT NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(strategy_version, experiment_id, idempotency_key)
                )
            ''')
            ensure_columns("strategy2_decisions", (
                ("strategy_version", "strategy_version TEXT NOT NULL DEFAULT ''"),
                ("experiment_id", "experiment_id TEXT NOT NULL DEFAULT ''"),
                ("idempotency_key", "idempotency_key TEXT NOT NULL DEFAULT ''"),
                ("correlation_id", "correlation_id TEXT NOT NULL DEFAULT ''"),
                ("snapshot_id", "snapshot_id TEXT NOT NULL DEFAULT ''"),
                ("pair", "pair TEXT NOT NULL DEFAULT ''"),
                ("status", "status TEXT NOT NULL DEFAULT ''"),
                ("reason_code", "reason_code TEXT NOT NULL DEFAULT ''"),
                ("reason", "reason TEXT NOT NULL DEFAULT ''"),
                ("evidence_json", "evidence_json TEXT NOT NULL DEFAULT '{}'"),
                ("created_at", "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"),
            ))
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS strategy2_state_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_version TEXT NOT NULL,
                    experiment_id TEXT NOT NULL,
                    event_key TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    pair TEXT NOT NULL,
                    from_state TEXT,
                    to_state TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    event_json TEXT NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(strategy_version, experiment_id, event_key)
                )
            ''')
            ensure_columns("strategy2_state_events", (
                ("strategy_version", "strategy_version TEXT NOT NULL DEFAULT ''"),
                ("experiment_id", "experiment_id TEXT NOT NULL DEFAULT ''"),
                ("event_key", "event_key TEXT NOT NULL DEFAULT ''"),
                ("correlation_id", "correlation_id TEXT NOT NULL DEFAULT ''"),
                ("snapshot_id", "snapshot_id TEXT NOT NULL DEFAULT ''"),
                ("user_id", "user_id INTEGER NOT NULL DEFAULT 0"),
                ("pair", "pair TEXT NOT NULL DEFAULT ''"),
                ("from_state", "from_state TEXT"),
                ("to_state", "to_state TEXT NOT NULL DEFAULT ''"),
                ("reason_code", "reason_code TEXT NOT NULL DEFAULT ''"),
                ("event_json", "event_json TEXT NOT NULL DEFAULT '{}'"),
                ("created_at", "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"),
            ))
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS strategy2_portfolios (
                    strategy_version TEXT NOT NULL,
                    experiment_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    cash REAL NOT NULL CHECK(cash >= 0),
                    initial_cash REAL NOT NULL CHECK(initial_cash > 0),
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(strategy_version, experiment_id, user_id)
                )
            ''')
            ensure_columns("strategy2_portfolios", (
                ("strategy_version", "strategy_version TEXT NOT NULL DEFAULT ''"),
                ("experiment_id", "experiment_id TEXT NOT NULL DEFAULT ''"),
                ("user_id", "user_id INTEGER NOT NULL DEFAULT 0"),
                ("cash", "cash REAL NOT NULL DEFAULT 0"),
                ("initial_cash", "initial_cash REAL NOT NULL DEFAULT 1"),
                ("updated_at", "updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"),
            ))
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS strategy2_positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_version TEXT NOT NULL,
                    experiment_id TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    pair TEXT NOT NULL,
                    state TEXT NOT NULL,
                    quantity REAL NOT NULL CHECK(quantity >= 0),
                    avg_price REAL NOT NULL CHECK(avg_price >= 0),
                    cost_basis REAL NOT NULL CHECK(cost_basis >= 0),
                    fees REAL NOT NULL CHECK(fees >= 0),
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(strategy_version, experiment_id, user_id, pair)
                )
            ''')
            ensure_columns("strategy2_positions", (
                ("strategy_version", "strategy_version TEXT NOT NULL DEFAULT ''"),
                ("experiment_id", "experiment_id TEXT NOT NULL DEFAULT ''"),
                ("user_id", "user_id INTEGER NOT NULL DEFAULT 0"),
                ("pair", "pair TEXT NOT NULL DEFAULT ''"),
                ("state", "state TEXT NOT NULL DEFAULT ''"),
                ("quantity", "quantity REAL NOT NULL DEFAULT 0"),
                ("avg_price", "avg_price REAL NOT NULL DEFAULT 0"),
                ("cost_basis", "cost_basis REAL NOT NULL DEFAULT 0"),
                ("fees", "fees REAL NOT NULL DEFAULT 0"),
                ("updated_at", "updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP"),
            ))
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_strategy2_decisions_snapshot
                ON strategy2_decisions(strategy_version, experiment_id, snapshot_id)''')
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_strategy2_events_position
                ON strategy2_state_events(strategy_version, experiment_id, user_id, pair, id)''')
            cursor.execute('''CREATE INDEX IF NOT EXISTS idx_strategy2_positions_state
                ON strategy2_positions(strategy_version, experiment_id, state)''')

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

    @staticmethod
    def _ensure_virtual_cash_account(conn, user_id):
        """Create a dry-run cash account without silently starting at zero."""
        conn.execute(
            'INSERT OR IGNORE INTO users(user_id, balance) VALUES(?, ?)',
            (user_id, float(Config.INITIAL_BALANCE)),
        )

    @staticmethod
    def _apply_virtual_cash_fill(conn, user_id, side, total, fee):
        """Apply one fill to virtual cash inside the caller's transaction."""
        total, fee = float(total), float(fee)
        if side.upper() == 'BUY':
            required = total + fee
            updated = conn.execute(
                'UPDATE users SET balance=balance-? WHERE user_id=? AND balance>=?',
                (required, user_id, required),
            ).rowcount
            if updated != 1:
                raise ValueError('insufficient virtual cash for dry-run fill')
        elif side.upper() == 'SELL':
            conn.execute(
                'UPDATE users SET balance=balance+? WHERE user_id=?',
                (total - fee, user_id),
            )
        else:
            raise ValueError(f'unsupported dry-run side: {side}')
    
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

    def _table_count(self, cursor, table, where_clause=None, params=()):
        query = f"SELECT COUNT(*) as cnt FROM {table}"
        if where_clause:
            query += f" WHERE {where_clause}"
        cursor.execute(query, params)
        return cursor.fetchone()['cnt']

    def _delete_from_table(self, cursor, table, where_clause=None, params=()):
        count = self._table_count(cursor, table, where_clause, params)
        if count <= 0:
            return 0
        query = f"DELETE FROM {table}"
        if where_clause:
            query += f" WHERE {where_clause}"
        cursor.execute(query, params)
        return cursor.rowcount

    def _db_size_gb(self):
        import os
        try:
            size = os.path.getsize(self.db_path)
            for suffix in ('-wal', '-shm'):
                sidecar = f"{self.db_path}{suffix}"
                if os.path.exists(sidecar):
                    size += os.path.getsize(sidecar)
            return size / (1024 ** 3)
        except OSError:
            return 0.0

    def cleanup_old_price_data(self, days=30, max_db_size_gb=None):
        """Delete old price history data to save storage space.

        Keeps the normal retention window at ``days``. If ``max_db_size_gb`` is
        provided and the SQLite database is larger than that limit, this still
        applies the same retention cutoff immediately and logs the size trigger.
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        db_size_gb = self._db_size_gb()
        size_triggered = max_db_size_gb is not None and db_size_gb > max_db_size_gb
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            old_count = self._table_count(cursor, 'price_history', 'timestamp < ?', (cutoff_date,))
            if old_count > 0:
                cursor.execute('DELETE FROM price_history WHERE timestamp < ?', (cutoff_date,))
                conn.commit()
                suffix = f" (DB size {db_size_gb:.2f}GB > {max_db_size_gb}GB)" if size_triggered else ""
                logger.info(f"🗑️ Cleaned up {old_count} old price records (older than {days} days){suffix}")
            else:
                logger.debug(f"✅ No old price data to cleanup (keeping last {days} days)")
        
        # VACUUM must run outside active transaction.
        self._vacuum_database()
        return old_count

    def cleanup_old_runtime_history(self, days=30, max_db_size_gb=None):
        """Delete old closed bot runtime history while preserving open positions.

        This covers Telegram AutoTrade/SmartHunter/AutoHunter analysis history:
        closed trades, daily performance, pair performance, trade reviews,
        trade outcomes, and in-DB signal rows. Open trades are intentionally
        preserved so live/running positions are not removed by retention.
        """
        cutoff_dt = datetime.now() - timedelta(days=days)
        cutoff_date = cutoff_dt.date().isoformat()
        db_size_gb = self._db_size_gb()
        size_triggered = max_db_size_gb is not None and db_size_gb > max_db_size_gb
        deleted = {}

        with self.get_connection() as conn:
            cursor = conn.cursor()
            old_closed_ids = [
                row['id'] for row in cursor.execute(
                    """
                    SELECT id FROM trades
                    WHERE status = 'CLOSED'
                      AND COALESCE(closed_at, opened_at) < ?
                    """,
                    (cutoff_dt,),
                ).fetchall()
            ]
            if old_closed_ids:
                placeholders = ','.join('?' for _ in old_closed_ids)
                deleted['trade_reviews'] = self._delete_from_table(cursor, 'trade_reviews', f'trade_id IN ({placeholders})', old_closed_ids)
                deleted['trade_outcomes'] = self._delete_from_table(cursor, 'trade_outcomes', f'trade_id IN ({placeholders})', old_closed_ids)
                deleted['trades'] = self._delete_from_table(cursor, 'trades', f'id IN ({placeholders})', old_closed_ids)
            else:
                deleted['trade_reviews'] = 0
                deleted['trade_outcomes'] = 0
                deleted['trades'] = 0

            deleted['performance'] = self._delete_from_table(cursor, 'performance', 'date < ?', (cutoff_date,))
            deleted['pair_performance'] = self._delete_from_table(cursor, 'pair_performance', 'last_trade_at < ?', (cutoff_dt,))
            deleted['signals'] = self._delete_from_table(cursor, 'signals', 'timestamp < ?', (cutoff_dt,))

        if any(deleted.values()):
            suffix = f" (DB size {db_size_gb:.2f}GB > {max_db_size_gb}GB)" if size_triggered else ""
            logger.info(f"🗑️ Runtime history cleanup (> {days} days){suffix}: {deleted}")
            self._vacuum_database()
        return deleted

    def reset_runtime_history(self, include_open=False):
        """Reset Telegram bot runtime history so analysis starts fresh now.

        By default this clears only closed trade history and analytics. Passing
        ``include_open=True`` also removes open bot positions; use only for an
        explicit operator-requested reset.
        """
        deleted = {}
        with self.get_connection() as conn:
            cursor = conn.cursor()
            deleted['trade_reviews'] = self._delete_from_table(cursor, 'trade_reviews')
            deleted['trade_outcomes'] = self._delete_from_table(cursor, 'trade_outcomes')
            if include_open:
                deleted['trades'] = self._delete_from_table(cursor, 'trades')
            else:
                deleted['trades'] = self._delete_from_table(cursor, 'trades', "status = 'CLOSED'")
            deleted['performance'] = self._delete_from_table(cursor, 'performance')
            deleted['pair_performance'] = self._delete_from_table(cursor, 'pair_performance')
            deleted['signals'] = self._delete_from_table(cursor, 'signals')
        if any(deleted.values()):
            logger.warning(f"🧹 Runtime history reset completed: {deleted}")
            self._vacuum_database()
        return deleted

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

                # sqlite3 only adapts exact stdlib datetime/date objects. Pandas
                # Timestamp (including values produced by DataFrame iteration)
                # is a datetime subclass but is not handled by that adapter.
                # Persist an ISO string so batch inserts work consistently for
                # pandas, Python datetime, and parsed string inputs.
                timestamp = pd.Timestamp(timestamp)
                if pd.isna(timestamp):
                    raise ValueError("timestamp is missing or invalid")
                timestamp = timestamp.isoformat(sep=' ')

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
    def add_trade(self, user_id, pair, trade_type, price, amount, total, fee, signal_source, ml_confidence, notes=None, status='OPEN', original_total=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT OR IGNORE INTO users(user_id) VALUES(?)',(user_id,))
            effective_status = status or 'OPEN'
            effective_original_total = total if original_total is None else original_total
            cursor.execute('''
                INSERT INTO trades (user_id, pair, type, price, amount, total, fee,
                                   signal_source, ml_confidence, status, original_total, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, pair, trade_type, price, amount, total, fee,
                  signal_source, ml_confidence, effective_status, effective_original_total, notes))
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

    def get_recent_closed_trades_for_pair(self, user_id, pair, limit=5):
        """Get last N CLOSED trades for a specific pair, ordered by closed_at DESC.

        Used by the pair loss-streak gate to detect consecutive losers.
        Returns list of dict-like rows with profit_loss field.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM trades
                WHERE user_id = ? AND pair = ? AND status = 'CLOSED'
                ORDER BY closed_at DESC
                LIMIT ?
            ''', (user_id, pair, limit))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

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
                ORDER BY
                    CASE
                        WHEN loss_count = 0 AND total_trades < 10 THEN 1
                        ELSE 0
                    END ASC,
                    profit_factor DESC,
                    total_trades DESC,
                    win_count DESC
            ''', (min_trades,))
            return cursor.fetchall()

    # =====================================================================
    # TRADE REVIEWS (Post-Trade Analysis)
    # =====================================================================

    def create_trade_review(self, conn, trade, exit_price, pnl_pct, exit_reason=None):
        """Create automatic trade review when a trade is closed.
        Requires an active connection (conn) because it's called inside close_trade.

        Bug HIGH #5 (audit 2026-06-07): trade review duplikat 4-8x per trade.
        Walau tabel pakai PRIMARY KEY trade_id + INSERT OR REPLACE (jadi tidak
        ada row duplicate), method ini bisa dipanggil multi kali untuk trade
        yang sama (partial→full close, retry, dll) → CPU waste + log noise +
        adaptive learning bisa pakai data yang berbeda dari panggilan terakhir.
        Idempotency guard: skip kalau review sudah ada untuk trade_id ini.
        """
        try:
            cursor = conn.cursor()
            trade_id = trade['id']
            # Idempotency: cek review existing dulu
            cursor.execute('SELECT 1 FROM trade_reviews WHERE trade_id = ? LIMIT 1', (trade_id,))
            if cursor.fetchone() is not None:
                logger.debug(f"⏭️ Trade review already exists for trade {trade_id}, skipping (idempotent)")
                return
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
            cursor.execute('INSERT OR IGNORE INTO users(user_id) VALUES(?)',(user_id,))
            cursor.execute('''
                INSERT INTO pending_orders (order_id, pair, user_id, trade_type, limit_price, amount, total, trade_id, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (order_id, pair, user_id, trade_type, limit_price, amount, total, trade_id, notes))
            return cursor.lastrowid

    def record_autotrade_intent(self, intent):
        """Insert an intent once and return its durable row/decision state."""
        payload = intent.to_dict() if hasattr(intent, "to_dict") else dict(intent)
        with self.get_connection() as conn:
            conn.execute('''
                INSERT OR IGNORE INTO autotrade_intents
                (idempotency_key, correlation_id, version, pair, recommendation,
                 signal_json, user_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime(?, 'unixepoch'))
            ''', (payload['idempotency_key'], payload['correlation_id'], payload.get('version', 1),
                  payload['pair'], payload['recommendation'], json.dumps(payload['signal'], sort_keys=True, default=str),
                  payload.get('user_id'),
                  payload['created_at']))
            return conn.execute(
                'SELECT * FROM autotrade_intents WHERE idempotency_key = ?',
                (payload['idempotency_key'],)
            ).fetchone()

    def record_autotrade_rejection(self, signal_id, reason_code, envelope):
        with self.get_connection() as conn:
            conn.execute('INSERT OR IGNORE INTO autotrade_rejections(signal_id,reason_code,envelope_json) VALUES(?,?,?)',
                         (str(signal_id),str(reason_code),json.dumps(envelope,sort_keys=True,default=str)))

    def decide_autotrade_intent(self, idempotency_key, status, reason_code, reason=''):
        with self.get_connection() as conn:
            conn.execute('''
                UPDATE autotrade_intents SET status=?, reason_code=?, reason=?,
                    updated_at=CURRENT_TIMESTAMP WHERE idempotency_key=?
            ''', (status, reason_code, reason, idempotency_key))
            return conn.execute(
                'SELECT * FROM autotrade_intents WHERE idempotency_key=?', (idempotency_key,)
            ).fetchone()

    def get_autotrade_funnel_report(self, *, user_id=None, start_at=None, end_at=None):
        """Return a read-only aggregate of durable autotrade intent outcomes."""
        with self.get_connection() as conn:
            return build_autotrade_funnel_report(
                conn, user_id=user_id, start_at=start_at, end_at=end_at,
            )

    def record_dryrun_fill(self, *, intent, user_id, order_id, pair, side,
                           price, quantity, fee, legacy_trade=None):
        """Atomically record logical order, fill and reconstructed position.

        Replaying the same intent/fill is a no-op. Any failed invariant rolls
        back all journal rows. This method never calls an exchange API.
        """
        price, quantity, fee = float(price), float(quantity), float(fee)
        total = price * quantity
        if side.upper() != 'BUY':
            raise ValueError('record_dryrun_fill only accepts BUY; use record_dryrun_sell for SELL')
        if not all(math.isfinite(v) for v in (price, quantity, total, fee)) or price <= 0 or quantity <= 0 or total <= 0 or fee < 0:
            raise ValueError("invalid dry-run fill invariant")
        payload = intent.to_dict() if hasattr(intent, "to_dict") else dict(intent)
        with self.get_connection() as conn:
            self._ensure_virtual_cash_account(conn, user_id)
            conn.execute('''
                INSERT OR IGNORE INTO autotrade_intents
                (idempotency_key, correlation_id, version, pair, recommendation,
                 signal_json, user_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, datetime(?, 'unixepoch'))
            ''', (payload['idempotency_key'], payload['correlation_id'], payload.get('version', 1), pair,
                  payload['recommendation'], json.dumps(payload['signal'], sort_keys=True, default=str), user_id,
                  payload['created_at']))
            intent_row = conn.execute('SELECT * FROM autotrade_intents WHERE idempotency_key=?',
                                      (payload['idempotency_key'],)).fetchone()
            conn.execute('''INSERT OR IGNORE INTO autotrade_orders
                (intent_id, order_id, pair, user_id, side, order_type, limit_price, quantity, total, status)
                VALUES (?, ?, ?, ?, ?, 'DRY_RUN', ?, ?, ?, 'FILLED')''',
                (intent_row['id'], order_id, pair, user_id, side, price, quantity, total))
            order = conn.execute('SELECT * FROM autotrade_orders WHERE intent_id=?', (intent_row['id'],)).fetchone()
            fill_key = f"{payload['idempotency_key']}:fill"
            inserted = conn.execute('''INSERT OR IGNORE INTO autotrade_fills
                (order_id, fill_key, price, quantity, total, fee) VALUES (?, ?, ?, ?, ?, ?)''',
                (order['id'], fill_key, price, quantity, total, fee)).rowcount
            if inserted:
                self._apply_virtual_cash_fill(conn, user_id, side, total, fee)
                existing = conn.execute('SELECT * FROM autotrade_positions WHERE pair=? AND user_id=?',
                                        (pair, user_id)).fetchone()
                old_qty = float(existing['quantity']) if existing else 0.0
                old_cost = float(existing['cost_basis']) if existing else 0.0
                old_fees = float(existing['fees']) if existing else 0.0
                new_qty, new_cost = old_qty + quantity, old_cost + total
                conn.execute('''INSERT INTO autotrade_positions
                    (pair,user_id,quantity,avg_price,cost_basis,fees,status)
                    VALUES (?,?,?,?,?,?,'OPEN')
                    ON CONFLICT(pair,user_id) DO UPDATE SET quantity=excluded.quantity,
                    avg_price=excluded.avg_price,cost_basis=excluded.cost_basis,
                    fees=excluded.fees,status='OPEN',updated_at=CURRENT_TIMESTAMP''',
                    (pair, user_id, new_qty, new_cost/new_qty, new_cost, old_fees+fee))
            conn.execute("UPDATE autotrade_orders SET status='FILLED' WHERE id=?", (order['id'],))
            conn.execute("UPDATE autotrade_intents SET status='FILLED', reason_code='DRYRUN_FILL', updated_at=CURRENT_TIMESTAMP WHERE id=?", (intent_row['id'],))
            return {"intent_id": intent_row['id'], "order_id": order['id'], "inserted": bool(inserted),
                    "legacy_trade_id": legacy_trade}

    def create_atomic_dryrun_fill(self, *, intent, user_id, order_id, pair, price,
                                  quantity, fee, confidence, notes, inject_failure=False):
        """Create legacy trade and normalized BUY fill in one transaction."""
        price, quantity, fee = float(price), float(quantity), float(fee)
        if not all(math.isfinite(v) for v in (price,quantity,fee)) or price <= 0 or quantity <= 0 or fee < 0:
            raise ValueError("invalid fill")
        payload = intent.to_dict() if hasattr(intent, 'to_dict') else dict(intent)
        total = price * quantity
        with self.get_connection() as conn:
            self._ensure_virtual_cash_account(conn, user_id)
            inserted=conn.execute('''INSERT OR IGNORE INTO autotrade_intents
                (idempotency_key,correlation_id,version,pair,recommendation,signal_json,user_id,created_at)
                VALUES(?,?,?,?,?,?,?,datetime(?,'unixepoch'))''',(payload['idempotency_key'],payload['correlation_id'],payload.get('version',1),pair,payload['recommendation'],json.dumps(payload['signal'],sort_keys=True,default=str),user_id,payload['created_at'])).rowcount
            intent_row=conn.execute('SELECT * FROM autotrade_intents WHERE idempotency_key=?',(payload['idempotency_key'],)).fetchone()
            if not inserted and intent_row['status']=='FILLED': return intent_row['legacy_trade_id']
            cur = conn.execute('''INSERT INTO trades(user_id,pair,type,price,amount,total,fee,signal_source,ml_confidence,status,original_total,notes)
                VALUES(?,?, 'BUY',?,?,?,?, 'auto',?,'OPEN',?,?)''',
                (user_id,pair,price,quantity,total,fee,confidence,total,notes))
            trade_id = cur.lastrowid
            if inject_failure:
                raise RuntimeError("injected atomic fill failure")
            intent_id=conn.execute('SELECT id FROM autotrade_intents WHERE idempotency_key=?',(payload['idempotency_key'],)).fetchone()[0]
            conn.execute("INSERT INTO autotrade_orders(intent_id,order_id,pair,user_id,side,order_type,limit_price,quantity,total,status) VALUES(?,?,?,?,'BUY','DRY_RUN',?,?,?,'FILLED')",(intent_id,order_id,pair,user_id,price,quantity,total))
            oid=conn.execute('SELECT id FROM autotrade_orders WHERE intent_id=?',(intent_id,)).fetchone()[0]
            conn.execute('INSERT INTO autotrade_fills(order_id,fill_key,price,quantity,total,fee) VALUES(?,?,?,?,?,?)',(oid,f"{payload['idempotency_key']}:fill",price,quantity,total,fee))
            self._apply_virtual_cash_fill(conn, user_id, 'BUY', total, fee)
            conn.execute('''INSERT INTO autotrade_positions(pair,user_id,quantity,avg_price,cost_basis,fees,status) VALUES(?,?,?,?,?,?,'OPEN')
                ON CONFLICT(pair,user_id) DO UPDATE SET quantity=quantity+excluded.quantity,cost_basis=cost_basis+excluded.cost_basis,
                avg_price=(cost_basis+excluded.cost_basis)/(quantity+excluded.quantity),fees=fees+excluded.fees,status='OPEN' ''',(pair,user_id,quantity,price,total,fee))
            conn.execute("UPDATE autotrade_intents SET status='FILLED',reason_code='DRYRUN_FILL',legacy_trade_id=? WHERE id=?",(trade_id,intent_id))
            return trade_id

    def create_atomic_dryrun_pending(self, *, intent, user_id, order_id, pair,
                                     limit_price, quantity, notes, inject_failure=False):
        payload=intent.to_dict() if hasattr(intent,'to_dict') else dict(intent)
        limit_price,quantity=float(limit_price),float(quantity)
        if not all(math.isfinite(v) for v in (limit_price,quantity)) or min(limit_price,quantity)<=0: raise ValueError("invalid pending")
        total=limit_price*quantity
        with self.get_connection() as conn:
            self._ensure_virtual_cash_account(conn, user_id)
            existing=conn.execute('SELECT id FROM autotrade_intents WHERE idempotency_key=?',(payload['idempotency_key'],)).fetchone()
            if existing:
                row=conn.execute('SELECT id FROM pending_orders WHERE order_id=?',(order_id,)).fetchone()
                normalized=conn.execute('SELECT id FROM autotrade_orders WHERE intent_id=?',(existing['id'],)).fetchone()
                if row and normalized: return row[0]
            conn.execute('''INSERT INTO pending_orders(order_id,pair,user_id,trade_type,limit_price,amount,total,notes)
                VALUES(?,?,?,'BUY',?,?,?,?)''',(order_id,pair,user_id,limit_price,quantity,total,notes))
            if inject_failure: raise RuntimeError("injected atomic pending failure")
            conn.execute('''INSERT OR IGNORE INTO autotrade_intents(idempotency_key,correlation_id,version,pair,recommendation,signal_json,user_id,status,reason_code,created_at)
                VALUES(?,?,?,?,?,?,?,'PENDING','DRYRUN_LIMIT_PENDING',datetime(?,'unixepoch'))''',(payload['idempotency_key'],payload['correlation_id'],payload.get('version',1),pair,payload['recommendation'],json.dumps(payload['signal'],sort_keys=True,default=str),user_id,payload['created_at']))
            iid=conn.execute('SELECT id FROM autotrade_intents WHERE idempotency_key=?',(payload['idempotency_key'],)).fetchone()[0]
            conn.execute("UPDATE autotrade_intents SET status='PENDING',reason_code='DRYRUN_LIMIT_PENDING' WHERE id=?",(iid,))
            conn.execute("INSERT INTO autotrade_orders(intent_id,order_id,pair,user_id,side,order_type,limit_price,quantity,total,status) VALUES(?,?,?,?,'BUY','DRY_RUN_LIMIT',?,?,?,'PENDING')",(iid,order_id,pair,user_id,limit_price,quantity,total))
            return conn.execute('SELECT id FROM pending_orders WHERE order_id=?',(order_id,)).fetchone()[0]

    def promote_atomic_dryrun_pending(self, *, pending_db_id, order_id, user_id,
                                      fill_price, fee, confidence, notes, inject_failure=False):
        """Legacy trade + both pending states + normalized fill atomically."""
        fill_price, fee = float(fill_price), float(fee)
        if not all(math.isfinite(v) for v in (fill_price, fee)) or fill_price <= 0 or fee < 0:
            raise ValueError('invalid pending promotion')
        with self.get_connection() as conn:
            self._ensure_virtual_cash_account(conn, user_id)
            pending=conn.execute("SELECT * FROM pending_orders WHERE id=? AND status='PENDING'",(pending_db_id,)).fetchone()
            order=conn.execute("SELECT * FROM autotrade_orders WHERE order_id=? AND status='PENDING'",(order_id,)).fetchone()
            if not pending or not order: return None
            if (str(pending['order_id']) != str(order_id) or pending['user_id'] != user_id
                    or order['user_id'] != user_id or order['pair'] != pending['pair']):
                raise ValueError('pending promotion ownership mismatch')
            qty=float(pending['amount']); total=float(fill_price)*qty
            trade_id=conn.execute('''INSERT INTO trades(user_id,pair,type,price,amount,total,fee,signal_source,ml_confidence,status,original_total,notes)
                VALUES(?,?, 'BUY',?,?,?,?, 'auto',?,'OPEN',?,?)''',(user_id,pending['pair'],fill_price,qty,total,fee,confidence,total,notes)).lastrowid
            if inject_failure: raise RuntimeError("injected promotion failure")
            conn.execute("UPDATE pending_orders SET status='FILLED',filled_at=CURRENT_TIMESTAMP,fill_price=?,trade_id=?,notes=? WHERE id=? AND status='PENDING'",(fill_price,trade_id,notes,pending_db_id))
            conn.execute("UPDATE autotrade_orders SET status='FILLED' WHERE id=? AND status='PENDING'",(order['id'],))
            intent=conn.execute('SELECT * FROM autotrade_intents WHERE id=?',(order['intent_id'],)).fetchone()
            conn.execute('INSERT INTO autotrade_fills(order_id,fill_key,price,quantity,total,fee) VALUES(?,?,?,?,?,?)',(order['id'],f"{intent['idempotency_key']}:fill",fill_price,qty,total,fee))
            self._apply_virtual_cash_fill(conn, user_id, 'BUY', total, fee)
            conn.execute('''INSERT INTO autotrade_positions(pair,user_id,quantity,avg_price,cost_basis,fees,status) VALUES(?,?,?,?,?,?,'OPEN')
                ON CONFLICT(pair,user_id) DO UPDATE SET quantity=quantity+excluded.quantity,cost_basis=cost_basis+excluded.cost_basis,
                avg_price=(cost_basis+excluded.cost_basis)/(quantity+excluded.quantity),fees=fees+excluded.fees,status='OPEN' ''',(pending['pair'],user_id,qty,fill_price,total,fee))
            conn.execute("UPDATE autotrade_intents SET status='FILLED',reason_code='DRYRUN_FILL' WHERE id=?",(order['intent_id'],))
            return trade_id

    def get_autotrade_position(self, pair, user_id):
        pair_key = str(pair).replace('/', '').replace('_', '').lower()
        with self.get_connection() as conn:
            return conn.execute('''
                SELECT * FROM autotrade_positions
                WHERE lower(replace(replace(pair, '/', ''), '_', ''))=? AND user_id=?
            ''', (pair_key, user_id)).fetchone()

    def get_open_autotrade_positions(self, user_id):
        """Return canonical normalized positions that still carry inventory."""
        with self.get_connection() as conn:
            return conn.execute('''
                SELECT * FROM autotrade_positions
                WHERE user_id=? AND status='OPEN' AND quantity>1e-12
                ORDER BY pair
            ''', (user_id,)).fetchall()

    def get_all_open_autotrade_positions(self):
        """Return every normalized position requiring mark-to-market monitoring."""
        with self.get_connection() as conn:
            return conn.execute('''
                SELECT * FROM autotrade_positions
                WHERE status='OPEN' AND quantity>1e-12
                ORDER BY user_id, pair
            ''').fetchall()

    def audit_autotrade_projection_drift(self, user_id):
        """Read-only comparison of legacy and normalized open-position state."""
        with self.get_connection() as conn:
            legacy_rows = conn.execute('''
                SELECT lower(replace(replace(pair, '/', ''), '_', '')) AS pair,
                       COUNT(*) AS open_count,
                       COALESCE(SUM(amount), 0) AS quantity
                FROM trades
                WHERE user_id=? AND signal_source='auto' AND status='OPEN'
                GROUP BY lower(replace(replace(pair, '/', ''), '_', ''))
            ''', (user_id,)).fetchall()
            normalized_rows = conn.execute('''
                SELECT lower(replace(replace(pair, '/', ''), '_', '')) AS pair,
                       quantity, cost_basis, fees
                FROM autotrade_positions
                WHERE user_id=? AND status='OPEN' AND quantity>1e-12
            ''', (user_id,)).fetchall()
            balance_row = conn.execute(
                'SELECT balance FROM users WHERE user_id=?', (user_id,)
            ).fetchone()
            peak_row = conn.execute(
                'SELECT equity_peak FROM drawdown_state WHERE user_id=?', (user_id,)
            ).fetchone()

        legacy = {row['pair']: dict(row) for row in legacy_rows}
        normalized = {row['pair']: dict(row) for row in normalized_rows}
        mismatches = []
        for pair in sorted(set(legacy) | set(normalized)):
            legacy_open = pair in legacy
            normalized_open = pair in normalized
            legacy_qty = float(legacy.get(pair, {}).get('quantity') or 0)
            normalized_qty = float(normalized.get(pair, {}).get('quantity') or 0)
            if legacy_open != normalized_open or not math.isclose(
                legacy_qty, normalized_qty, rel_tol=1e-9, abs_tol=1e-12
            ):
                mismatches.append({
                    'pair': pair,
                    'legacy_open': legacy_open,
                    'legacy_quantity': legacy_qty,
                    'normalized_open': normalized_open,
                    'normalized_quantity': normalized_qty,
                })
        return {
            'user_id': user_id,
            'cash': float(balance_row['balance']) if balance_row else None,
            'equity_peak': float(peak_row['equity_peak']) if peak_row else None,
            'legacy_open_count': len(legacy),
            'normalized_open_count': len(normalized),
            'normalized_open_cost_basis': sum(
                float(row['cost_basis']) for row in normalized.values()
            ),
            'mismatches': mismatches,
        }

    def record_dryrun_pending(self, *, intent, user_id, order_id, pair, side,
                              limit_price, quantity):
        """Atomically journal a deferred simulated order (idempotent)."""
        price, quantity = float(limit_price), float(quantity)
        if price <= 0 or quantity <= 0:
            raise ValueError("invalid dry-run pending invariant")
        payload = intent.to_dict() if hasattr(intent, "to_dict") else dict(intent)
        with self.get_connection() as conn:
            conn.execute('''INSERT OR IGNORE INTO autotrade_intents
                (idempotency_key,correlation_id,version,pair,recommendation,signal_json,user_id,created_at)
                VALUES (?,?,?,?,?,?,?,datetime(?,'unixepoch'))''',
                (payload['idempotency_key'], payload['correlation_id'], payload.get('version', 1), pair,
                 payload['recommendation'], json.dumps(payload['signal'], sort_keys=True, default=str), user_id,
                 payload['created_at']))
            row = conn.execute('SELECT * FROM autotrade_intents WHERE idempotency_key=?',
                               (payload['idempotency_key'],)).fetchone()
            conn.execute('''INSERT OR IGNORE INTO autotrade_orders
                (intent_id,order_id,pair,user_id,side,order_type,limit_price,quantity,total,status)
                VALUES (?,?,?,?,?, 'DRY_RUN_LIMIT',?,?,?,'PENDING')''',
                (row['id'], order_id, pair, user_id, side, price, quantity, price*quantity))
            conn.execute("UPDATE autotrade_intents SET status='PENDING',reason_code='DRYRUN_LIMIT_PENDING',updated_at=CURRENT_TIMESTAMP WHERE id=?", (row['id'],))
            return conn.execute('SELECT * FROM autotrade_orders WHERE intent_id=?', (row['id'],)).fetchone()

    def promote_dryrun_pending_fill(self, *, order_id, user_id, price, fee, legacy_trade=None):
        """Promote an existing normalized pending order to a fill/position."""
        with self.get_connection() as conn:
            order = conn.execute("SELECT * FROM autotrade_orders WHERE order_id=? AND status='PENDING'", (order_id,)).fetchone()
            if not order:
                return None
            intent = conn.execute('SELECT * FROM autotrade_intents WHERE id=?', (order['intent_id'],)).fetchone()
        payload = dict(intent)
        payload['signal'] = json.loads(payload.pop('signal_json'))
        return self.record_dryrun_fill(intent=payload, user_id=user_id, order_id=order_id,
            pair=order['pair'], side=order['side'], price=price,
            quantity=order['quantity'], fee=fee, legacy_trade=legacy_trade)

    def record_dryrun_sell(self, *, fill_key, order_id, pair, user_id, price, quantity, fee):
        """Idempotently decrement/close a normalized dry-run position."""
        price, quantity, fee = float(price), float(quantity), float(fee)
        if not all(math.isfinite(v) for v in (price,quantity,fee)) or min(price, quantity) <= 0 or fee < 0 or fee > price*quantity:
            raise ValueError("invalid sell invariant")
        with self.get_connection() as conn:
            self._ensure_virtual_cash_account(conn, user_id)
            pair_key = str(pair).replace('/', '').replace('_', '').lower()
            pos = conn.execute('''SELECT * FROM autotrade_positions
                WHERE lower(replace(replace(pair, '/', ''), '_', ''))=? AND user_id=?''',
                (pair_key, user_id)).fetchone()
            if not pos or quantity > float(pos['quantity']) + 1e-12:
                raise ValueError("sell exceeds open position")
            exists = conn.execute('SELECT 1 FROM autotrade_fills WHERE fill_key=?', (fill_key,)).fetchone()
            if exists:
                return False
            # Synthetic sell intent/order keeps the normalized journal complete.
            key = f"sell:{fill_key}"
            conn.execute("INSERT INTO autotrade_intents(idempotency_key,correlation_id,version,pair,recommendation,signal_json,user_id,status,reason_code,created_at) VALUES(?,?,1,?,'SELL','{}',?,'FILLED','DRYRUN_SELL_FILL',CURRENT_TIMESTAMP)", (key,key,pair,user_id))
            iid = conn.execute('SELECT id FROM autotrade_intents WHERE idempotency_key=?',(key,)).fetchone()[0]
            conn.execute("INSERT INTO autotrade_orders(intent_id,order_id,pair,user_id,side,order_type,limit_price,quantity,total,status) VALUES(?,?,?,?,'SELL','DRY_RUN',?,?,?,'FILLED')",(iid,order_id,pair,user_id,price,quantity,price*quantity))
            oid=conn.execute('SELECT id FROM autotrade_orders WHERE intent_id=?',(iid,)).fetchone()[0]
            conn.execute('INSERT INTO autotrade_fills(order_id,fill_key,price,quantity,total,fee) VALUES(?,?,?,?,?,?)',(oid,fill_key,price,quantity,price*quantity,fee))
            self._apply_virtual_cash_fill(conn, user_id, 'SELL', price*quantity, fee)
            remain=max(0.0,float(pos['quantity'])-quantity)
            basis=float(pos['cost_basis']) * (remain/float(pos['quantity'])) if remain else 0
            conn.execute("UPDATE autotrade_positions SET quantity=?,cost_basis=?,avg_price=?,fees=fees+?,status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(remain,basis,(basis/remain if remain else 0),fee,('OPEN' if remain else 'CLOSED'),pos['id']))
            return True

    def close_atomic_dryrun_position(self, *, trade_id, fill_key, order_id, pair,
                                     user_id, sell_price, quantity, fee, reason,
                                     pnl, pnl_pct, inject_failure=False):
        """Atomically close legacy trade quantity and normalized position."""
        sell_price,quantity,fee=float(sell_price),float(quantity),float(fee)
        if not all(math.isfinite(v) for v in (sell_price,quantity,fee,pnl,pnl_pct)) or min(sell_price,quantity)<=0 or fee<0 or fee>sell_price*quantity:
            raise ValueError("invalid atomic sell")
        with self.get_connection() as conn:
            self._ensure_virtual_cash_account(conn, user_id)
            legacy=conn.execute("SELECT * FROM trades WHERE id=? AND status='OPEN'",(trade_id,)).fetchone()
            pair_key = str(pair).replace('/', '').replace('_', '').lower()
            pos=conn.execute('''SELECT * FROM autotrade_positions
                WHERE lower(replace(replace(pair, '/', ''), '_', ''))=?
                  AND user_id=? AND status='OPEN' ''',(pair_key,user_id)).fetchone()
            if not legacy or not pos: return False
            legacy_pair_key = str(legacy['pair']).replace('/', '').replace('_', '').lower()
            if legacy['user_id'] != user_id or legacy_pair_key != pair_key:
                raise ValueError('legacy trade ownership mismatch')
            if quantity>float(pos['quantity'])+1e-12: raise ValueError("sell exceeds normalized position")
            if conn.execute('SELECT 1 FROM autotrade_fills WHERE fill_key=?',(fill_key,)).fetchone(): return False
            remain=max(0.0,float(legacy['amount'])-quantity)
            legacy_status='OPEN' if remain>1e-12 else 'CLOSED'
            conn.execute('''UPDATE trades SET amount=?,total=?,status=?,closed_at=CASE WHEN ?='CLOSED' THEN CURRENT_TIMESTAMP ELSE closed_at END,
                profit_loss=?,profit_loss_pct=?,realized_profit_loss=COALESCE(realized_profit_loss,0)+?,notes=COALESCE(notes,'')||' | '||? WHERE id=?''',
                (remain,remain*float(legacy['price']),legacy_status,legacy_status,pnl,pnl_pct,pnl,reason,trade_id))
            if inject_failure: raise RuntimeError("injected atomic sell failure")
            key=f"sell:{fill_key}"
            conn.execute("INSERT INTO autotrade_intents(idempotency_key,correlation_id,version,pair,recommendation,signal_json,user_id,status,reason_code,created_at,legacy_trade_id) VALUES(?,?,1,?,'SELL','{}',?,'FILLED','DRYRUN_SELL_FILL',CURRENT_TIMESTAMP,?)",(key,key,pair,user_id,trade_id))
            iid=conn.execute('SELECT id FROM autotrade_intents WHERE idempotency_key=?',(key,)).fetchone()[0]
            conn.execute("INSERT INTO autotrade_orders(intent_id,order_id,pair,user_id,side,order_type,limit_price,quantity,total,status) VALUES(?,?,?,?,'SELL','DRY_RUN',?,?,?,'FILLED')",(iid,order_id,pair,user_id,sell_price,quantity,sell_price*quantity))
            oid=conn.execute('SELECT id FROM autotrade_orders WHERE intent_id=?',(iid,)).fetchone()[0]
            conn.execute('INSERT INTO autotrade_fills(order_id,fill_key,price,quantity,total,fee) VALUES(?,?,?,?,?,?)',(oid,fill_key,sell_price,quantity,sell_price*quantity,fee))
            self._apply_virtual_cash_fill(conn, user_id, 'SELL', sell_price*quantity, fee)
            premain=max(0.0,float(pos['quantity'])-quantity); basis=float(pos['cost_basis'])*(premain/float(pos['quantity'])) if premain else 0
            conn.execute("UPDATE autotrade_positions SET quantity=?,cost_basis=?,avg_price=?,fees=fees+?,status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(premain,basis,basis/premain if premain else 0,fee,'OPEN' if premain>1e-12 else 'CLOSED',pos['id']))
            return True

    def rebuild_autotrade_position(self, pair, user_id):
        """Return persisted projection after validating it against ordered fills."""
        with self.get_connection() as conn:
            rows=conn.execute('''SELECT o.side,f.quantity,f.total,f.fee FROM autotrade_fills f
                JOIN autotrade_orders o ON o.id=f.order_id WHERE o.pair=? AND o.user_id=? ORDER BY f.id''',(pair,user_id)).fetchall()
            qty=cost=fees=0.0
            for row in rows:
                if row['side']=='BUY': qty+=row['quantity']; cost+=row['total']
                else:
                    sold=min(qty,row['quantity']); cost*=((qty-sold)/qty) if qty else 0; qty-=sold
                fees+=row['fee']
            status='OPEN' if qty>0 else 'CLOSED'
            conn.execute('''INSERT INTO autotrade_positions(pair,user_id,quantity,avg_price,cost_basis,fees,status)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(pair,user_id) DO UPDATE SET quantity=excluded.quantity,avg_price=excluded.avg_price,cost_basis=excluded.cost_basis,fees=excluded.fees,status=excluded.status''',(pair,user_id,qty,cost/qty if qty else 0,cost,fees,status))
            return conn.execute('SELECT * FROM autotrade_positions WHERE pair=? AND user_id=?',(pair,user_id)).fetchone()

    def get_pending_orders(self, pair=None, status='PENDING', user_id=None):
        """Get pending limit orders."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if pair and user_id is not None:
                cursor.execute('SELECT * FROM pending_orders WHERE pair=? AND user_id=? AND status=? ORDER BY placed_at ASC',(pair,user_id,status))
            elif pair:
                cursor.execute('''
                    SELECT * FROM pending_orders WHERE pair = ? AND status = ? ORDER BY placed_at ASC
                ''', (pair, status))
            else:
                cursor.execute('''
                    SELECT * FROM pending_orders WHERE status = ? ORDER BY placed_at ASC
                ''', (status,))
            return cursor.fetchall()

    def update_pending_order_filled(self, db_id, fill_price, notes=None, trade_id=None):
        """Mark pending order as filled."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE pending_orders
                SET status = 'FILLED', filled_at = CURRENT_TIMESTAMP, fill_price = ?, notes = COALESCE(?, notes), trade_id = COALESCE(?, trade_id)
                WHERE id = ?
            ''', (fill_price, notes, trade_id, db_id))

    def update_pending_order_cancelled(self, db_id, notes=None, reason_code='PENDING_CANCELLED'):
        """Atomically cancel legacy pending, normalized order, and its intent."""
        with self.get_connection() as conn:
            pending = conn.execute('SELECT * FROM pending_orders WHERE id=?', (db_id,)).fetchone()
            if not pending:
                raise ValueError(f'pending order not found: {db_id}')
            if pending['status'] != 'PENDING':
                return False
            normalized = conn.execute(
                "SELECT * FROM autotrade_orders WHERE order_id=? AND user_id=? AND status='PENDING'",
                (pending['order_id'], pending['user_id']),
            ).fetchone()
            if not normalized:
                raise RuntimeError('normalized pending order missing or non-pending')
            intent = conn.execute(
                "SELECT * FROM autotrade_intents WHERE id=? AND status='PENDING'",
                (normalized['intent_id'],),
            ).fetchone()
            if not intent:
                raise RuntimeError('normalized pending intent missing or non-pending')
            conn.execute('''UPDATE pending_orders SET status='CANCELLED',
                cancelled_at=CURRENT_TIMESTAMP,notes=COALESCE(?,notes) WHERE id=?''', (notes, db_id))
            conn.execute("UPDATE autotrade_orders SET status='CANCELLED' WHERE id=?", (normalized['id'],))
            conn.execute('''UPDATE autotrade_intents SET status='NO_ENTRY',reason_code=?,reason=?,
                updated_at=CURRENT_TIMESTAMP WHERE id=?''', (reason_code, notes or '', normalized['intent_id']))
            return True

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

    def set_watchlist_active(self, user_id: int, pair: str, is_active: bool = True):
        """Set active/inactive status for a pair in user's watchlist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE watchlist SET is_active = ?
                WHERE user_id = ? AND pair = ?
            ''', (1 if is_active else 0, user_id, pair.lower().strip()))
            return cursor.rowcount > 0

    def bulk_upsert_watchlist(self, user_id: int, pairs: list):
        """Bulk insert/update active pairs for a user, deactivating all others first.
        
        This is atomic: all existing pairs for this user are set inactive,
        then the provided pairs are upserted with is_active=1.
        Returns (deactivated_count, activated_count).
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Count and deactivate all current active pairs
            cursor.execute('''
                SELECT COUNT(*) as cnt FROM watchlist
                WHERE user_id = ? AND is_active = 1
            ''', (user_id,))
            deactivated = cursor.fetchone()['cnt']
            
            cursor.execute('''
                UPDATE watchlist SET is_active = 0
                WHERE user_id = ?
            ''', (user_id,))
            
            # Ensure user exists in telegram_users to prevent foreign key constraint failures
            cursor.execute('''
                INSERT INTO telegram_users (user_id, role, is_active)
                VALUES (?, 'admin', 1)
                ON CONFLICT(user_id) DO NOTHING
            ''', (user_id,))

            # Upsert new pairs as active
            activated = 0
            for pair in pairs:
                pair_clean = pair.lower().strip()
                cursor.execute('''
                    INSERT INTO watchlist (user_id, pair, is_active)
                    VALUES (?, ?, 1)
                    ON CONFLICT(user_id, pair) DO UPDATE SET is_active = 1
                ''', (user_id, pair_clean))
                activated += 1
            
            logger.info(
                "🔄 Watchlist bulk refresh: %d deactivated, %d activated for user %d",
                deactivated, activated, user_id
            )
            return deactivated, activated

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

    def set_auto_trade_mode(self, is_dry_run):
        """Persist auto-trade mode (dry-run or real) to database."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO app_settings (key, value)
                VALUES ('auto_trade_dry_run', ?)
            ''', (str(bool(is_dry_run)).lower(),))

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

    def reconcile_closed_dryrun_cash(self, user_id, pre_fill_baseline_cash):
        """Rebuild virtual cash from normalized fills when every position is closed.

        This fail-closed migration is deterministic and idempotent. It refuses
        to guess a cash value while either ledger still reports an open trade.
        """
        baseline_cash = float(pre_fill_baseline_cash)
        if not math.isfinite(baseline_cash) or baseline_cash < 0:
            raise ValueError('invalid dry-run baseline cash')
        with self.get_connection() as conn:
            legacy_open = conn.execute(
                "SELECT COUNT(*) FROM trades WHERE user_id=? AND status='OPEN'", (user_id,)
            ).fetchone()[0]
            normalized_open = conn.execute(
                "SELECT COUNT(*) FROM autotrade_positions WHERE user_id=? AND status='OPEN' AND quantity>1e-12",
                (user_id,),
            ).fetchone()[0]
            if legacy_open or normalized_open:
                raise RuntimeError(
                    f'cash reconciliation refused: legacy_open={legacy_open}, normalized_open={normalized_open}'
                )
            uncovered_legacy = conn.execute('''
                SELECT COUNT(*) FROM trades t
                WHERE t.user_id=? AND t.signal_source='auto' AND t.status='CLOSED'
                  AND NOT EXISTS (
                    SELECT 1 FROM autotrade_intents i WHERE i.legacy_trade_id=t.id
                  )
            ''', (user_id,)).fetchone()[0]
            if uncovered_legacy:
                raise RuntimeError(f'cash reconciliation refused: uncovered_legacy={uncovered_legacy}')
            rows = conn.execute('''
                SELECT o.side, f.total, f.fee
                FROM autotrade_fills f
                JOIN autotrade_orders o ON o.id=f.order_id
                WHERE o.user_id=? ORDER BY f.id
            ''', (user_id,)).fetchall()
            cash = baseline_cash
            for row in rows:
                if row['side'] == 'BUY':
                    cash -= float(row['total']) + float(row['fee'])
                elif row['side'] == 'SELL':
                    cash += float(row['total']) - float(row['fee'])
                else:
                    raise RuntimeError(f"unknown fill side: {row['side']}")
            if not math.isfinite(cash) or cash < 0:
                raise RuntimeError(f'cash reconciliation produced invalid cash: {cash}')
            self._ensure_virtual_cash_account(conn, user_id)
            conn.execute('UPDATE users SET balance=? WHERE user_id=?', (cash, user_id))
            conn.execute('''
                INSERT INTO drawdown_state(user_id,equity_peak,last_updated)
                VALUES(?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET equity_peak=excluded.equity_peak,
                    last_updated=CURRENT_TIMESTAMP
            ''', (user_id, cash))
            return {'cash': cash, 'equity_peak': cash, 'fill_count': len(rows)}

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
