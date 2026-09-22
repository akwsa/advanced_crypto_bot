#!/usr/bin/env python3
# Tujuan: Labeling outcome signal historis untuk training ML V4.
# Caller: bot.py auto-train dan maintenance commands.
# Dependensi: SignalDatabase, price history, pandas.
# Main Functions: SignalOutcomeLabeler; train_model_from_signals.
# Side Effects: DB read/write outcome cache; CPU-heavy analysis.
"""
ML Signal Trainer - Trade Outcome Based Labeling
================================================
Module untuk mengubah signal historis menjadi training dataset
 dengan label berbasis hasil trade (bukan harga future).

Label:
- GOOD_BUY    : Signal BUY yang jika di-entry, TP kena duluan sebelum SL
- BAD_BUY     : Signal BUY yang jika di-entry, SL kena duluan sebelum TP
- NEUTRAL_BUY : Signal BUY yang tidak kena TP maupun SL dalam window
- GOOD_SELL   : Signal SELL yang jika di-entry, TP kena duluan sebelum SL
- BAD_SELL    : Signal SELL yang jika di-entry, SL kena duluan sebelum TP
- NEUTRAL_SELL: Signal SELL yang tidak kena TP maupun SL dalam window

Usage:
    from analysis.ml_signal_trainer import SignalOutcomeLabeler, train_model_from_signals
    labeler = SignalOutcomeLabeler()
    labeled = labeler.label_all_signals(tp_pct=3, sl_pct=2, window=10)
    X, y = labeler.prepare_ml_dataset(labeled)
"""

import sqlite3
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


def _normalize_pair_key(pair: str) -> str:
    """Normalize pair/symbol variants to the DB's canonical compact key."""
    return str(pair or "").strip().lower().replace("/", "").replace("_", "")


def _pair_lookup_variants(pair: str) -> List[str]:
    """Return common stored pair variants without disabling SQLite indexes."""
    raw = str(pair or "").strip()
    compact = _normalize_pair_key(raw)
    variants = {raw, raw.lower(), raw.upper(), compact, compact.upper()}
    if compact.endswith("idr") and len(compact) > 3:
        base = compact[:-3]
        variants.update({
            f"{base}_idr", f"{base}_IDR", f"{base.upper()}_IDR",
            f"{base}/idr", f"{base}/IDR", f"{base.upper()}/IDR",
        })
    return [v for v in variants if v]

logger = logging.getLogger("crypto_bot")

# Default thresholds
DEFAULT_TP_PCT = 3.0       # Take profit 3%
DEFAULT_SL_PCT = 2.0       # Stop loss 2%
DEFAULT_WINDOW_CANDLES = 10  # Cek 10 candle ke depan
SIGNALS_DB_PATH = "data/signals.db"
TRADING_DB_PATH = "data/trading.db"


@dataclass
class SignalOutcome:
    """Hasil evaluasi satu signal"""
    signal_id: int
    symbol: str
    signal_price: float
    recommendation: str
    ml_confidence: float
    received_at: datetime
    label: str  # GOOD_BUY, BAD_BUY, NEUTRAL_BUY, GOOD_SELL, BAD_SELL, NEUTRAL_SELL
    max_profit_pct: float
    max_loss_pct: float
    final_return_pct: float
    candles_checked: int
    hit_tp: bool
    hit_sl: bool
    exit_price: Optional[float]
    exit_time: Optional[datetime]


