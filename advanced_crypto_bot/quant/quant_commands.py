#!/usr/bin/env python3
# Tujuan: Telegram command handlers untuk quant trading modules.
# Caller: bot.py via handler_registry.py.
# Dependensi: quant/*, telegram, core/config.
# Main Functions: register_quant_handlers, quant command handlers.
# Side Effects: Telegram message sends, DB reads for trade history.
"""
Quant Trading Telegram Command Handlers
=========================================
Commands:
    /quant           - Menu utama quant modules
    /quant_mr        - Z-Score Mean Reversion analysis
    /quant_kelly     - Bayesian Kelly position sizing
    /quant_momentum  - Momentum factor scoring
    /quant_perf      - Performance analytics
    /quant_corr      - Dynamic correlation matrix
    /quant_arb       - Statistical arbitrage scanner
"""

import logging
try:
    from telegram import Update
    from telegram.ext import CommandHandler, ContextTypes
except (ImportError, ModuleNotFoundError):
    class Update:
        pass

    class ContextTypes:
        DEFAULT_TYPE = object

    class CommandHandler:
        def __init__(self, command, callback, *args, **kwargs):
            self.command = command
            self.callback = callback
            self.args = args
            self.kwargs = kwargs

logger = logging.getLogger("crypto_bot")


# =============================================================================
# QUANT MENU
# =============================================================================

