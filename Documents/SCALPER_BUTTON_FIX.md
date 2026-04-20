# Scalper Button Handler Fix

## Problem
Beberapa button di scalper menu tidak merespons karena tidak ada handler-nya di `menu_callback`:

- ❌ `s_analisa_hint` - Button untuk info analisa pair
- ❌ `s_close_all_confirm` - Button untuk konfirmasi close all positions  
- ❌ `s_confirm_close_all` - Button eksekusi close all
- ❌ `s_refresh_portfolio` - Button refresh portfolio view

## Solution
Menambahkan handler untuk semua button yang belum terhandle di `menu_callback()`.

### Handlers Added

#### 1. `s_analisa_hint`
Menampilkan panduan cara menggunakan fitur analisa teknikal:

```
📈 **Analisa Pair**

Ketik: `/s_analisa <pair>`
Contoh: `/s_analisa btcidr`

Menampilkan:
• RSI, MACD, Moving Average
• Bollinger Bands
• Volume analysis
• Support & Resistance

💡 Gunakan sebelum entry untuk analisa teknikal lengkap!
```

#### 2. `s_close_all_confirm`
Menampilkan dialog konfirmasi sebelum close all positions:

```
⚠️ **CONFIRMATION**

Tutup SEMUA posisi aktif?

Jumlah posisi: 3

Tindakan ini tidak bisa dibatalkan!

[⚠️ YES, Close ALL Positions] [❌ Cancel]
```

#### 3. `s_confirm_close_all`
Method baru: `_execute_close_all_positions(query)`

**Fungsi:**
- Iterate semua posisi aktif
- Sell semua posisi di harga market saat ini
- Hitung total P/L
- Update saldo
- Tampilkan summary lengkap

**Example Output:**
```
🔄 Menutup 3 posisi...

🟢 **BTCIDR**: `+50,000 IDR` (`+2.5%`)
🔴 **ETHIDR**: `-20,000 IDR` (`-1.0%`)
🟢 **BRIDR**: `+30,000 IDR` (`+3.2%`)

✅ **CLOSE ALL COMPLETE** (DRY RUN)
• Closed: 3
• Total P/L: `+60,000 IDR`
• Saldo: `10,060,000 IDR`
```

**Features:**
- ✅ Support DRY RUN dan REAL trading mode
- ✅ Graceful error handling per position
- ✅ Summary dengan P/L detail
- ✅ Safe iteration (copy list before modifying)
- ✅ Indodax API integration untuk real trading

#### 4. `s_refresh_portfolio`
Handler untuk refresh portfolio callback (sudah ada method `refresh_portfolio_callback`, tinggal di-link).

## Code Changes

### File: `scalper_module.py`

#### 1. Added handlers in `menu_callback()`:

```python
if query.data == 's_analisa_hint':
    await query.edit_message_text(
        "📈 **Analisa Pair**\n\n"
        "Ketik: `/s_analisa <pair>`\n"
        "Contoh: `/s_analisa btcidr`\n\n"
        "Menampilkan:\n"
        "• RSI, MACD, Moving Average\n"
        "• Bollinger Bands\n"
        "• Volume analysis\n"
        "• Support & Resistance\n\n"
        "💡 Gunakan sebelum entry untuk analisa teknikal lengkap!",
        parse_mode='Markdown'
    )
    return

if query.data == 's_close_all_confirm':
    keyboard = [
        [InlineKeyboardButton("⚠️ YES, Close ALL Positions", callback_data="s_confirm_close_all")],
        [InlineKeyboardButton("❌ Cancel", callback_data="s_cancel_action")]
    ]
    await query.edit_message_text(
        "⚠️ **CONFIRMATION**\n\n"
        "Tutup SEMUA posisi aktif?\n\n"
        f"Jumlah posisi: {len(self.active_positions)}\n\n"
        "Tindakan ini tidak bisa dibatalkan!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return

if query.data == 's_confirm_close_all':
    await self._execute_close_all_positions(query)
    return

if query.data == 's_refresh_portfolio':
    await self.refresh_portfolio_callback(update, context)
    return
```

#### 2. Added new method `_execute_close_all_positions()`:

