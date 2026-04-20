================================================================================
🤖 ADVANCED CRYPTO TRADING BOT - COMPLETE COMMAND REFERENCE
================================================================================
Generated: April 07, 2026 at 07:04
Bot: Indodax + Telegram + Machine Learning + Scalper Module
⚠️ AUTO-GENERATED - DO NOT EDIT MANUALLY
   Run: python generate_docs.py to regenerate
================================================================================

📋 TABLE OF CONTENTS:
1. Bot Commands - Watchlist & Monitoring
2. Bot Commands - Trading & Portfolio
3. Bot Commands - Auto Trading & Admin
   - Auto-Trade Configuration (/set_interval)
4. Scalper Commands - Buy/Sell
5. Scalper Commands - Position Management
6. Scalper Commands - Analysis & Info
7. Scalper Commands - Pair Management
8. Quick Reference - Common Workflows
9. Important Notes & Tips
10. Troubleshooting

================================================================================
1️⃣ BOT COMMANDS - WATCHLIST & MONITORING
================================================================================

/watch
    ➤ Subscribe to real-time updates for one or more pairs
    ➤ Method: watch
    ➤ Supports multiple pairs: /watch btcidr, ethidr, solidr
    ➤ Auto-add to scalper list

/unwatch
    ➤ Unsubscribe from one or more pairs
    ➤ Method: unwatch
    ➤ Supports multiple pairs: /unwatch btcidr, ethidr, solidr
    ➤ Auto-add to scalper list

/list
    ➤ Show user's watchlist
    ➤ Method: list_watch

/price
    ➤ Quick price check for a pair
    ➤ Method: price

/monitor
    ➤ Show monitored positions with SL/TP levels
    ➤ Method: monitor

================================================================================
2️⃣ BOT COMMANDS - TRADING & PORTFOLIO
================================================================================

/signal
    ➤ Generate and send trading signal for a pair
    ➤ Method: get_signal

/signals
    ➤ Show trading signals for all watched pairs
    ➤ Method: signals

/position
    ➤ Analyze open position for a pair with order book analysis
    ➤ Method: position

/balance
    ➤ Show portfolio balance and positions
    ➤ Method: balance

/trades
    ➤ Show trade history
    ➤ Method: trades

/performance
    ➤ Show trading performance metrics
    ➤ Method: performance

/sync
    ➤ Sync trade history from Indodax API to database
    ➤ Method: sync_trades

================================================================================
3️⃣ BOT COMMANDS - AUTO TRADING & ADMIN
================================================================================

/autotrade
    ➤ Toggle auto-trading ON/OFF with status check
    ➤ Method: autotrade

/autotrade_status
    ➤ Show detailed auto-trading status and history
    ➤ Method: autotrade_status

/status
    ➤ Enhanced admin status command
    ➤ Method: status

/retrain
    ➤ Manually retrain ML model (admin only)
    ➤ Method: retrain_ml

/hunter_status
    ➤ Show Smart Hunter bot status
    ➤ Method: hunter_status

/ultrahunter
    ➤ Ultra Conservative Hunter control command
    ➤ Method: ultra_hunter_cmd

/trade
    ➤ Execute manual trade via Indodax API
    ➤ Method: trade

/cancel
    ➤ Cancel a pending or open order
    ➤ Method: cancel_trade

/set_sl
    ➤ Set custom stop loss percentage
    ➤ Method: set_stoploss

/set_tp
    ➤ Set custom take profit percentage
    ➤ Method: set_takeprofit

/set_interval
    ➤ Change auto-trade check interval (1-30 minutes)
    ➤ Method: set_interval
    ➤ Usage: /set_interval <minutes>
    ➤ Presets: 1=Fast, 2=Medium-fast, 3=Balanced, 5=Conservative

================================================================================
4️⃣ SCALPER COMMANDS - BUY/SELL
================================================================================

/buy
    ➤ Buy position for scalper pair with optional TP/SL
    ➤ Method: cmd_buy
    ➤ Also available as: /s_buy

/sell
    ➤ Sell scalper position at market or limit price
    ➤ Method: cmd_sell
    ➤ Also available as: /s_sell

/s_buy
    ➤ Buy position for scalper pair with optional TP/SL
    ➤ Method: cmd_buy
    ➤ Alias: /buy

/s_sell
    ➤ Sell scalper position at market or limit price
    ➤ Method: cmd_sell
    ➤ Alias: /sell

================================================================================
5️⃣ SCALPER COMMANDS - POSITION MANAGEMENT
================================================================================

/posisi
    ➤ Lihat SEMUA pair scalper: yang ada posisi + yang hanya di-monitor
    ➤ Method: cmd_posisi
    ➤ Also available as: /s_posisi

/sltp
    ➤ Set or update Take Profit / Stop Loss for scalper position
    ➤ Method: cmd_sltp
    ➤ Also available as: /s_sltp

/s_posisi
    ➤ Lihat SEMUA pair scalper: yang ada posisi + yang hanya di-monitor
    ➤ Method: cmd_posisi
    ➤ Alias: /posisi

/s_sltp
    ➤ Set or update Take Profit / Stop Loss for scalper position
    ➤ Method: cmd_sltp
    ➤ Alias: /sltp

/s_cancel
    ➤ Cancel TP, SL, or pending order for scalper position
    ➤ Method: cmd_cancel
    ➤ Alias: /cancel

================================================================================
6️⃣ SCALPER COMMANDS - ANALYSIS & INFO
================================================================================

/analisa
    ➤ Analisa pair dengan technical indicators seperti bot utama
    ➤ Method: cmd_analisa
    ➤ Also available as: /s_analisa

/s_analisa
    ➤ Analisa pair dengan technical indicators seperti bot utama
    ➤ Method: cmd_analisa
    ➤ Alias: /analisa

/s_info
    ➤ Show detailed info for specific scalper position
    ➤ Method: cmd_info
    ➤ Alias: /info

================================================================================
7️⃣ SCALPER COMMANDS - PAIR MANAGEMENT
================================================================================

/s_pair
    ➤ Lihat SEMUA pair scalper: yang ada posisi + yang hanya di-monitor
    ➤ Method: cmd_pair
    ➤ Alias: /pair

================================================================================
8️⃣ QUICK REFERENCE - COMMON WORKFLOWS
================================================================================

See examples in code comments and method docstrings.

================================================================================
9️⃣ IMPORTANT NOTES & TIPS
================================================================================

💡 GENERAL TIPS:
    • Always test with /autotrade dryrun first
    • Watched pairs auto-add to scalper list
    • Both /buy and /s_buy work identically
    • Use /analisa before entry for technical analysis

⚠️ RISK MANAGEMENT:
    • Max position size: 25% of balance
    • Recommended stop-loss: 2% per trade
    • Recommended take-profit: 5% per trade
    • Max trades per day: 10
    • Daily loss limit: 5%

================================================================================
🔟 TROUBLESHOOTING
================================================================================

Q: Command not found
A: Restart bot after adding new commands

Q: Pair not found on Indodax
A: Verify pair name is correct (e.g., 'btcidr' not 'btc')

================================================================================
📌 VERSION HISTORY
================================================================================

v2026.04 - Auto-generated documentation
Generated: April 07, 2026 at 07:04

================================================================================
END OF DOCUMENTATION
================================================================================