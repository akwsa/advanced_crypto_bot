#!/usr/bin/env python3
"""Read-only diagnosis: why no new autotrade dry-run activity?
Prints funnel evidence from data/trading.db + log tails. No writes, no secrets."""
import os, sqlite3, sys, datetime

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(APP, "data", "trading.db")

def q(c, sql, args=()):
    try:
        return c.execute(sql, args).fetchall()
    except Exception as e:
        return [("ERR", str(e)[:120])]

print("=" * 64)
print("AUTOTRADE STALL DIAGNOSIS -", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("=" * 64)
if not os.path.exists(DB):
    print("FATAL: DB not found:", DB); sys.exit(1)
c = sqlite3.connect("file:%s?mode=ro" % DB, uri=True)

# --- 0) timestamp format probe ---
t = q(c, "SELECT DISTINCT typeof(created_at) FROM autotrade_intents LIMIT 3")
print("\n[0] intent.created_at types:", t)
mx = q(c, "SELECT MAX(created_at), MIN(created_at), COUNT(*) FROM autotrade_intents")
print("[0] intents: max=%s min=%s total=%s" % (mx[0][0], mx[0][1], mx[0][2]))

# --- 1) daily intent volume (when did it stop?) ---
print("\n[1] intents per day (last 14 days with any intent):")
rows = q(c, "SELECT substr(created_at,1,10) d, COUNT(*), MAX(substr(created_at,1,16)) FROM autotrade_intents GROUP BY d ORDER BY d DESC LIMIT 14")
for r in rows: print("   ", r)

# --- 2) funnel since cutoff = 7 days ago ---
cut = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
print("\n[2] decision funnel since %s:" % cut)
for r in q(c, "SELECT status, reason_code, recommendation, COUNT(*) FROM autotrade_intents WHERE created_at >= ? GROUP BY status, reason_code, recommendation ORDER BY 4 DESC LIMIT 25", (cut,)):
    print("   ", r)

# --- 3) all-time status breakdown ---
print("\n[3] all-time intents by status:")
for r in q(c, "SELECT status, COUNT(*) FROM autotrade_intents GROUP BY status ORDER BY 2 DESC"):
    print("   ", r)

# --- 4) last 5 intents raw (format + recency proof) ---
print("\n[4] latest 5 intents (pair, rec, status, reason_code, created_at):")
for r in q(c, "SELECT pair, recommendation, status, reason_code, created_at FROM autotrade_intents ORDER BY id DESC LIMIT 5"):
    print("   ", r)

# --- 5) orders / fills / positions ---
print("\n[5] orders:", q(c, "SELECT COUNT(*), MAX(created_at) FROM autotrade_orders")[0])
print("    fills :", q(c, "SELECT COUNT(*), MAX(filled_at) FROM autotrade_fills")[0])
print("    positions by status:", q(c, "SELECT status, COUNT(*) FROM autotrade_positions GROUP BY status"))
for r in q(c, "SELECT pair, quantity, avg_price, status, updated_at FROM autotrade_positions WHERE status='OPEN' LIMIT 10"):
    print("    OPEN pos:", r)

# --- 6) legacy trades ---
print("\n[6] legacy trades: total, by signal_source:")
for r in q(c, "SELECT signal_source, status, COUNT(*) FROM trades GROUP BY signal_source, status ORDER BY 3 DESC LIMIT 12"):
    print("   ", r)
print("    last 5 trades (pair, opened_at, status, notes[:40]):")
for r in q(c, "SELECT pair, opened_at, status, substr(COALESCE(notes,''),1,40) FROM trades ORDER BY id DESC LIMIT 5"):
    print("   ", r)
print("    OPEN legacy positions:")
for r in q(c, "SELECT id, pair, price, opened_at FROM trades WHERE status='OPEN' OR profit_loss IS NULL ORDER BY id DESC LIMIT 10"):
    print("   ", r)

# --- 7) circuit breaker / cash state ---
print("\n[7] drawdown_state:", q(c, "SELECT user_id, equity_peak, last_updated FROM drawdown_state"))
cols = [r[1] for r in q(c, "PRAGMA table_info(users)")]
if isinstance(cols, list) and cols and cols[0] != "ERR":
    want = [x for x in ("balance", "is_trading") if x in cols]
    if want:
        print("    users:", q(c, "SELECT %s FROM users LIMIT 3" % ",".join(want)))
else:
    print("    users table: not readable:", cols)

# --- 8) strategy2 shadow activity ---
print("\n[8] strategy2_decisions:", q(c, "SELECT COUNT(*) FROM strategy2_decisions")[0])

# --- 9) recent runtime evidence from logs ---
print("\n[9] log scan (last matches, markers of pipeline life):")
MARK = "Signal queued|Processing signal|DRYRUN_FILL|NO_ENTRY|Decision|Traceback|Telegram Conflict|ERROR"
for lf in ("logs/bot.log", "logs/trading_bot.log"):
    p = os.path.join(APP, lf)
    if not os.path.exists(p):
        print("    (no %s)" % lf); continue
    sz = os.path.getsize(p)
    with open(p, "rb") as f:
        f.seek(max(0, sz - 400000)); blob = f.read().decode("utf-8", "ignore")
    hits = [l for l in blob.splitlines() if any(m in l for m in MARK.split("|"))]
    print("    -- %s (%d bytes, %d marker hits, last 15):" % (lf, sz, len(hits)))
    for l in hits[-15:]: print("      ", l[:160])

c.close()
print("\nDONE - paste ALL output back.")
