# 🔴 Real Trading Setup Guide

## How to Enable Real Trading

### 1. Edit `.env`
```ini
AUTO_TRADE_DRY_RUN=false   # Change from 'true' to 'false'
INDODAX_API_KEY=YOUR_KEY_HERE
INDODAX_SECRET_KEY=YOUR_SECRET_HERE
```

### 2. Restart Bot
```bash
python bot.py
```

You should see:
```
🔗 Indodax API connected
🔴 REAL TRADING MODE
```

## What Happens in Real Trading Mode

| Feature | DRY RUN | REAL TRADING |
|---------|---------|--------------|
| Buy/Sell | Local simulation only | ✅ Calls Indodax API |
| Balance | Starts from 10,000,000 IDR | ✅ Syncs from Indodax (every 5 min) |
| TP/SL | Local notification only | ✅ Auto-sells on Indodax |
| Cancel | Removes local TP/SL | ✅ Also cancels order on Indodax |
| Confirmation | Direct execution | ⚠️ **Must confirm** before trade |

## Safety Features

1. **Confirmation Required** - Every buy/sell needs explicit confirmation
2. **Balance Sync** - Auto-syncs from Indodax every 5 minutes
3. **TP/SL Auto-Execute** - Sells automatically when price hits target
4. **Error Logging** - All API failures logged with details
5. **Cancel Order** - `/s_cancel` also cancels pending orders on Indodax

## Commands

All scalper commands use `s_` prefix to avoid conflicts:

```
/s_menu          - Interactive buy/sell buttons
/s_buy           - Manual buy: /s_buy l3idr 375 1000000 400 350
/s_sell          - Sell: /s_sell l3idr 400
/s_sltp          - Set TP/SL: /s_sltp l3idr 400 350
/s_cancel        - Cancel TP/SL + order: /s_cancel l3idr all
/s_info          - Position details: /s_info l3idr
/s_posisi        - All positions + buttons
/s_pair          - Manage pairs: /s_pair add ethidr
/s_reset         - Reset all positions
```

### Auto-Trade Configuration

```
/set_interval <minutes>  - Change scan interval (1-30 min)
/autotrade_status        - Check current interval setting
```

**Examples:**
```bash
/set_interval 1      → Fast scanning (every 1 min)
/set_interval 3      → Balanced (recommended)
/set_interval 5      → Conservative (default)
```

**Note:** You can change the interval anytime without restarting the bot.

## ⚠️ WARNING

- **Real trading uses YOUR money**
- **Start with DRY RUN first** to learn the bot
- **Test with small amounts** before going full scale
- **Always set Stop Loss** to limit losses
- **Monitor positions regularly** via console + Telegram updates