```python
async def _execute_close_all_positions(self, query):
    """Close all active positions at current market price"""
    if not self.active_positions:
        await query.edit_message_text("ℹ️ Tidak ada posisi aktif untuk ditutup")
        return

    total_positions = len(self.active_positions)
    closed_count = 0
    failed_count = 0
    total_pnl = 0
    
    summary_msg = f"🔄 Menutup {total_positions} posisi...\n\n"
    
    # Create a copy to avoid modification during iteration
    positions_to_close = list(self.active_positions.items())
    
    for pair, pos in positions_to_close:
        try:
            # Get current price
            loop = asyncio.get_running_loop()
            price = await loop.run_in_executor(None, lambda p=pair: self._get_price_sync(p))
            
            # Calculate P/L
            pnl_pct = ((price * (1-ScalperConfig.TRADING_FEE_PCT) - pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT)) / (pos['entry'] * (1+ScalperConfig.TRADING_FEE_PCT))) * 100
            profit_idr = (price * pos['amount']) * (1 - ScalperConfig.TRADING_FEE_PCT) - pos['capital']
            total_pnl += profit_idr
            
            if self.is_real_trading and self.indodax:
                # REAL: Execute sell via Indodax API
                amount = pos['amount']
                result = self.indodax.create_order(pair, 'sell', price, amount)
                if result and result.get('success'):
                    self.balance += profit_idr + pos['capital']
                    del self.active_positions[pair]
                    closed_count += 1
                    emoji = "🟢" if profit_idr >= 0 else "🔴"
                    summary_msg += f"{emoji} **{pair.upper()}**: `{profit_idr:+,.0f} IDR` (`{pnl_pct:+.1f}%`)\n"
                else:
                    failed_count += 1
                    summary_msg += f"❌ **{pair.upper()}**: Gagal sell\n"
            else:
                # DRY RUN
                self.balance += profit_idr + pos['capital']
                del self.active_positions[pair]
                closed_count += 1
                emoji = "🟢" if profit_idr >= 0 else "🔴"
                summary_msg += f"{emoji} **{pair.upper()}**: `{profit_idr:+,.0f} IDR` (`{pnl_pct:+.1f}%`)\n"
                
        except Exception as e:
            failed_count += 1
            summary_msg += f"❌ **{pair.upper()}**: Error - {str(e)[:50]}\n"
    
    # Save updated positions
    self._save_positions()
    
    # Add summary
    mode_str = "REAL" if self.is_real_trading else "DRY RUN"
    summary_msg += f"\n✅ **CLOSE ALL COMPLETE** ({mode_str})"
    summary_msg += f"\n• Closed: {closed_count}"
    if failed_count > 0:
        summary_msg += f"\n• Failed: {failed_count}"
    summary_msg += f"\n• Total P/L: `{total_pnl:+,.0f} IDR`"
    summary_msg += f"\n• Saldo: `{self.balance:,.0f} IDR`"
    
    await query.edit_message_text(summary_msg, parse_mode='Markdown')
```

## Testing Checklist

- [x] Button `s_analisa_hint` → Shows help text ✅
- [x] Button `s_close_all_confirm` → Shows confirmation dialog ✅
- [x] Button `s_confirm_close_all` → Executes close all ✅
- [x] Button `s_refresh_portfolio` → Refreshes portfolio view ✅
- [x] Syntax validation passes ✅
- [x] DRY RUN mode tested ✅
- [x] REAL trading mode supported ✅
- [x] Error handling per position ✅
- [x] Safe list iteration ✅

## Buttons Now Working

| Button | Handler | Status |
|--------|---------|--------|
| `s_buy:<pair>` | `_execute_buy()` | ✅ Working |
| `s_sell:<pair>` | `_execute_sell()` | ✅ Working |
| `s_confirm_buy:<pair>:<capital>` | `_execute_confirmed_buy()` | ✅ Working |
| `s_confirm_sell:<pair>:<price>` | `_execute_confirmed_sell()` | ✅ Working |
| `s_cancel_action` | Inline in handler | ✅ Working |
| `s_add_pair_hint` | Inline in handler | ✅ Working |
| `s_analisa_hint` | Inline in handler | ✅ **FIXED** |
| `s_close_all_confirm` | Inline in handler | ✅ **FIXED** |
| `s_confirm_close_all` | `_execute_close_all_positions()` | ✅ **FIXED** |
| `s_refresh_posisi` | `refresh_posisi_callback()` | ✅ Working |
| `s_refresh_prices` | `refresh_prices_callback()` | ✅ Working |
| `s_refresh_portfolio` | `refresh_portfolio_callback()` | ✅ **FIXED** |
| `s_info:<pair>` | Inline in handler | ✅ Working |

## Related Files

- `scalper_module.py` - Main file modified
- `AUTO_ADD_SCALPER_FEATURE.md` - Related scalper feature
- `INVALID_PAIR_BLACKLIST_FIX.md` - Related invalid pair handling

## Impact

✅ Semua button di scalper menu sekarang responsif  
✅ User bisa close all positions dengan aman  
✅ Panduan analisa pair tersedia  
✅ Portfolio refresh bekerja dengan baik  
