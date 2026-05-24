# Tujuan: Core engine untuk adaptive learning — bot belajar dari hasil trade.
# Caller: analysis.nightly_analyzer, bot.py (saat close_trade), signals.signal_pipeline.
# Dependensi: core.config, core.database, analysis.ml_model_v4.
# Main Functions: AdaptiveLearningEngine.
# Side Effects: DB read/write untuk adaptive_thresholds, trade outcomes.

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import json

from core.config import Config

logger = logging.getLogger('crypto_bot')


@dataclass
class PairPerformanceMetrics:
    """Metrics untuk satu pair berdasarkan hasil trade historis."""
    pair: str
    total_trades: int
    win_count: int
    loss_count: int
    win_rate: float
    profit_factor: float
    avg_profit_pct: float
    avg_loss_pct: float
    best_confidence_win: float
    worst_confidence_loss: float
    optimal_confidence_threshold: float
    optimal_rr_threshold: float
    last_updated: datetime


class AdaptiveLearningEngine:
    """
    Engine untuk adaptive learning.
    
    Fungsi utama:
    1. Analisis hasil trade per pair → update optimal thresholds
    2. Generate V4 training labels dari trade outcomes nyata
    3. Track market regime history
    4. Pair performance ranking (untuk skip list)
    """

    def __init__(self, db):
        self.db = db
        self._ensure_tables()

    def _ensure_tables(self):
        """Pastikan tabel adaptive learning ada di DB."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Adaptive thresholds per pair
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
            
            # Market regime history
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
            
            # Trade outcomes untuk V4 training (labelled by actual results)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trade_outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id INTEGER,
                    pair TEXT NOT NULL,
                    signal_price REAL,
                    entry_price REAL,
                    exit_price REAL,
                    ml_confidence REAL,
                    v4_prediction TEXT,
                    v4_confidence REAL,
                    recommendation TEXT,
                    pnl_pct REAL,
                    hold_duration_minutes INTEGER,
                    outcome_label TEXT,  -- GOOD_BUY, BAD_BUY, GOOD_SELL, BAD_SELL
                    market_regime TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (trade_id) REFERENCES trades(id)
                )
            ''')
            
            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_regime_pair ON regime_history(pair, started_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_outcomes_pair ON trade_outcomes(pair, created_at)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_outcomes_label ON trade_outcomes(outcome_label)')

    def analyze_pair_performance(self, pair: str, days: int = 7) -> Optional[PairPerformanceMetrics]:
        """
        Analisis performa trade untuk satu pair dalam N hari terakhir.
        
        Returns:
            PairPerformanceMetrics atau None jika tidak ada data.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cutoff = datetime.now() - timedelta(days=days)
            
            cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN profit_loss_pct > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN profit_loss_pct <= 0 THEN 1 ELSE 0 END) as losses,
                    AVG(CASE WHEN profit_loss_pct > 0 THEN profit_loss_pct END) as avg_profit,
                    AVG(CASE WHEN profit_loss_pct <= 0 THEN profit_loss_pct END) as avg_loss,
                    MAX(CASE WHEN profit_loss_pct > 0 THEN ml_confidence END) as best_conf_win,
                    MIN(CASE WHEN profit_loss_pct <= 0 THEN ml_confidence END) as worst_conf_loss
                FROM trades
                WHERE pair = ? AND status = 'CLOSED' AND closed_at >= ?
            ''', (pair, cutoff))
            
            row = cursor.fetchone()
            if not row or row['total'] == 0:
                return None
            
            total = row['total'] or 0
            wins = row['wins'] or 0
            losses = row['losses'] or 0
            win_rate = wins / total if total > 0 else 0
            
            # Profit factor
            cursor.execute('''
                SELECT 
                    SUM(CASE WHEN profit_loss_pct > 0 THEN profit_loss_pct ELSE 0 END) as total_profit,
                    SUM(CASE WHEN profit_loss_pct <= 0 THEN ABS(profit_loss_pct) ELSE 0 END) as total_loss
                FROM trades
                WHERE pair = ? AND status = 'CLOSED' AND closed_at >= ?
            ''', (pair, cutoff))
            
            pf_row = cursor.fetchone()
            total_profit = pf_row['total_profit'] or 0
            total_loss = pf_row['total_loss'] or 0
            profit_factor = total_profit / total_loss if total_loss > 0 else (float('inf') if total_profit > 0 else 0)
            
            # Optimal confidence threshold (median confidence of winning trades)
            optimal_conf = self._calculate_optimal_confidence(cursor, pair, cutoff)
            optimal_rr = self._calculate_optimal_rr(cursor, pair, cutoff)
            
            return PairPerformanceMetrics(
                pair=pair,
                total_trades=total,
                win_count=wins,
                loss_count=losses,
                win_rate=win_rate,
                profit_factor=profit_factor,
                avg_profit_pct=row['avg_profit'] or 0,
                avg_loss_pct=row['avg_loss'] or 0,
                best_confidence_win=row['best_conf_win'] or 0,
                worst_confidence_loss=row['worst_conf_loss'] or 0,
                optimal_confidence_threshold=optimal_conf,
                optimal_rr_threshold=optimal_rr,
                last_updated=datetime.now()
            )

    def _calculate_optimal_confidence(self, cursor, pair: str, cutoff: datetime) -> float:
        """Hitung confidence threshold optimal berdasarkan distribusi win/loss."""
        cursor.execute('''
            SELECT ml_confidence, profit_loss_pct
            FROM trades
            WHERE pair = ? AND status = 'CLOSED' AND closed_at >= ? AND ml_confidence IS NOT NULL
            ORDER BY ml_confidence
        ''', (pair, cutoff))
        
        rows = cursor.fetchall()
        if len(rows) < 5:
            return Config.CONFIDENCE_THRESHOLD
        
        # Find confidence level where win_rate >= 50%
        best_threshold = Config.CONFIDENCE_THRESHOLD
        best_score = 0
        all_losses = True  # Track if all trades are losses
        
        for row in rows:
            threshold = row['ml_confidence']
            wins_above = sum(1 for r in rows if r['ml_confidence'] >= threshold and r['profit_loss_pct'] > 0)
            total_above = sum(1 for r in rows if r['ml_confidence'] >= threshold)
            
            if wins_above > 0:
                all_losses = False
            
            if total_above >= 3:
                win_rate_above = wins_above / total_above
                # Score = win_rate * number_of_trades (prefer threshold dengan banyak sample)
                score = win_rate_above * total_above
                if score > best_score and win_rate_above >= 0.5:
                    best_score = score
                    best_threshold = threshold
        
        # FIX BUG #10: Handle edge case where all trades are losses
        if all_losses and best_score == 0:
            # Semua trade loss, naikkan threshold drastis untuk filter lebih ketat
            logger.warning(f"⚠️ [ADAPTIVE] {pair}: All {len(rows)} trades are losses, raising threshold to 0.85")
            best_threshold = 0.85
        
        # Clamp to reasonable range
        return max(0.50, min(0.85, best_threshold))

    def _calculate_optimal_rr(self, cursor, pair: str, cutoff: datetime) -> float:
        """Hitung RR ratio optimal berdasarkan hasil trade."""
        # NOTE: risk_reward_ratio column may not exist in all DB schemas.
        # Fallback to default if query fails.
        try:
            cursor.execute('''
                SELECT risk_reward_ratio, profit_loss_pct
                FROM trades
                WHERE pair = ? AND status = 'CLOSED' AND closed_at >= ? AND risk_reward_ratio IS NOT NULL AND risk_reward_ratio > 0
                ORDER BY risk_reward_ratio
            ''', (pair, cutoff))
            
            rows = cursor.fetchall()
            if len(rows) < 5:
                return Config.RISK_REWARD_RATIO
            
            # Find RR where win_rate >= 50%
            best_rr = Config.RISK_REWARD_RATIO
            best_score = 0
            
            for row in rows:
                rr = row['risk_reward_ratio']
                wins_above = sum(1 for r in rows if r['risk_reward_ratio'] >= rr and r['profit_loss_pct'] > 0)
                total_above = sum(1 for r in rows if r['risk_reward_ratio'] >= rr)
                
                if total_above >= 3:
                    win_rate_above = wins_above / total_above
                    score = win_rate_above * total_above
                    if score > best_score and win_rate_above >= 0.5:
                        best_score = score
                        best_rr = rr
            
            return max(1.0, min(3.0, best_rr))
        except Exception:
            return Config.RISK_REWARD_RATIO

    def update_adaptive_thresholds(self, metrics: PairPerformanceMetrics):
        """Update adaptive thresholds di DB berdasarkan metrics."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Determine if pair should be skipped
            should_skip = 0
            if metrics.total_trades >= 5 and metrics.profit_factor < 1.0:
                should_skip = 1
                logger.warning(f"🚫 [ADAPTIVE] Pair {metrics.pair} skipped: PF={metrics.profit_factor:.2f} < 1.0 over {metrics.total_trades} trades")
            
            # Adjust confidence thresholds
            buy_threshold = metrics.optimal_confidence_threshold
            strong_buy_threshold = min(0.90, buy_threshold + 0.15)
            
            # Position size multiplier based on win_rate
            if metrics.win_rate >= 0.60:
                pos_mult = 1.2
            elif metrics.win_rate >= 0.50:
                pos_mult = 1.0
            elif metrics.win_rate >= 0.40:
                pos_mult = 0.8
            else:
                pos_mult = 0.6
            
            cursor.execute('''
                INSERT OR REPLACE INTO adaptive_thresholds (
                    pair, confidence_threshold_buy, confidence_threshold_strong_buy,
                    min_rr_ratio, position_size_multiplier, skip_pair,
                    win_rate_7d, profit_factor_7d, total_trades_7d, last_analyzed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                metrics.pair, buy_threshold, strong_buy_threshold,
                metrics.optimal_rr_threshold, pos_mult, should_skip,
                metrics.win_rate, metrics.profit_factor, metrics.total_trades,
                datetime.now()
            ))
            
            logger.info(
                f"📊 [ADAPTIVE] {metrics.pair}: win_rate={metrics.win_rate:.1%}, "
                f"pf={metrics.profit_factor:.2f}, conf_threshold={buy_threshold:.2f}, "
                f"rr_threshold={metrics.optimal_rr_threshold:.2f}, pos_mult={pos_mult:.1f}, "
                f"skip={should_skip}"
            )

    def get_adaptive_thresholds(self, pair: str) -> Dict:
        """Get adaptive thresholds untuk satu pair."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM adaptive_thresholds WHERE pair = ?', (pair,))
            row = cursor.fetchone()
            
            if row:
                return {
                    'confidence_threshold_buy': row['confidence_threshold_buy'],
                    'confidence_threshold_strong_buy': row['confidence_threshold_strong_buy'],
                    'min_rr_ratio': row['min_rr_ratio'],
                    'position_size_multiplier': row['position_size_multiplier'],
                    'skip_pair': bool(row['skip_pair']),
                    'win_rate_7d': row['win_rate_7d'],
                    'profit_factor_7d': row['profit_factor_7d'],
                }
            
            # Return defaults (Opsi B: STRONG_BUY fallback turun 0.80 → 0.75)
            return {
                'confidence_threshold_buy': Config.CONFIDENCE_THRESHOLD,
                'confidence_threshold_strong_buy': 0.75,
                'min_rr_ratio': Config.RISK_REWARD_RATIO,
                'position_size_multiplier': 1.0,
                'skip_pair': False,
                'win_rate_7d': 0.0,
                'profit_factor_7d': 0.0,
            }

    def record_trade_outcome(self, trade_id: int, pair: str, entry_price: float,
                             exit_price: float, ml_confidence: float, 
                             recommendation: str, pnl_pct: float,
                             hold_duration_minutes: int, 
                             v4_prediction: str = None, v4_confidence: float = None,
                             market_regime: str = None):
        """
        Record trade outcome untuk V4 training dan analisis.
        
        Label:
        - GOOD_BUY: pnl_pct > 0 dan recommendation BUY/STRONG_BUY
        - BAD_BUY: pnl_pct <= 0 dan recommendation BUY/STRONG_BUY
        - GOOD_SELL: pnl_pct > 0 dan recommendation SELL/STRONG_SELL
        - BAD_SELL: pnl_pct <= 0 dan recommendation SELL/STRONG_SELL
        """
        rec_upper = recommendation.upper()
        if 'BUY' in rec_upper:
            label = 'GOOD_BUY' if pnl_pct > 0 else 'BAD_BUY'
        elif 'SELL' in rec_upper:
            label = 'GOOD_SELL' if pnl_pct > 0 else 'BAD_SELL'
        else:
            label = 'NEUTRAL'
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO trade_outcomes (
                    trade_id, pair, entry_price, exit_price, ml_confidence,
                    v4_prediction, v4_confidence, recommendation, pnl_pct,
                    hold_duration_minutes, outcome_label, market_regime
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                trade_id, pair, entry_price, exit_price, ml_confidence,
                v4_prediction, v4_confidence, rec_upper, pnl_pct,
                hold_duration_minutes, label, market_regime
            ))
            
            logger.info(f"📝 [ADAPTIVE] Trade outcome recorded: {pair} {label} ({pnl_pct:+.2f}%)")

    def get_v4_training_data(self, days: int = 30) -> List[Dict]:
        """Get labelled outcomes untuk V4 incremental training."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cutoff = datetime.now() - timedelta(days=days)
            
            cursor.execute('''
                SELECT * FROM trade_outcomes
                WHERE created_at >= ?
                ORDER BY created_at DESC
            ''', (cutoff,))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def record_regime(self, pair: str, regime: str, volatility: float,
                      trend_direction: str):
        """Record market regime untuk pair."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Close previous regime
            cursor.execute('''
                UPDATE regime_history
                SET ended_at = CURRENT_TIMESTAMP,
                    duration_minutes = (julianday(CURRENT_TIMESTAMP) - julianday(started_at)) * 24 * 60
                WHERE pair = ? AND ended_at IS NULL
            ''', (pair,))
            
            # Insert new regime
            cursor.execute('''
                INSERT INTO regime_history (pair, regime, volatility, trend_direction)
                VALUES (?, ?, ?, ?)
            ''', (pair, regime, volatility, trend_direction))
            
            logger.info(f"📊 [REGIME] {pair}: {regime} (vol={volatility:.2f}, trend={trend_direction})")

    def get_regime_history(self, pair: str, limit: int = 10) -> List[Dict]:
        """Get regime history untuk pair."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM regime_history
                WHERE pair = ?
                ORDER BY started_at DESC
                LIMIT ?
            ''', (pair, limit))
            return [dict(row) for row in cursor.fetchall()]

    def get_regime_adjusted_position_size(self, pair: str, base_size: float) -> float:
        """
        Adjust position size based on current market regime + adaptive thresholds.
        
        Returns final position size multiplier (0.0 to 1.5x).
        """
        # Get adaptive base multiplier
        thresholds = self.get_adaptive_thresholds(pair)
        if thresholds.get('skip_pair'):
            return 0.0
        
        base_mult = thresholds.get('position_size_multiplier', 1.0)
        
        # Get current regime
        regime_history = self.get_regime_history(pair, limit=1)
        if not regime_history:
            return base_size * base_mult
        
        current_regime = regime_history[0]
        regime_name = current_regime.get('regime', 'UNKNOWN')
        volatility = current_regime.get('volatility', 0.0)
        
        # Regime-based adjustments
        regime_mult = 1.0
        if regime_name == 'TRENDING_UP':
            regime_mult = 1.15  # Boost 15% in uptrend
        elif regime_name == 'TRENDING_DOWN':
            regime_mult = 0.60  # Reduce 40% in downtrend
        elif regime_name == 'RANGING':
            regime_mult = 0.85  # Reduce 15% in ranging
        elif regime_name == 'VOLATILE':
            regime_mult = 0.50  # Reduce 50% in volatile
        
        # Volatility overlay
        vol_mult = 1.0
        if volatility > 0.10:  # > 10% volatility
            vol_mult = 0.70
        elif volatility > 0.05:  # 5-10%
            vol_mult = 0.85
        elif volatility < 0.02:  # < 2%
            vol_mult = 1.10  # Boost in calm market
        
        final_mult = base_mult * regime_mult * vol_mult
        final_mult = max(0.2, min(1.5, final_mult))  # Clamp between 0.2x and 1.5x
        
        logger.info(
            f"📊 [REGIME] {pair}: base_mult={base_mult:.2f}, regime={regime_name} "
            f"(×{regime_mult:.2f}), vol={volatility:.2%} (×{vol_mult:.2f}) → final={final_mult:.2f}"
        )
        
        return base_size * final_mult

    def run_nightly_analysis(self, pairs: List[str] = None):
        """
        Run complete nightly analysis untuk semua pair.
        
        Ini adalah entry point utama yang dipanggil oleh nightly job.
        """
        logger.info("🌙 [NIGHTLY] Starting adaptive learning analysis...")
        
        if pairs is None:
            # Get all pairs that have trades
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT DISTINCT pair FROM trades WHERE status = "CLOSED"')
                pairs = [row['pair'] for row in cursor.fetchall()]
        
        analyzed = 0
        skipped = 0
        
        for pair in pairs:
            metrics = self.analyze_pair_performance(pair, days=7)
            if metrics:
                self.update_adaptive_thresholds(metrics)
                analyzed += 1
            else:
                skipped += 1
        
        # Get V4 training data summary
        v4_data = self.get_v4_training_data(days=7)
        logger.info(
            f"🌙 [NIGHTLY] Analysis complete: {analyzed} pairs analyzed, "
            f"{skipped} skipped (no data), {len(v4_data)} V4 outcomes this week"
        )
        
        return {
            'pairs_analyzed': analyzed,
            'pairs_skipped': skipped,
            'v4_outcomes_7d': len(v4_data),
        }
