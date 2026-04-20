# Invalid Pair Blacklist Fix

## Problem
Saat user menambahkan pair yang salah/tidak ada di Indodax (misalnya `croackidr`), bot akan **terus-menerus mencoba** setiap 10 detik dengan pesan error berulang:

```
❌ Failed to get ticker for croackidr after 3 attempts
⚠️ No ticker data for croackidr
❌ Failed to get ticker for croackidr after 3 attempts
⚠️ No ticker data for croackidr
... (terus berulang selamanya)
```

## Solution
Implementasi **blacklist otomatis** untuk pair yang invalid:

### 1. **Failure Tracking**
- Setiap pair yang gagal di-track dalam dictionary `pair_fail_count`
- Setelah **2 kali gagal berturut-turut**, pair otomatis di-blacklist
- Counter di-reset jika pair berhasil di-fetch

### 2. **Automatic Blacklisting**
```python
# Di PricePoller.__init__
self.invalid_pairs = set()  # Blacklist pair invalid
self.max_invalid_attempts = 2  # Max 2x gagal → blacklist
self.pair_fail_count = {}  # Track failure per pair
```

### 3. **Skip Blacklisted Pairs**
Sebelum polling cycle, pair yang sudah di-blacklist otomatis diskip:

```python
valid_pairs = all_pairs - self.invalid_pairs
filtered_pairs = all_pairs - valid_pairs

if filtered_pairs:
    logger.info(f"⏭️ Skipping {len(filtered_pairs)} invalid pair(s): ...")
```

## Behavior

### First Attempt (10s cycle 1)
```
⚠️ No ticker data for croackidr
```

### Second Attempt (10s cycle 2)
```
⚠️ No ticker data for croackidr
🚫 Pair CROACKIDR blacklisted - appears to be invalid/non-existent on Indodax
💡 Total invalid pairs: 1 - CROACKIDR
```

### Third Attempt (10s cycle 3) - SKIPPED!
```
⏭️ Skipping 1 invalid pair(s): CROACKIDR
🔄 Polling prices for 4 pair(s) (sequential)...
```

✅ **Tidak ada lagi error berulang untuk pair yang invalid!**

## User Notification

Saat ada pair yang di-blacklist, log akan menampilkan:
```
🚫 Pair CROACKIDR blacklisted - appears to be invalid/non-existent on Indodax
💡 Total invalid pairs: 1 - CROACKIDR
```

Dan di polling cycle berikutnya:
```
⏭️ Skipping 1 invalid pair(s): CROACKIDR
```

## How to Fix Invalid Pairs

Jika user sadar pair salah, bisa unwatch dan watch lagi dengan pair benar:

```bash
# Hapus pair invalid
/unwatch croackidr

# Tambah pair benar
/watch crowidr
```

## Technical Details

### Files Modified
- `price_poller.py`:
  - Added `invalid_pairs` blacklist set
  - Added `pair_fail_count` dictionary
  - Added `max_invalid_attempts = 2` threshold
  - Modified `_poll_all_pairs()` to skip blacklisted pairs
  - Modified `_poll_single_pair()` to track failures
  - Added `_track_pair_failure()` method

### Failure Scenarios
| Scenario | Behavior | Action |
|----------|----------|--------|
| Pair tidak ada di Indodax | 2x gagal → blacklist | ✅ User perlu `/unwatch` |
| Rate limit (429) | Retry 3x → global cooldown | ⏸️ Tidak di-blacklist (temporary) |
| Timeout/Network error | Retry 3x → skip | ⚠️ Tidak di-blacklist (might be temporary) |

### Rate Limit vs Invalid Pair
- **Rate limit (429)**: Tidak masuk blacklist, hanya cooldown 60 detik
- **Invalid pair (404/empty)**: Masuk blacklist setelah 2x gagal

## Testing

Untuk test fitur ini:
1. Tambahkan pair yang tidak ada: `/watch croackidr`
2. Tunggu 20 detik (2 polling cycles)
3. Cek log, harus muncul: `🚫 Pair CROACKIDR blacklisted`
4. Cycle berikutnya akan skip pair tersebut

## Future Improvements

- [ ] Notify user via Telegram saat pair di-blacklist
- [ ] Allow manual whitelist: `/whitelist <pair>`
- [ ] Auto-retry blacklisted pairs setiap 1 jam (in case of temporary issues)
- [ ] Validate pair saat `/watch` dipanggil (fail fast)