class SignalOutcomeLabeler:
    """
    Label signal historis berdasarkan trade outcome.
    Bukan berdasarkan harga close N candle ke depan,
    tapi berdasarkan apakah TP atau SL yang kena duluan.
    """

    def __init__(self, signals_db: str = SIGNALS_DB_PATH,
                 trading_db: str = TRADING_DB_PATH):
        self.signals_db = signals_db
        self.trading_db = trading_db

    def _get_connection(self, db_path: str):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def load_signals(self, min_confidence: float = 0.0,
                     days_back: int = 90,
                     recommendation: Optional[str] = None) -> pd.DataFrame:
        """
        Load signal historis dari signals.db.

        Args:
            min_confidence: Minimum ML confidence (0-1)
            days_back: Load signal dari N hari terakhir
            recommendation: Filter by rec (BUY, SELL, STRONG_BUY, STRONG_SELL, HOLD)
        """
        cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

        query = """
            SELECT id, symbol, price, recommendation, ml_confidence,
                   received_at, combined_strength
            FROM signals
            WHERE received_date >= ?
              AND ml_confidence >= ?
        """
        params = [cutoff, min_confidence]

        if recommendation:
            query += " AND recommendation = ?"
            params.append(recommendation.upper())

        query += " ORDER BY received_at ASC"

        conn = None
        try:
            conn = self._get_connection(self.signals_db)
            df = pd.read_sql_query(query, conn, params=params)
        except Exception as e:
            logger.error(f"❌ Failed to load signals: {e}")
            return pd.DataFrame()
        finally:
            if conn is not None:
                conn.close()

        if df.empty:
            logger.warning("⚠️ No signals found in DB for labeling")
            return df

        df['received_at'] = pd.to_datetime(df['received_at'])
        logger.info(f"📊 Loaded {len(df)} signals from {self.signals_db}")
        return df

    def load_price_history_after(self, symbol: str,
                                  after_time: datetime,
                                  limit: int = 50) -> pd.DataFrame:
        """
        Load price history untuk pair setelah waktu signal.
        Mengambil dari trading.db price_history.
        """
        conn = None
        try:
            conn = self._get_connection(self.trading_db)
            variants = _pair_lookup_variants(symbol)
            placeholders = ",".join("?" for _ in variants)
            df = pd.read_sql_query(
                f"""
                SELECT timestamp, open, high, low, close, volume
                FROM price_history
                WHERE pair IN ({placeholders})
                  AND timestamp > ?
                ORDER BY timestamp ASC
                LIMIT ?
                """,
                conn,
                params=(*variants, after_time.strftime("%Y-%m-%d %H:%M:%S"), limit)
            )
        except Exception as e:
            logger.debug(f"Price history load failed for {symbol}: {e}")
            return pd.DataFrame()
        finally:
            if conn is not None:
                conn.close()

        if df.empty:
            return df

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df

    def label_single_signal(self, row: pd.Series,
                            tp_pct: float = DEFAULT_TP_PCT,
                            sl_pct: float = DEFAULT_SL_PCT,
                            window: int = DEFAULT_WINDOW_CANDLES) -> SignalOutcome:
        """
        Evaluasi satu signal: cek apakah TP atau SL kena duluan.

        Logic:
        - BUY signal: TP = signal_price * (1 + tp_pct/100)
                      SL = signal_price * (1 - sl_pct/100)
        - SELL signal: TP = signal_price * (1 - tp_pct/100)
                       SL = signal_price * (1 + sl_pct/100)

        Scan candle ke depan:
        - Jika high >= TP sebelum low <= SL → GOOD
        - Jika low <= SL sebelum high >= TP → BAD
        - Jika sampai window habis tidak kena TP/SL → NEUTRAL
        """
        symbol = row['symbol']
        signal_price = float(row['price'])
        rec = row['recommendation']
        received_at = row['received_at']

        # Ambil price history setelah signal
        future = self.load_price_history_after(symbol, received_at, limit=window)

        # Default outcome (kalau tidak ada data)
        if future.empty or len(future) < 3:
            return SignalOutcome(
                signal_id=int(row.get('id', 0)),
                symbol=symbol,
                signal_price=signal_price,
                recommendation=rec,
                ml_confidence=float(row.get('ml_confidence', 0) or 0),
                received_at=received_at,
                label="NEUTRAL_BUY" if 'BUY' in rec else "NEUTRAL_SELL" if 'SELL' in rec else "NEUTRAL",
                max_profit_pct=0.0,
                max_loss_pct=0.0,
                final_return_pct=0.0,
                candles_checked=0,
                hit_tp=False,
                hit_sl=False,
                exit_price=None,
                exit_time=None,
            )

        # Hitung TP dan SL levels
        is_buy = 'BUY' in rec
        tp_price = signal_price * (1 + tp_pct / 100) if is_buy else signal_price * (1 - tp_pct / 100)
        sl_price = signal_price * (1 - sl_pct / 100) if is_buy else signal_price * (1 + sl_pct / 100)

        # Scan candle
        hit_tp = False
        hit_sl = False
        exit_price = None
        exit_time = None
        max_profit_pct = 0.0
        max_loss_pct = 0.0

        for idx, candle in future.iterrows():
            high = float(candle['high'])
            low = float(candle['low'])
            close = float(candle['close'])

            # Track max profit/loss selama window
            if signal_price != 0:
                profit_pct = ((high if is_buy else low) - signal_price) / signal_price * 100
                loss_pct = ((low if is_buy else high) - signal_price) / signal_price * 100
            else:
                profit_pct = 0.0
                loss_pct = 0.0
            max_profit_pct = max(max_profit_pct, profit_pct if is_buy else -profit_pct)
            max_loss_pct = min(max_loss_pct, loss_pct if is_buy else -loss_pct)

            # Cek TP
            if is_buy and high >= tp_price:
                hit_tp = True
                exit_price = tp_price
                exit_time = candle['timestamp']
                break
            elif not is_buy and low <= tp_price:
                hit_tp = True
                exit_price = tp_price
                exit_time = candle['timestamp']
                break

            # Cek SL
            if is_buy and low <= sl_price:
                hit_sl = True
                exit_price = sl_price
                exit_time = candle['timestamp']
                break
            elif not is_buy and high >= sl_price:
                hit_sl = True
                exit_price = sl_price
                exit_time = candle['timestamp']
                break

        # Final return = close terakhir candle window
        final_price = float(future.iloc[-1]['close'])
        final_return_pct = (final_price - signal_price) / signal_price * 100 if signal_price != 0 else 0.0

        # Tentukan label
        if is_buy:
            if hit_tp and not hit_sl:
                label = "GOOD_BUY"
            elif hit_sl and not hit_tp:
                label = "BAD_BUY"
            else:
                label = "NEUTRAL_BUY"
        elif 'SELL' in rec:
            if hit_tp and not hit_sl:
                label = "GOOD_SELL"
            elif hit_sl and not hit_tp:
                label = "BAD_SELL"
            else:
                label = "NEUTRAL_SELL"
        else:
            label = "NEUTRAL"

        return SignalOutcome(
            signal_id=int(row.get('id', 0)),
            symbol=symbol,
            signal_price=signal_price,
            recommendation=rec,
            ml_confidence=float(row.get('ml_confidence', 0) or 0),
            received_at=received_at,
            label=label,
            max_profit_pct=max_profit_pct,
            max_loss_pct=max_loss_pct,
            final_return_pct=final_return_pct,
            candles_checked=len(future),
            hit_tp=hit_tp,
            hit_sl=hit_sl,
            exit_price=exit_price,
            exit_time=exit_time,
        )

    def label_all_signals(self, tp_pct: float = DEFAULT_TP_PCT,
                          sl_pct: float = DEFAULT_SL_PCT,
                          window: int = DEFAULT_WINDOW_CANDLES,
                          min_confidence: float = 0.0,
                          days_back: int = 90) -> List[SignalOutcome]:
        """
        Label semua signal historis.

        Returns:
            List[SignalOutcome] - hasil evaluasi tiap signal
        """
        signals = self.load_signals(min_confidence=min_confidence, days_back=days_back)
        if signals.empty:
            return []

        # Hanya proses actionable signals (BUY/SELL/STRONG)
        actionable = signals[
            signals['recommendation'].isin(['BUY', 'STRONG_BUY', 'SELL', 'STRONG_SELL'])
        ].copy()

        if actionable.empty:
            logger.warning("⚠️ No actionable signals to label")
            return []

        logger.info(f"🔍 Labeling {len(actionable)} actionable signals "
                    f"(TP={tp_pct}%, SL={sl_pct}%, window={window}candles)")

        outcomes = []
        for _, row in actionable.iterrows():
            outcome = self.label_single_signal(row, tp_pct, sl_pct, window)
            outcomes.append(outcome)

        # Summary
        labels = [o.label for o in outcomes]
        from collections import Counter
        dist = Counter(labels)
        logger.info(f"📊 Label distribution: {dict(dist)}")

        good = sum(1 for o in outcomes if o.label.startswith('GOOD'))
        bad = sum(1 for o in outcomes if o.label.startswith('BAD'))
        neutral = sum(1 for o in outcomes if o.label.startswith('NEUTRAL'))
        total = len(outcomes)

        if total > 0:
            win_rate = good / (good + bad) if (good + bad) > 0 else 0
            logger.info(f"📊 Win rate (TP before SL): {win_rate:.1%} "
                        f"({good} good / {bad} bad / {neutral} neutral)")

        return outcomes

    def prepare_ml_dataset(self, outcomes: List[SignalOutcome],
                           include_hold: bool = True) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Siapkan dataset untuk training ML dari hasil labeling.

        Returns:
            X: DataFrame fitur (price, confidence, combined_strength, time features)
            y: Series label (GOOD_BUY, BAD_BUY, NEUTRAL, GOOD_SELL, BAD_SELL)
        """
        if not outcomes:
            return pd.DataFrame(), pd.Series()

        records = []
        for o in outcomes:
            records.append({
                'symbol': o.symbol,
                'signal_price': o.signal_price,
                'ml_confidence': o.ml_confidence,
                'recommendation': o.recommendation,
                'hour': o.received_at.hour,
                'dayofweek': o.received_at.weekday(),
                'label': o.label,
            })

        df = pd.DataFrame(records)

        # Encode categorical
        df['rec_encoded'] = df['recommendation'].map({
            'BUY': 0, 'STRONG_BUY': 1, 'SELL': 2, 'STRONG_SELL': 3
        }).fillna(-1)

        # Fitur dasar
        X = df[['signal_price', 'ml_confidence', 'rec_encoded', 'hour', 'dayofweek']].copy()

        # Normalisasi price (gunakan log)
        X['signal_price_log'] = np.log1p(df['signal_price'])

        # Fitur interaksi
        X['conf_x_rec'] = X['ml_confidence'] * X['rec_encoded']

        y = df['label']

        logger.info(f"📊 ML dataset: {len(X)} samples, {len(y.unique())} classes")
        return X, y

    def get_label_stats(self, outcomes: List[SignalOutcome]) -> Dict:
        """Hitung statistik outcome untuk report"""
        if not outcomes:
            return {}

        labels = [o.label for o in outcomes]
        from collections import Counter
        dist = Counter(labels)

        buy_signals = [o for o in outcomes if 'BUY' in o.recommendation and 'SELL' not in o.recommendation]
        sell_signals = [o for o in outcomes if 'SELL' in o.recommendation]

        def calc_stats(sigs):
            if not sigs:
                return {}
            good = sum(1 for s in sigs if s.label.startswith('GOOD'))
            bad = sum(1 for s in sigs if s.label.startswith('BAD'))
            neutral = sum(1 for s in sigs if s.label.startswith('NEUTRAL'))
            total = len(sigs)
            win_rate = good / (good + bad) if (good + bad) > 0 else 0
            avg_max_profit = np.mean([s.max_profit_pct for s in sigs])
            avg_max_loss = np.mean([s.max_loss_pct for s in sigs])
            return {
                'total': total,
                'good': good,
                'bad': bad,
                'neutral': neutral,
                'win_rate': win_rate,
                'avg_max_profit_pct': avg_max_profit,
                'avg_max_loss_pct': avg_max_loss,
            }

        return {
            'overall': dict(dist),
            'buy_stats': calc_stats(buy_signals),
            'sell_stats': calc_stats(sell_signals),
        }


# =============================================================================
# Integration helper
# =============================================================================

def train_model_from_signals(bot, tp_pct: float = DEFAULT_TP_PCT,
                             sl_pct: float = DEFAULT_SL_PCT,
                             window: int = DEFAULT_WINDOW_CANDLES,
                             days_back: int = 90) -> Tuple[bool, str]:
    """
    Helper untuk training model dari signal historis.
    Dipanggil dari bot.py saat auto-retrain atau manual /retrain.

    Returns:
        (success: bool, message: str)
    """
    try:
        labeler = SignalOutcomeLabeler(
            signals_db=getattr(bot, '_signal_db_path', SIGNALS_DB_PATH),
            trading_db=getattr(bot, 'db_path', TRADING_DB_PATH)
        )

        outcomes = labeler.label_all_signals(
            tp_pct=tp_pct, sl_pct=sl_pct, window=window, days_back=days_back
        )

        if not outcomes:
            return False, "No actionable signals found for training"

        stats = labeler.get_label_stats(outcomes)
        buy_stats = stats.get('buy_stats', {})
        sell_stats = stats.get('sell_stats', {})

        msg = (
            f"📊 Signal labeling complete\n"
            f"• Total labeled: {len(outcomes)}\n"
            f"• BUY win rate: {buy_stats.get('win_rate', 0):.1%} "
            f"({buy_stats.get('good', 0)} good / {buy_stats.get('bad', 0)} bad)\n"
            f"• SELL win rate: {sell_stats.get('win_rate', 0):.1%} "
            f"({sell_stats.get('good', 0)} good / {sell_stats.get('bad', 0)} bad)\n"
            f"• Labels: {stats.get('overall', {})}"
        )
        logger.info(msg)

        # Simpan outcomes ke bot untuk digunakan oleh model
        bot._last_signal_outcomes = outcomes
        bot._last_signal_label_stats = stats

        return True, msg

    except Exception as e:
        logger.error(f"❌ Signal labeling failed: {e}")
        return False, f"Signal labeling failed: {e}"


if __name__ == "__main__":
    # Test run
    logging.basicConfig(level=logging.INFO)
    labeler = SignalOutcomeLabeler()
    outcomes = labeler.label_all_signals(tp_pct=3, sl_pct=2, window=10, days_back=30)
    if outcomes:
        stats = labeler.get_label_stats(outcomes)
        print("\nStats:", stats)
        X, y = labeler.prepare_ml_dataset(outcomes)
        print(f"\nDataset shape: X={X.shape}, y={y.shape}")
        print("Label distribution:")
        print(y.value_counts())