async def quant_menu_cmd(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show quant trading modules menu."""
    text = (
        "📈 <b>Quant Trading Modules</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔬 <b>Available Modules:</b>\n\n"
        "1️⃣ /quant_mr &lt;pair&gt;\n"
        "   Z-Score Mean Reversion\n"
        "   <i>Detect oversold/overbought via statistical z-score</i>\n\n"
        "2️⃣ /quant_kelly &lt;pair&gt;\n"
        "   Bayesian Kelly Sizing\n"
        "   <i>Optimal position size based on win rate history</i>\n\n"
        "3️⃣ /quant_momentum &lt;pair&gt;\n"
        "   Momentum Factor Scoring\n"
        "   <i>Multi-timeframe ROC + volume-weighted momentum</i>\n\n"
        "4️⃣ /quant_perf\n"
        "   Performance Analytics\n"
        "   <i>Sharpe, Sortino, Calmar, Profit Factor, Drawdown</i>\n\n"
        "5️⃣ /quant_corr\n"
        "   Dynamic Correlation\n"
        "   <i>Portfolio heat & correlation matrix</i>\n\n"
        "6️⃣ /quant_arb\n"
        "   Statistical Arbitrage\n"
        "   <i>Pair trading via cointegration & spread z-score</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "7️⃣ /quant_risk &lt;pair&gt;\n"
        "   CAGR, VaR (3 metode), CVaR\n"
        "   <i>Risk metrics dari return historis harga</i>\n\n"
        "8️⃣ /quant_forecast &lt;pair&gt; [steps]\n"
        "   ARIMA Price Forecast\n"
        "   <i>Prediksi harga jangka pendek (default 5 langkah)</i>\n\n"
        "9️⃣ /quant_frontier\n"
        "   Efficient Frontier (Markowitz MPT)\n"
        "   <i>Alokasi modal optimal dari semua pair di watchlist</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <i>Modules #1 (Mean Reversion), GARCH, VaR, ARIMA sudah aktif di signal pipeline.</i>"
    )
    await update.message.reply_text(text, parse_mode='HTML')


# =============================================================================
# /quant_mr - Mean Reversion Analysis
# =============================================================================

async def quant_mr_cmd(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Z-Score Mean Reversion analysis for a pair."""
    from quant.mean_reversion import MeanReversionEngine

    pair = context.args[0].lower() if context.args else None
    if not pair:
        await update.message.reply_text(
            "Usage: /quant_mr <pair>\nExample: /quant_mr btcidr",
            parse_mode='HTML'
        )
        return

    pair = bot.trading_engine._validate_signal_inputs and pair.replace('/', '').replace('_', '')

    if pair not in bot.historical_data or bot.historical_data[pair].empty:
        await update.message.reply_text(f"❌ No data for {pair}. Add to watchlist first: /watch {pair}")
        return

    df = bot.historical_data[pair].copy()
    engine = bot.signal_quality_engine.mean_reversion_engine
    if engine is None:
        engine = MeanReversionEngine()

    regime, _ = bot.signal_quality_engine.detect_market_regime(df)
    current_price = df['close'].iloc[-1]
    result = engine.analyze(df, current_price=current_price, pair=pair, market_regime=regime)

    if result is None:
        await update.message.reply_text(f"⚠️ Insufficient data for {pair} (need 60+ candles)")
        return

    # Format output
    z_emoji = "🟢" if result.z_score_composite < -1.5 else "🔴" if result.z_score_composite > 1.5 else "⚪"
    text = (
        f"📊 <b>Mean Reversion Analysis: {pair.upper()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{z_emoji} <b>Z-Score Composite:</b> <code>{result.z_score_composite:+.3f}</code>\n\n"
        f"📈 <b>Multi-Timeframe Z-Scores:</b>\n"
        f"   Fast (20):   <code>{result.z_score_fast:+.3f}</code>\n"
        f"   Medium (50): <code>{result.z_score_medium:+.3f}</code>\n"
        f"   Slow (100):  <code>{result.z_score_slow:+.3f}</code>\n\n"
        f"📉 <b>Bollinger %B:</b> <code>{result.bb_pct_b:.3f}</code>\n"
        f"   {'⬇️ Below lower band' if result.bb_pct_b < 0.2 else '⬆️ Above upper band' if result.bb_pct_b > 0.8 else '↔️ Within bands'}\n\n"
        f"{'📊 <b>VWAP Z-Score:</b> <code>' + f'{result.vwap_z_score:+.3f}' + '</code>' if result.vwap_z_score else ''}\n\n"
        f"🎯 <b>Signal:</b> <code>{result.signal}</code>\n"
        f"   Confluence Bonus: +{result.confluence_bonus}\n"
        f"   Confidence Boost: +{result.confidence_boost:.1%}\n"
        f"   Regime Alignment: {'✅' if result.regime_alignment else '⚠️'} ({regime})\n\n"
        f"💰 <b>Price Context:</b>\n"
        f"   Current: <code>{current_price:,.0f}</code>\n"
        f"   Mean (20): <code>{result.mean_price:,.0f}</code>\n"
        f"   Std: <code>{result.std_price:,.0f}</code>\n"
    )
    await update.message.reply_text(text, parse_mode='HTML')


# =============================================================================
# /quant_kelly - Bayesian Kelly Position Sizing
# =============================================================================

async def quant_kelly_cmd(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bayesian Kelly position sizing for a pair."""
    from quant.bayesian_kelly import BayesianKellyEngine

    pair = context.args[0].lower().replace('/', '').replace('_', '') if context.args else None
    user_id = update.effective_user.id

    # Initialize engine if not exists
    if not hasattr(bot, '_quant_kelly_engine'):
        bot._quant_kelly_engine = BayesianKellyEngine()
        # Seed with trade history
        trades = bot.db.get_trade_history(user_id, limit=100)
        for t in (trades or []):
            if t.get('profit_loss') is not None and t.get('pair'):
                won = t['profit_loss'] > 0
                pnl_pct = t.get('profit_loss_pct', 0) or (
                    t['profit_loss'] / t['total'] * 100 if t.get('total') else 0
                )
                bot._quant_kelly_engine.update_trade_outcome(
                    t['pair'].lower(), won=won, pnl_pct=pnl_pct
                )

    engine = bot._quant_kelly_engine
    balance = bot.db.get_balance(user_id)

    if not pair:
        # Show stats for all pairs
        stats = engine.get_all_stats()
        if not stats:
            await update.message.reply_text(
                "📊 <b>Bayesian Kelly</b>\n\n"
                "No trade history yet. Use: /quant_kelly &lt;pair&gt;\n"
                "Kelly will use global stats or prior.",
                parse_mode='HTML'
            )
            return
        text = "📊 <b>Bayesian Kelly — Per-Pair Stats</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for p, s in stats.items():
            text += (
                f"<b>{p.upper()}</b>: WR={s['bayesian_win_rate']:.1%} | "
                f"W/L={s['win_loss_ratio']:.2f} | "
                f"Kelly={s['raw_kelly_pct']:.1%} | "
                f"Trades={s['total_trades']}\n"
            )
        await update.message.reply_text(text, parse_mode='HTML')
        return

    # Get current price
    price = 0
    if pair in bot.historical_data and not bot.historical_data[pair].empty:
        price = float(bot.historical_data[pair]['close'].iloc[-1])
    if price <= 0:
        await update.message.reply_text(f"❌ No price data for {pair}")
        return

    result = engine.calculate_position_size(
        pair=pair, balance=balance, entry_price=price,
        ml_confidence=0.70, volatility_pct=2.0, current_drawdown_pct=0.0
    )

    text = (
        f"📊 <b>Bayesian Kelly: {pair.upper()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 <b>Position Sizing:</b>\n"
        f"   Allocation: <code>{result.kelly_fraction:.2%}</code> of balance\n"
        f"   Position: <code>{result.position_value:,.0f}</code> IDR\n"
        f"   Amount: <code>{result.position_amount:.8f}</code>\n\n"
        f"📈 <b>Kelly Components:</b>\n"
        f"   Raw Kelly: <code>{result.raw_kelly_pct:.2%}</code>\n"
        f"   Win Rate (Bayesian): <code>{result.bayesian_win_rate:.1%}</code>\n"
        f"   W/L Ratio: <code>{result.win_loss_ratio:.2f}</code>\n\n"
        f"⚙️ <b>Adjustment Factors:</b>\n"
        f"   Confidence: <code>{result.confidence_factor:.2f}</code>\n"
        f"   Volatility: <code>{result.volatility_factor:.2f}</code>\n"
        f"   Drawdown: <code>{result.drawdown_factor:.2f}</code>\n\n"
        f"📋 Method: <code>{result.method}</code>\n"
        f"   Trades used: {result.total_trades}\n"
    )
    await update.message.reply_text(text, parse_mode='HTML')


# =============================================================================
# /quant_momentum - Momentum Factor Scoring
# =============================================================================

async def quant_momentum_cmd(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Momentum factor analysis for a pair."""
    from quant.momentum_factor import MomentumFactorEngine

    pair = context.args[0].lower().replace('/', '').replace('_', '') if context.args else None
    if not pair:
        await update.message.reply_text("Usage: /quant_momentum <pair>\nExample: /quant_momentum btcidr")
        return

    if pair not in bot.historical_data or bot.historical_data[pair].empty:
        await update.message.reply_text(f"❌ No data for {pair}. Add to watchlist: /watch {pair}")
        return

    if not hasattr(bot, '_quant_momentum_engine'):
        bot._quant_momentum_engine = MomentumFactorEngine()

    df = bot.historical_data[pair].copy()
    result = bot._quant_momentum_engine.analyze(df, pair=pair)

    if result is None:
        await update.message.reply_text(f"⚠️ Insufficient data for {pair} (need 55+ candles)")
        return

    dir_emoji = "🟢" if result.direction == 'BULLISH' else "🔴" if result.direction == 'BEARISH' else "⚪"
    text = (
        f"📊 <b>Momentum Factor: {pair.upper()}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{dir_emoji} <b>Score:</b> <code>{result.momentum_score:+.1f}</code>/100\n"
        f"   Direction: <b>{result.direction}</b> ({result.strength})\n"
        f"   Edge Bonus: +{result.edge_bonus:.0f} pts\n\n"
        f"📈 <b>Rate of Change (ROC):</b>\n"
        f"   5-period:  <code>{result.roc_fast:+.2f}%</code>\n"
        f"   10-period: <code>{result.roc_medium:+.2f}%</code>\n"
        f"   20-period: <code>{result.roc_slow:+.2f}%</code>\n"
        f"   50-period: <code>{result.roc_trend:+.2f}%</code>\n\n"
        f"📊 <b>Advanced:</b>\n"
        f"   Vol-Weighted: <code>{result.volume_momentum:+.3f}</code>\n"
        f"   Acceleration: <code>{result.acceleration:+.3f}</code>\n"
        f"   {'⬆️ Accelerating' if result.acceleration > 0.5 else '⬇️ Decelerating' if result.acceleration < -0.5 else '↔️ Stable'}\n"
    )
    await update.message.reply_text(text, parse_mode='HTML')


# =============================================================================
# /quant_perf - Performance Analytics
# =============================================================================

async def quant_perf_cmd(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Performance analytics (Sharpe, Sortino, Calmar)."""
    from quant.performance_analytics import PerformanceAnalytics

    user_id = update.effective_user.id
    trades = bot.db.get_trade_history(user_id, limit=200)

    if not trades or len(trades) < 5:
        await update.message.reply_text(
            "📊 <b>Performance Analytics</b>\n\n"
            "⚠️ Need at least 5 closed trades for analytics.\n"
            f"Current: {len(trades) if trades else 0} trades",
            parse_mode='HTML'
        )
        return

    pa = PerformanceAnalytics()
    metrics = pa.calculate_from_trades(trades)

    if metrics is None:
        await update.message.reply_text("⚠️ Could not calculate metrics from trade history.")
        return

    # Risk level emoji
    if metrics.sharpe_ratio >= 1.5:
        perf_emoji = "🏆"
    elif metrics.sharpe_ratio >= 0.5:
        perf_emoji = "✅"
    elif metrics.sharpe_ratio >= 0:
        perf_emoji = "⚠️"
    else:
        perf_emoji = "❌"

    text = (
        f"📊 <b>Quant Performance Analytics</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{perf_emoji} <b>Risk-Adjusted Returns:</b>\n"
        f"   Sharpe Ratio:  <code>{metrics.sharpe_ratio:.3f}</code>\n"
        f"   Sortino Ratio: <code>{metrics.sortino_ratio:.3f}</code>\n"
        f"   Calmar Ratio:  <code>{metrics.calmar_ratio:.3f}</code>\n\n"
        f"💰 <b>Profit Metrics:</b>\n"
        f"   Profit Factor: <code>{metrics.profit_factor:.2f}</code>\n"
        f"   Expectancy: <code>{metrics.expectancy_pct:+.3f}%</code>/trade\n"
        f"   Net Profit: <code>{metrics.net_profit_pct:+.2f}%</code>\n\n"
        f"🎯 <b>Win/Loss:</b>\n"
        f"   Win Rate: <code>{metrics.win_rate:.1%}</code> ({metrics.winning_trades}W/{metrics.losing_trades}L)\n"
        f"   Avg Win: <code>+{metrics.avg_win_pct:.2f}%</code>\n"
        f"   Avg Loss: <code>{metrics.avg_loss_pct:.2f}%</code>\n"
        f"   Best: <code>+{metrics.best_trade_pct:.2f}%</code> | Worst: <code>{metrics.worst_trade_pct:.2f}%</code>\n"
        f"   Max Streak: {metrics.max_consecutive_wins}W / {metrics.max_consecutive_losses}L\n\n"
        f"📉 <b>Drawdown:</b>\n"
        f"   Max Drawdown: <code>{metrics.max_drawdown_pct:.2f}%</code>\n"
        f"   Current DD: <code>{metrics.current_drawdown_pct:.2f}%</code>\n"
        f"   Recovery Factor: <code>{metrics.recovery_factor:.2f}</code>\n\n"
        f"📊 <b>Rolling (Recent):</b>\n"
        f"   Sharpe 7d: <code>{metrics.sharpe_7d:.2f}</code>\n" if metrics.sharpe_7d else ""
        f"   Sharpe 30d: <code>{metrics.sharpe_30d:.2f}</code>\n" if metrics.sharpe_30d else ""
        f"   Win Rate 7d: <code>{metrics.win_rate_7d:.1%}</code>\n" if metrics.win_rate_7d else ""
    )
    await update.message.reply_text(text, parse_mode='HTML')


# =============================================================================
# /quant_corr - Dynamic Correlation
# =============================================================================

async def quant_corr_cmd(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dynamic correlation matrix and portfolio heat."""
    from quant.dynamic_correlation import DynamicCorrelationEngine

    if not hasattr(bot, '_quant_corr_engine'):
        bot._quant_corr_engine = DynamicCorrelationEngine()

    engine = bot._quant_corr_engine

    # Feed current price data
    for pair, df in bot.historical_data.items():
        if df is not None and not df.empty and len(df) >= 20:
            prices = df['close'].astype(float).tolist()
            engine.update_prices(pair, prices)

    matrix = engine.get_correlation_matrix()
    if matrix is None or matrix.empty:
        await update.message.reply_text(
            "⚠️ Need at least 2 pairs with 15+ candles for correlation.\n"
            "Add pairs to watchlist: /watch btcidr ethidr"
        )
        return

    # Portfolio heat
    user_id = update.effective_user.id
    open_trades = bot.db.get_open_trades(user_id) if hasattr(bot.db, 'get_open_trades') else []
    heat = engine.calculate_portfolio_heat(open_trades) if open_trades else None

    # Build correlation text (top correlations)
    pairs = list(matrix.columns)
    corr_lines = []
    for i, p1 in enumerate(pairs):
        for p2 in pairs[i+1:]:
            val = matrix.loc[p1, p2]
            if abs(val) >= 0.4:
                emoji = "🔴" if abs(val) >= 0.7 else "🟡" if abs(val) >= 0.5 else "⚪"
                corr_lines.append(f"   {emoji} {p1}/{p2}: <code>{val:+.3f}</code>")

    corr_lines.sort(key=lambda x: abs(float(x.split(':')[1].strip().replace('</code>', ''))), reverse=True)

    text = (
        f"📊 <b>Dynamic Correlation Matrix</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📈 <b>Tracked Pairs:</b> {len(pairs)}\n\n"
        f"🔗 <b>Top Correlations:</b>\n"
    )
    text += "\n".join(corr_lines[:10]) if corr_lines else "   No significant correlations found"
    text += "\n\n"

    if heat:
        heat_emoji = "🟢" if heat.risk_level == 'LOW' else "🟡" if heat.risk_level == 'MODERATE' else "🔴"
        text += (
            f"🌡️ <b>Portfolio Heat:</b>\n"
            f"   {heat_emoji} Risk Level: <b>{heat.risk_level}</b>\n"
            f"   Heat Score: <code>{heat.total_heat:.3f}</code>\n"
            f"   Diversification: <code>{heat.diversification_score:.3f}</code>\n"
            f"   Avg Correlation: <code>{heat.avg_correlation:.3f}</code>\n"
        )
        if heat.correlation_groups:
            text += "   Groups: " + ", ".join(
                f"{k}({','.join(v)})" for k, v in heat.correlation_groups.items()
            ) + "\n"
    else:
        text += "🌡️ <i>No open positions for heat analysis</i>\n"

    await update.message.reply_text(text, parse_mode='HTML')


# =============================================================================
# /quant_arb - Statistical Arbitrage Scanner
# =============================================================================

async def quant_arb_cmd(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Statistical arbitrage pair scanner."""
    from quant.stat_arb import StatArbEngine

    if not hasattr(bot, '_quant_arb_engine'):
        bot._quant_arb_engine = StatArbEngine()

    engine = bot._quant_arb_engine

    # Feed price data
    fed_pairs = 0
    for pair, df in bot.historical_data.items():
        if df is not None and not df.empty and len(df) >= 60:
            prices = df['close'].astype(float).tolist()
            engine.update_prices(pair, prices)
            fed_pairs += 1

    if fed_pairs < 2:
        await update.message.reply_text(
            "⚠️ Need at least 2 pairs with 60+ candles.\n"
            "Add pairs: /watch btcidr ethidr dogeidr"
        )
        return

    # Scan for cointegrated pairs
    cointegrated = engine.get_cointegrated_pairs()
    opportunities = engine.scan_all_pairs()

    text = (
        f"📊 <b>Statistical Arbitrage Scanner</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📈 <b>Pairs Analyzed:</b> {fed_pairs}\n"
        f"🔗 <b>Cointegrated Pairs:</b> {len(cointegrated)}\n\n"
    )

    if cointegrated:
        text += "📋 <b>Cointegrated Pairs:</b>\n"
        for c in cointegrated[:5]:
            text += (
                f"   • {c.pair_a}/{c.pair_b}\n"
                f"     p={c.p_value:.4f} | β={c.hedge_ratio:.3f} | "
                f"HL={c.half_life:.0f} | ρ={c.correlation:.2f}\n"
            )
        text += "\n"

    if opportunities:
        text += "🎯 <b>Active Opportunities:</b>\n"
        for opp in opportunities[:5]:
            signal_emoji = "🟢" if 'LONG_A' in opp.signal else "🔴"
            text += (
                f"   {signal_emoji} {opp.pair_a}/{opp.pair_b}\n"
                f"     Signal: <code>{opp.signal}</code>\n"
                f"     Spread Z: <code>{opp.spread_z_score:+.2f}</code> | "
                f"Conf: {opp.confidence:.1%}\n"
                f"     Expected: <code>{opp.expected_profit_pct:+.1f}%</code> | "
                f"HL: {opp.half_life:.0f} candles\n"
            )
    else:
        text += "💤 <i>No active arbitrage opportunities at this time.</i>\n"

    text += (
        f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Cointegration = pairs that revert to equilibrium.\n"
        f"Trade when spread z-score > ±2.0, exit at ±0.5</i>"
    )
    await update.message.reply_text(text, parse_mode='HTML')


# =============================================================================
# HANDLER REGISTRATION
# =============================================================================

def register_quant_handlers(bot, app):
    """Register all quant command handlers with the Telegram app."""
    # Bind commands to bot instance
    async def _quant(update, context):
        await quant_menu_cmd(bot, update, context)

    async def _quant_mr(update, context):
        await quant_mr_cmd(bot, update, context)

    async def _quant_kelly(update, context):
        await quant_kelly_cmd(bot, update, context)

    async def _quant_momentum(update, context):
        await quant_momentum_cmd(bot, update, context)

    async def _quant_perf(update, context):
        await quant_perf_cmd(bot, update, context)

    async def _quant_corr(update, context):
        await quant_corr_cmd(bot, update, context)

    async def _quant_arb(update, context):
        await quant_arb_cmd(bot, update, context)

    app.add_handler(CommandHandler("quant", _quant))
    app.add_handler(CommandHandler("quant_mr", _quant_mr))
    app.add_handler(CommandHandler("quant_kelly", _quant_kelly))
    app.add_handler(CommandHandler("quant_momentum", _quant_momentum))
    app.add_handler(CommandHandler("quant_perf", _quant_perf))
    app.add_handler(CommandHandler("quant_corr", _quant_corr))
    app.add_handler(CommandHandler("quant_arb", _quant_arb))

    async def _quant_risk(update, context):
        await quant_risk_cmd(bot, update, context)

    async def _quant_forecast(update, context):
        await quant_forecast_cmd(bot, update, context)

    async def _quant_frontier(update, context):
        await quant_frontier_cmd(bot, update, context)

    app.add_handler(CommandHandler("quant_risk", _quant_risk))
    app.add_handler(CommandHandler("quant_forecast", _quant_forecast))
    app.add_handler(CommandHandler("quant_frontier", _quant_frontier))

    logger.info("✅ Quant Trading commands registered (10 commands)")

    logger.info("✅ Quant Trading commands registered (7 commands)")


# =============================================================================
# /quant_risk <pair> — CAGR, VaR, CVaR dari return historis harga
# =============================================================================

async def quant_risk_cmd(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show CAGR, VaR (3 methods), CVaR for a pair."""
    args = context.args
    pair = args[0].lower() if args else "btcidr"

    await update.message.reply_text(f"⏳ Menghitung risk metrics untuk <b>{pair.upper()}</b>...", parse_mode='HTML')

    try:
        from quant.risk_metrics import RiskMetrics

        df = bot.historical_data.get(pair)
        if df is None or df.empty or len(df) < 20:
            await update.message.reply_text(f"❌ Data tidak cukup untuk {pair.upper()} (butuh min 20 candle).")
            return

        returns_pct = (df["close"].pct_change().dropna() * 100).tolist()
        if len(returns_pct) < 20:
            await update.message.reply_text("❌ Data return tidak cukup.")
            return

        rm = RiskMetrics(mc_simulations=2000, random_seed=42)
        result = rm.calculate(returns_pct[-200:], confidence=0.95)
        if not result:
            await update.message.reply_text("❌ Gagal menghitung risk metrics.")
            return

        text = (
            f"📊 <b>Risk Metrics — {pair.upper()}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 CAGR: <code>{result.cagr*100:+.2f}%/tahun</code>\n"
            f"📉 Total Return: <code>{result.total_return_pct:+.2f}%</code>\n"
            f"🔢 Observasi: <code>{result.n_trades}</code> candle\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ <b>VaR 95% (per candle)</b>\n"
            f"  Historical : <code>{result.var_historical:.3f}%</code>\n"
            f"  Parametric : <code>{result.var_parametric:.3f}%</code>\n"
            f"  Monte Carlo: <code>{result.var_montecarlo:.3f}%</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔴 <b>CVaR / Expected Shortfall</b>\n"
            f"  Historical : <code>{result.cvar_historical:.3f}%</code>\n"
            f"  Parametric : <code>{result.cvar_parametric:.3f}%</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📐 Mean: <code>{result.mean_return:+.4f}%</code> | "
            f"Std: <code>{result.std_return:.4f}%</code>\n"
            f"Skew: <code>{result.skewness:+.2f}</code> | "
            f"Kurt: <code>{result.kurtosis:+.2f}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>⚠️ Disclaimer: CAGR dan VaR dihitung dari return per-candle harga, "
            f"BUKAN dari return per-trade. CAGR bisa terlihat sangat tinggi karena "
            f"di-annualize dari candle (bukan sesi trading). "
            f"Gunakan sebagai indikator volatilitas, bukan proyeksi profit.</i>"
        )
        await update.message.reply_text(text, parse_mode='HTML')

    except Exception as e:
        logger.error(f"[quant_risk] Error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


# =============================================================================
# /quant_forecast <pair> [steps] — ARIMA price forecast
# =============================================================================

async def quant_forecast_cmd(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ARIMA price forecast for a pair."""
    args = context.args
    pair = args[0].lower() if args else "btcidr"
    steps = int(args[1]) if len(args) > 1 and args[1].isdigit() else 5
    steps = max(1, min(steps, 10))

    await update.message.reply_text(f"⏳ Menghitung ARIMA forecast untuk <b>{pair.upper()}</b>...", parse_mode='HTML')

    try:
        from quant.forecasting import ARIMAModel

        df = bot.historical_data.get(pair)
        if df is None or df.empty or len(df) < 30:
            await update.message.reply_text(f"❌ Data tidak cukup untuk {pair.upper()} (butuh min 30 candle).")
            return

        prices = df["close"].tolist()
        arima = ARIMAModel(p=1, d=1, q=1)
        result = arima.fit_forecast(prices[-100:], steps=steps)
        if not result:
            await update.message.reply_text("❌ Gagal menghitung ARIMA forecast.")
            return

        dir_emoji = {"UP": "📈", "DOWN": "📉", "FLAT": "➡️"}.get(result.direction, "❓")
        forecast_lines = "\n".join(
            f"  +{i+1}: <code>{result.forecast[i]:,.0f}</code> "
            f"[<code>{result.conf_lower[i]:,.0f}</code> – <code>{result.conf_upper[i]:,.0f}</code>]"
            for i in range(len(result.forecast))
        )
        text = (
            f"🔮 <b>ARIMA(1,1,1) Forecast — {pair.upper()}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Harga terakhir: <code>{result.last_price:,.0f}</code> IDR\n"
            f"Forecast +{steps}: <code>{result.forecast_price:,.0f}</code> IDR\n"
            f"Perubahan: <code>{result.expected_change_pct:+.2f}%</code> {dir_emoji}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Detail (95% CI):</b>\n{forecast_lines}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"AIC: <code>{result.aic:.1f}</code> | "
            f"Converged: {'✅' if result.converged else '⚠️'}\n"
            f"<i>⚠️ ARIMA adalah model linear. Gunakan sebagai konfirmasi, bukan sinyal utama.</i>"
        )
        await update.message.reply_text(text, parse_mode='HTML')

    except Exception as e:
        logger.error(f"[quant_forecast] Error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")


# =============================================================================
# /quant_frontier — Efficient Frontier dari semua pair di watchlist
# =============================================================================

async def quant_frontier_cmd(bot, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Markowitz Efficient Frontier dari pair di watchlist."""
    await update.message.reply_text("⏳ Menghitung Efficient Frontier dari watchlist...", parse_mode='HTML')

    try:
        from quant.efficient_frontier import EfficientFrontier

        # Kumpulkan return dari semua pair yang punya data cukup
        returns_matrix = {}
        for pair, df in bot.historical_data.items():
            if df is not None and not df.empty and len(df) >= 20:
                rets = (df["close"].pct_change().dropna() * 100).tolist()
                if len(rets) >= 20:
                    returns_matrix[pair] = rets[-100:]

        if len(returns_matrix) < 2:
            await update.message.reply_text(
                "❌ Butuh minimal 2 pair dengan data cukup di watchlist.\n"
                "Gunakan /watch untuk menambah pair."
            )
            return

        ef = EfficientFrontier(max_weight=0.60)
        result = ef.optimize(returns_matrix)
        if not result:
            await update.message.reply_text("❌ Gagal menghitung Efficient Frontier.")
            return

        # Format individual asset stats
        asset_lines = "\n".join(
            f"  {p}: ret=<code>{result.asset_returns[p]:.1f}%</code> "
            f"vol=<code>{result.asset_vols[p]:.1f}%</code> "
            f"sharpe=<code>{result.asset_sharpes[p]:.2f}</code>"
            for p in result.assets
        )

        # Format max sharpe weights
        ms_lines = "\n".join(
            f"  {p}: <code>{w*100:.1f}%</code>"
            for p, w in sorted(result.max_sharpe.weights.items(), key=lambda x: -x[1])
        )
        mv_lines = "\n".join(
            f"  {p}: <code>{w*100:.1f}%</code>"
            for p, w in sorted(result.min_variance.weights.items(), key=lambda x: -x[1])
        )

        text = (
            f"📊 <b>Efficient Frontier — Markowitz MPT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Individual Asset Stats (annualized)</b>\n{asset_lines}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏆 <b>Max Sharpe Portfolio</b>\n{ms_lines}\n"
            f"  Return: <code>{result.max_sharpe.expected_return:.1f}%</code> | "
            f"Vol: <code>{result.max_sharpe.volatility:.1f}%</code> | "
            f"Sharpe: <code>{result.max_sharpe.sharpe_ratio:.2f}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🛡️ <b>Min Variance Portfolio</b>\n{mv_lines}\n"
            f"  Return: <code>{result.min_variance.expected_return:.1f}%</code> | "
            f"Vol: <code>{result.min_variance.volatility:.1f}%</code> | "
            f"Sharpe: <code>{result.min_variance.sharpe_ratio:.2f}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Frontier dihitung dari {result.n_assets} pair, data {len(list(returns_matrix.values())[0])} candle terakhir.</i>"
        )
        await update.message.reply_text(text, parse_mode='HTML')

    except Exception as e:
        logger.error(f"[quant_frontier] Error: {e}")
        await update.message.reply_text(f"❌ Error: {e}")
