# 🌅 TOMORROW MORNING CHECKLIST

**Date**: 2026-04-15 (besok pagi)
**Purpose**: Verify signal fixes are working

---

## ✅ QUICK CHECKS (5 minutes)

### 1. Check Bot is Running
```bash
# Check if bot process is running
tasklist | findstr python

# OR check Telegram - send /status command
```
**Expected**: Bot responds with status

### 2. Check for BUY Signals in Logs
```bash
# Check recent signals
grep "\[FINAL\].*BUY" logs/trading_bot.log | tail -20

# Check if STRONG_BUY signals appear
grep "\[FINAL\].*STRONG_BUY" logs/trading_bot.log | tail -10

# Check stabilization events
grep "\[STABILIZE\]" logs/trading_bot.log | tail -20
```

**Expected Results**:
- ✅ More BUY signals than before
- ✅ Some STRONG_BUY signals appearing
- ✅ Fewer stabilization downgrades

### 3. Check Signal Distribution
```bash
# Count signals by type (last 100 signals)
grep "\[FINAL\]" logs/trading_bot.log | tail -100 | sort | uniq -c | sort -rn
```

**Expected Distribution**:
- HOLD: ~40%
- BUY: ~25%
- SELL: ~20%
- STRONG_BUY: ~15%

**If still mostly HOLD/SELL**: See troubleshooting below

---

## 🔍 TELEGRAM CHECKS

### 4. Check Bot Status
Send in Telegram:
```
/status
```
**Expected**: Bot responds with system status

### 5. Check Auto-Trade Mode
Send in Telegram:
```
/autotrade_status
```
**Expected**: Shows DRY RUN mode active

### 6. Test Signal Generation
Send in Telegram:
```
/signal BTCIDR
```
**Expected**: Returns BUY/SELL/HOLD signal with details

### 7. Check Recent Signals
Send in Telegram:
```
/signals
```
**Expected**: Shows recent signal history

---

## 🐛 TROUBLESHOOTING

### Problem: Still mostly HOLD signals
**Possible causes**:
1. Market conditions actually neutral (normal)
2. ML model needs retraining

**Solutions**:
```bash
# Retrain ML model manually
# Send in Telegram:
/retrain
```

### Problem: Still no BUY signals
**Check**:
1. ML confidence distribution in logs
2. TA signal strengths
3. Combined strength values

**Commands**:
```bash
# Check ML confidence
grep "ML Confidence" logs/trading_bot.log | tail -20

# Check TA strength
grep "TA Strength" logs/trading_bot.log | tail -20

# Check combined strength
grep "Combined Strength" logs/trading_bot.log | tail -20
```

**If ML confidence < 0.55**: Signals become HOLD (by design)
**If TA strength near 0**: Market is neutral (normal)

### Problem: Too many STRONG_BUY downgraded to BUY
**Check stabilization logs**:
```bash
grep "\[STABILIZE\]" logs/trading_bot.log | tail -20
```

**If too many downgrades**: May need to relax thresholds further

---

## 📊 REDIS CHECKS

### 8. Check Redis Connections
```bash
# Test Redis connection
redis-cli ping

# Expected: PONG
```

### 9. Check Signal Queue
```bash
# Check queued signals
redis-cli zcard signal_queue:signals

# Check signal stats
redis-cli keys "signal_queue:stats:*"
```

---

## 🎯 SUCCESS CRITERIA

✅ **Fix is working if**:
- More BUY signals appear (at least 20-30% of signals)
- STRONG_BUY signals not immediately downgraded
- Signal distribution more balanced
- User reports more actionable signals

❌ **Fix needs adjustment if**:
- Still 90%+ HOLD signals
- No BUY signals after 2+ hours
- All STRONG_BUY downgraded to BUY
- User reports no improvement

---

## 📝 LOG COMMANDS

### Monitor logs in real-time
```bash
# Watch logs live
tail -f logs/trading_bot.log | grep -i "signal\|buy\|sell"

# Filter for final signals
tail -f logs/trading_bot.log | grep "\[FINAL\]"

# Filter for stabilization
tail -f logs/trading_bot.log | grep "\[STABILIZE\]"
```

### Check error logs
```bash
# Check for errors
grep -i "error\|exception\|failed" logs/trading_bot.log | tail -20

# Check Redis errors
grep -i "redis.*error\|redis.*fail" logs/trading_bot.log | tail -10
```

---

## 📞 IF ISSUES FOUND

### Document the issue:
1. What signal distribution you see (% HOLD/BUY/SELL)
2. Sample logs (last 50 signals)
3. Telegram bot response to /signal command
4. Any error messages in logs

### Share findings:
- Save to: `SIGNAL_FIX_FEEDBACK_2026-04-15.md`
- Include: Logs, screenshots, signal counts

---

## ✅ CHECKLIST

- [ ] Bot is running (check /status)
- [ ] BUY signals appearing in logs
- [ ] Signal distribution improved
- [ ] Redis connections working
- [ ] No errors in logs
- [ ] Telegram commands responsive
- [ ] User reports better signals

**If all ✅**: Fix is successful, continue monitoring
**If any ❌**: Document issue, adjust thresholds if needed

---

**Good luck besok pagi! 🚀**
