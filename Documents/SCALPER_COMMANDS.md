# 📋 Scalper Module - Command Reference

## Commands (prefix `s_` to avoid conflict with main bot)

### Trading
| Command | Format | Example |
|---------|--------|---------|
| `/s_menu` | Interactive buy/sell buttons | `/s_menu` |
| `/s_buy` | Manual buy with optional TP/SL | `/s_buy l3idr 375 1000000 400 350` |
| `/s_sell` | Sell position | `/s_sell l3idr 400` or `/s_sell l3idr` (market price) |
| `/s_sltp` | Set TP/SL | `/s_sltp l3idr 400 350` or `/s_sltp l3idr - 350` (SL only) |
| `/s_cancel` | Cancel TP/SL | `/s_cancel l3idr sl` or `/s_cancel l3idr all` |
| `/s_info` | Position details | `/s_info l3idr` |
| `/s_posisi` | All positions with buttons | `/s_posisi` |

### Management
| Command | Format | Example |
|---------|--------|---------|
| `/s_pair` | Manage pairs | `/s_pair add ethidr`, `/s_pair list`, `/s_pair reset` |
| `/s_reset` | Reset all positions | `/s_reset` |

## Features
- ✅ DRY RUN by default (safe simulation)
- ✅ Real trading mode when `AUTO_TRADE_DRY_RUN=false` in `.env`
- ✅ Average down (buy same pair = merge positions)
- ✅ Auto TP/SL monitoring (every 5 sec)
- ✅ Telegram alerts when profit ≥3%
- ✅ Position persistence (JSON file)
- ✅ Auto-add pair when bought

## Safety
- Real trading requires **confirmation button** before execute
- TP/SL auto-sell **blocked** in real trading mode (safety)
- Balance tracked locally (sync with Indodax planned for future)
