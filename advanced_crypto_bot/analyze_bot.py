#!/usr/bin/env python3
import sys
import os
import sqlite3

sys.path.insert(0, '/home/officer/advanced_crypto_bot/advanced_crypto_bot')

def analyze_bot_performance():
    db_path = '/home/officer/advanced_crypto_bot/advanced_crypto_bot/trading_bot.db'
    
    if not os.path.exists(db_path):
        print('Database tidak ditemukan!')
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print('=' * 80)
    print('BOT PERFORMANCE ANALYSIS')
    print('=' * 80)
    
    cursor.execute('SELECT COUNT(*) FROM signals')
    total_signals = cursor.fetchone()[0]
    print(f'\nTotal Signals: {total_signals}')
    
    cursor.execute('SELECT recommendation, COUNT(*) FROM signals GROUP BY recommendation')
    print('\nSignal Breakdown:')
    for rec, count in cursor.fetchall():
        pct = (count / total_signals * 100) if total_signals > 0 else 0
        print(f'  {rec}: {count} ({pct:.1f}%)')
    
    cursor.execute('SELECT COUNT(*) FROM trades')
    total_trades = cursor.fetchone()[0]
    print(f'\nTotal Trades: {total_trades}')
    
    if total_trades > 0:
        cursor.execute('SELECT SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END), SUM(CASE WHEN profit_loss < 0 THEN 1 ELSE 0 END) FROM trades WHERE status = "closed"')
        result = cursor.fetchone()
        wins = result[0] or 0
        losses = result[1] or 0
        if wins + losses > 0:
            win_rate = wins / (wins + losses) * 100
            print(f'Win Rate: {win_rate:.1f}% ({wins}W / {losses}L)')
        
        cursor.execute('SELECT SUM(profit_loss) FROM trades WHERE status = "closed"')
        total_pnl = cursor.fetchone()[0] or 0
        print(f'Total P&L: Rp {total_pnl:,.0f}')
    
    cursor.execute('SELECT COUNT(*) FROM positions WHERE status = "open"')
    open_pos = cursor.fetchone()[0]
    print(f'\nOpen Positions: {open_pos}')
    
    conn.close()
    print('=' * 80)

def check_bot_status():
    import subprocess
    result = subprocess.run(['pgrep', '-f', 'bot.py'], capture_output=True)
    if result.returncode == 0:
        print('Bot is RUNNING')
        return True
    else:
        print('Bot is NOT running')
        return False

def main():
    print('\nADVANCED CRYPTO BOT ANALYSIS\n')
    check_bot_status()
    analyze_bot_performance()

if __name__ == '__main__':
    main()
