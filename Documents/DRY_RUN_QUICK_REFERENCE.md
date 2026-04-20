# 🧪 Dry Run Mode - Quick Reference

## Commands

| Command | Description |
|---------|-------------|
| `/autotrade dryrun` | Enable **simulation mode** (no real trades) |
| `/autotrade real` | Enable **real trading** (real money) ⚠️ |
| `/autotrade off` | Disable auto-trading |
| `/autotrade` | Toggle (keeps current mode) |
| `/autotrade_status` | Check status & see dry run trades |

## Configuration

### `.env` File
```env
# true = simulation, false = real trading
AUTO_TRADE_DRY_RUN=true
```

## Key Differences

| Feature | Dry Run 🧪 | Real 🔴 |
|---------|-----------|---------|
| API Calls | ❌ No | ✅ Yes |
| Real Money | ❌ No | ✅ Yes |
| Orders Placed | ❌ No | ✅ Yes |
| P&L Tracking | ✅ Virtual | ✅ Real |
| SL/TP Monitor | ✅ Yes | ✅ Yes |
| Database Records | ✅ Yes | ✅ Yes |
| Order ID Format | `DRY-XXXXXX` | Indodax Order ID |
| Notes in DB | `[DRY RUN]` | Normal |

## Workflow

```
1. /autotrade dryrun
   ↓
2. /watch BTC/IDR
   ↓
3. Wait 5-10 minutes
   ↓
4. /autotrade_status
   ↓
5. Review simulated trades
   ↓
6. Analyze virtual P&L
   ↓
7. Decide: Keep simulating OR /autotrade real
```

## Safety Checklist

Before switching to REAL trading:
- [ ] Run dry run for at least 1-2 weeks
- [ ] Check win rate (>50% recommended)
- [ ] Verify positive virtual P&L
- [ ] Understand SL/TP mechanics
- [ ] Have valid Indodax API keys
- [ ] Start with small amounts

## Log Examples

### Dry Run:
```
🧪 DRY RUN Scanning BTC/IDR for auto-trade opportunity...
🧪 [DRY RUN] Simulated BUY for BTC/IDR: 0.0015 @ 1650000000
```

### Real:
```
🔴 REAL Scanning BTC/IDR for auto-trade opportunity...
✅ Auto-BUY executed for BTC/IDR: 0.0015 @ 1650000000
```
