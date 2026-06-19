import sqlite3, subprocess
from datetime import datetime
from pathlib import Path
DB = Path.home() / "advanced_crypto_bot/advanced_crypto_bot/data/trading.db"
VAULT = Path.home() / "obsidian_vault/crypto-bot"
REPORT = Path.home() / "advanced_crypto_bot/advanced_crypto_bot/reports"
c = sqlite3.connect(str(DB))
cr = c.execute("SELECT COUNT(*),SUM(CASE WHEN o.pnl_pct>0 THEN 1 ELSE 0 END),SUM(CASE WHEN o.pnl_pct<0 THEN 1 ELSE 0 END),ROUND(COALESCE(SUM(o.pnl_pct),0),2) FROM trades t LEFT JOIN trade_outcomes o ON o.trade_id=t.id WHERE t.signal_source='auto'").fetchone()
n = c.execute("SELECT COUNT(*),SUM(CASE WHEN o.pnl_pct>0 THEN 1 ELSE 0 END),SUM(CASE WHEN o.pnl_pct<0 THEN 1 ELSE 0 END),ROUND(COALESCE(SUM(o.pnl_pct),0),2) FROM trades t LEFT JOIN trade_outcomes o ON o.trade_id=t.id WHERE t.signal_source='auto' AND t.opened_at >= datetime('now','-24 hours')").fetchone()
pr = c.execute("SELECT t.pair,COUNT(*),SUM(CASE WHEN o.pnl_pct>0 THEN 1 ELSE 0 END),SUM(CASE WHEN o.pnl_pct<0 THEN 1 ELSE 0 END),ROUND(COALESCE(AVG(o.pnl_pct),0),2) FROM trades t LEFT JOIN trade_outcomes o ON o.trade_id=t.id WHERE t.signal_source='auto' GROUP BY t.pair HAVING COUNT(*)>=3 ORDER BY AVG(o.pnl_pct) DESC").fetchall()
op = c.execute("SELECT COUNT(*) FROM trades WHERE status='OPEN'").fetchone()[0]
r = subprocess.run("pgrep -af 'python.*bot.py'|grep -v grep|wc -l",shell=True,capture_output=True,text=True,timeout=5)
pid = int(r.stdout.strip() or 0); c.close()
ts = datetime.now().strftime("%Y-%m-%d_%H%M")
text = f"# Bot Report {ts} WIB\n**Bot:** {'RUNNING' if pid>0 else 'DEAD'} ({pid} proc) | **Open:** {op}\n\n## All-Time\n| Trades | Win | Loss | WR | PnL |\n|---|---|---|---|---|\n| {cr[0]} | {cr[1]} | {cr[2]} | {cr[1]/cr[0]*100:.0f}% | {cr[3]}% |\n\n## 24h\n| Trades | Win | Loss | PnL |\n|---|---|---|---|\n| {n[0]} | {n[1]} | {n[2]} | {n[3]}% |\n\n## Pairs\n| Pair | Trades | W:L | Avg PnL |\n|------|--------|-----|---------|\n"
for p in pr[:5]+pr[-3:]: text += f"| {p[0]} | {p[1]} | {p[2]}:{p[3]} | {p[4]}% |\n"
VAULT.mkdir(parents=True,exist_ok=True); REPORT.mkdir(parents=True,exist_ok=True)
(VAULT/f"bot_{ts}.md").write_text(text); (REPORT/f"bot_{ts}.md").write_text(text)
print(text)
