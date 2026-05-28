# Tujuan: Regression tests untuk ranking tampilan signal, market scan read-only,
# pair performance ordering, dan safety logic Ultra Hunter.
# Caller: scripts/test.sh focused ranking/hunter tests.
# Side Effects: memakai DB sqlite temp; tidak mengirim order/Telegram nyata.

import asyncio
import sqlite3
from datetime import date, timedelta

import pytest

from bot_parts.formatting import format_signal_section_html
from core.database import Database
from autohunter.ultra_hunter import UltraConservativeHunter


def test_signal_section_ranks_strong_buy_before_plain_buy_even_with_lower_confidence():
    text = format_signal_section_html(
        "🟢 BUY Signals",
        [
            {
                "pair": "weakidr",
                "recommendation": "BUY",
                "ml_confidence": 0.95,
                "combined_strength": 0.10,
                "price": 100,
            },
            {
                "pair": "strongidr",
                "recommendation": "STRONG_BUY",
                "ml_confidence": 0.72,
                "combined_strength": 0.80,
                "price": 100,
            },
        ],
    )

    assert text.index("STRONGIDR") < text.index("WEAKIDR")


def test_signal_section_ranks_buy_by_strength_before_confidence_when_same_decision():
    text = format_signal_section_html(
        "🟢 BUY Signals",
        [
            {
                "pair": "confonlyidr",
                "recommendation": "BUY",
                "ml_confidence": 0.92,
                "combined_strength": 0.15,
                "price": 100,
            },
            {
                "pair": "qualityidr",
                "recommendation": "BUY",
                "ml_confidence": 0.75,
                "combined_strength": 0.65,
                "price": 100,
            },
        ],
    )

    assert text.index("QUALITYIDR") < text.index("CONFONLYIDR")


def test_pair_performance_ranking_demotes_zero_loss_infinity_with_tiny_sample(tmp_path):
    db = Database(str(tmp_path / "ranking.db"))
    with db.get_connection() as conn:
        conn.executemany(
            """
            INSERT INTO pair_performance
            (pair, total_trades, win_count, loss_count, avg_profit_pct, avg_loss_pct,
             total_profit_pct, total_loss_pct, profit_factor, last_trade_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [
                ("LUCKYIDR", 5, 5, 0, 0.20, 0.0, 1.0, 0.0, float("inf")),
                ("STEADYIDR", 30, 20, 10, 1.00, -0.50, 20.0, 5.0, 4.0),
                ("MIDIDR", 20, 12, 8, 0.80, -0.60, 9.6, 4.8, 2.0),
            ],
        )

    rows = db.get_all_pair_performance(min_trades=5)

    assert [row["pair"] for row in rows[:3]] == ["STEADYIDR", "MIDIDR", "LUCKYIDR"]


def test_ultra_hunter_macd_fresh_only_when_last_candle_crosses_zero():
    hunter = UltraConservativeHunter(dry_run=True)
    prices = [100.0] * 36 + [160.0] * 5

    macd = hunter.calc_macd(prices)

    assert macd["bullish"] is True
    assert macd["fresh"] is False


def test_ultra_hunter_daily_reset_keeps_pnl_when_open_positions_and_resets_without_positions():
    hunter = UltraConservativeHunter(dry_run=True)
    hunter.daily_trades = 2
    hunter.daily_pnl = -50_000
    hunter.active_trades = {"BTCIDR": {"entry_price": 100}}
    hunter._last_reset = date.today() - timedelta(days=1)

    hunter._reset_daily_counters_if_needed(today=date.today())

    assert hunter.daily_trades == 0
    assert hunter.daily_pnl == -50_000
    assert hunter._last_reset == date.today()

    hunter.active_trades = {}
    hunter.daily_pnl = -75_000
    hunter._last_reset = date.today() - timedelta(days=1)

    hunter._reset_daily_counters_if_needed(today=date.today())

    assert hunter.daily_pnl == 0


@pytest.mark.asyncio
async def test_market_scan_ranks_gainers_by_positive_change_not_absolute_drop(monkeypatch):
    from bot import AdvancedCryptoBot

    sent = []
    bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)

    async def fake_send(update, context, text, parse_mode=None):
        sent.append((text, parse_mode))

    bot._send_message = fake_send

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "tickers": {
                    "bigdrop_idr": {"last": "100", "open": "200", "high": "210", "low": "90", "vol_idr": "5000000000"},
                    "smallgain_idr": {"last": "110", "open": "100", "high": "115", "low": "95", "vol_idr": "2000000000"},
                    "biggain_idr": {"last": "150", "open": "100", "high": "155", "low": "95", "vol_idr": "1500000000"},
                }
            }

    class FakeIndodax:
        base_url = "https://example.test"

    async def fake_to_thread(fn, *args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr("api.indodax_api.IndodaxAPI", lambda: FakeIndodax())
    monkeypatch.setattr("bot.asyncio.to_thread", fake_to_thread)

    await bot.market_scan(object(), object())

    final_text = sent[-1][0]
    gainers_section = final_text.split("🟢 **TOP GAINERS**", 1)[1].split("🔴 **TOP LOSERS**", 1)[0]
    assert gainers_section.index("BIGGAIN/IDR") < gainers_section.index("SMALLGAIN/IDR")
    assert "BIGDROP/IDR" not in gainers_section
    assert "Change vs open" in final_text
