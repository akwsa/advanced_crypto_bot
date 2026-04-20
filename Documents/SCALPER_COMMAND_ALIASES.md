# Scalper Command Aliases Fix

## Problem
User harus mengetik command dengan prefix `s_` yang lebih panjang:
```bash
/s_buy daridr 213 500000    # Harus pakai 's_'
/s_sell daridr 250          # Harus pakai 's_'
/s_sltp daridr 300 200      # Harus pakai 's_'
```

User mengharapkan bisa pakai command pendek tanpa prefix:
```bash
/buy daridr 213 500000      # ❌ Tidak bekerja sebelumnya
/sell daridr 250            # ❌ Tidak bekerja sebelumnya
```

## Solution
Menambahkan **alias commands** tanpa prefix `s_` untuk kemudahan penggunaan.

## New Commands Added

| Alias Command | Original Command | Function |
|---------------|------------------|----------|
| `/buy` | `/s_buy` | Buy scalper position |
| `/sell` | `/s_sell` | Sell scalper position |
| `/sltp` | `/s_sltp` | Set TP/SL |
| `/posisi` | `/s_posisi` | View active positions |
| `/analisa` | `/s_analisa` | Technical analysis |

## Usage Examples

### Buy Command
```bash
# Both work now!
/buy daridr 213 500000
/s_buy daridr 213 500000
```

**Format:**
```
/buy <pair> <price> <idr_amount> [tp] [sl]
```

**Examples:**
```bash
/buy daridr 213 500000           # Buy without TP/SL
/buy daridr 213 500000 250 200   # Buy with TP=250, SL=200
/buy bridr 8500 2000000          # Buy BRIDR
```

### Sell Command
```bash
# Both work now!
/sell daridr
/s_sell daridr
/sell daridr 250                 # Sell at specific price
```

**Format:**
```
/sell <pair> [price]
```

**Examples:**
```bash
/sell daridr                     # Sell at market price
/sell daridr 250                 # Sell at limit price 250
```

### Set TP/SL
```bash
# Both work now!
/sltp daridr 300 200
/s_sltp daridr 300 200
```

**Format:**
```
/sltp <pair> <take_profit> <stop_loss>
```

**Examples:**
```bash
/sltp daridr 300 200             # Set TP=300, SL=200
/sltp daridr - 200               # Set SL only
/sltp daridr 300 -               # Set TP only
```

### View Positions
```bash
# Both work now!
/posisi
/s_posisi
```

### Technical Analysis
```bash
# Both work now!
/analisa daridr
/s_analisa daridr
```

## Implementation Details

### File Modified: `scalper_module.py`

```python
def _register_handlers(self):
    # Primary scalper commands (with s_ prefix)
    self.app.add_handler(CommandHandler("s_buy", self.cmd_buy))
    self.app.add_handler(CommandHandler("s_sell", self.cmd_sell))
    self.app.add_handler(CommandHandler("s_sltp", self.cmd_sltp))
    self.app.add_handler(CommandHandler("s_cancel", self.cmd_cancel))
    self.app.add_handler(CommandHandler("s_info", self.cmd_info))
    self.app.add_handler(CommandHandler("s_pair", self.cmd_pair))
    self.app.add_handler(CommandHandler("s_posisi", self.cmd_posisi))
    self.app.add_handler(CommandHandler("s_reset", self.cmd_reset))
    self.app.add_handler(CommandHandler("s_analisa", self.cmd_analisa))
    self.app.add_handler(CommandHandler("s_menu", self.cmd_menu))
    self.app.add_handler(CommandHandler("s_sync", self.cmd_sync))
    self.app.add_handler(CommandHandler("s_portfolio", self.cmd_portfolio))
    self.app.add_handler(CommandHandler("s_riwayat", self.cmd_riwayat))
    
    # Aliases for convenience (no 's_' prefix needed)
    # Note: Skip 'menu' as it conflicts with main bot's /menu command
    self.app.add_handler(CommandHandler("buy", self.cmd_buy))
    self.app.add_handler(CommandHandler("sell", self.cmd_sell))
    self.app.add_handler(CommandHandler("sltp", self.cmd_sltp))
    self.app.add_handler(CommandHandler("posisi", self.cmd_posisi))
    self.app.add_handler(CommandHandler("analisa", self.cmd_analisa))
```

## Commands NOT Aliased

Some commands are intentionally NOT aliased to avoid conflicts:

| Command | Reason |
|---------|--------|
| `/menu` | Already exists in main bot |
| `/pair` | Too generic, might conflict |
| `/reset` | Too dangerous without prefix |
| `/cancel` | Already exists in main bot |
| `/info` | Too generic |
| `/sync` | Already exists in main bot |
| `/portfolio` | Too long, not commonly used |
| `/riwayat` | Indonesian specific, keep with prefix |

## Backward Compatibility

✅ **All original `s_` commands still work**
- `/s_buy`, `/s_sell`, etc. remain functional
- No breaking changes

✅ **Same handlers**
- Both `/buy` and `/s_buy` call `cmd_buy()`
- Same validation, same logic

## Testing Checklist

- [x] `/buy daridr 213 500000` works ✅
- [x] `/s_buy daridr 213 500000` still works ✅
- [x] `/sell daridr` works ✅
- [x] `/s_sell daridr` still works ✅
- [x] `/sltp daridr 300 200` works ✅
- [x] `/posisi` shows positions ✅
- [x] `/analisa daridr` shows analysis ✅
- [x] No conflicts with main bot commands ✅
- [x] Syntax validation passes ✅

## Benefits

### 1. **Faster Typing** ⚡
- `/buy` vs `/s_buy` - 3 characters saved
- Less typing on mobile devices

### 2. **More Intuitive** 🎯
- Users naturally try `/buy` first
- No need to remember `s_` prefix

### 3. **Consistent UX** ✅
- Both versions work identically
- No learning curve

### 4. **Backward Compatible** 🛡️
- Old commands still work
- No breaking changes

## Common Workflows

### Quick Buy & Sell
```bash
# Old way (still works)
/s_buy daridr 213 500000
/s_sell daridr

# New way (faster!)
/buy daridr 213 500000
/sell daridr
```

### Set TP/SL After Buy
```bash
/buy daridr 213 500000
/sltp daridr 250 200
```

### Check Position
```bash
/posisi
/analisa daridr
```

## Related Files

- `scalper_module.py` - Main file modified
- `SCALPER_BUTTON_FIX.md` - Related button fix
- `AUTO_ADD_SCALPER_FEATURE.md` - Related auto-add feature
