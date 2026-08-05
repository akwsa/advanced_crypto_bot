#!/usr/bin/env python3
"""Quick trade report — run: venv/bin/python3 scripts/trade_report.py"""
import sqlite3, sys, os

db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'trading.db')
if len(sys.argv) > 1:
    db_path = sys.argv[1]

c = sqlite3.connect(db_path)
c.row_factory = sqlite3.Row

rows = c.execute(
    "SELECT t.id, t.pair, t.price, t.original_total, t.profit_loss, t.notes, "
    "o.pnl_pct, o.exit_price, o.hold_duration_minutes "
    "FROM trades t LEFT JOIN trade_outcomes o ON o.trade_id = t.id "
    "WHERE t.signal_source = 'auto' ORDER BY t.id DESC LIMIT 30"
).fetchall()

wins = losses = 0
total_pnl = 0.0

for r in rows:
    pp = r['pnl_pct'] or 0
    pr = r['profit_loss'] or 0
    if pp > 0:
        wins += 1
    elif pp < 0:
        losses += 1
    total_pnl += pr
    n = r['notes'] or ''
    if 'STOP_LOSS' in n:
        bl = 'SL'
    elif 'TAKE_PROFIT' in n:
        bl = 'TP'
    elif 'TRAILING' in n:
        bl = 'TR'
    elif 'TIME_EXIT' in n:
        bl = 'TE'
    elif 'STRONG_SELL' in n:
        bl = 'SE'
    elif r['pnl_pct'] is None:
        bl = 'OP'
    else:
        bl = '??'
    hd = r['hold_duration_minutes'] or 0
    print(f"#{r['id']:>4d} {r['pair']:>15s} PnL:{pp:>+6.2f}% Rp{pr:>+10,.0f} {bl} hold:{hd:.0f}m")

closed = wins + losses
wr = wins / closed * 100 if closed > 0 else 0
print(f"\nLast {len(rows)} trades: {wins}W/{losses}L WR={wr:.0f}% Net=Rp{total_pnl:>+12,.0f}")
c.close()
