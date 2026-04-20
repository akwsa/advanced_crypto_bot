# 🔧 Skip Pairs Blacklist Fix

## Problem

Valid pairs like `SUPERIDR`, `ORDERIDR`, `DIDR` were being incorrectly blacklisted as "invalid" due to:
1. **Rate limiting** (429 errors from Indodax)
2. **Timeout errors** (slow network)
3. **Connection errors** (temporary network issues)

The blacklist threshold was too aggressive (`max_invalid_attempts = 2`), meaning just 2 consecutive failures would permanently skip a pair until bot restart.

---

## Root Cause

```python
# BEFORE: Too aggressive
self.max_invalid_attempts = 2  # Blacklisted after just 2 failures!

# Any failure (including timeouts) counted toward blacklist
def _track_pair_failure(self, pair):
    self.pair_fail_count[pair] += 1
    if self.pair_fail_count[pair] >= 2:  # Too easy!
        self.invalid_pairs.add(pair)
```

---

## Solution

### 1. Increased Blacklist Threshold
```python
# AFTER: More reasonable
self.max_invalid_attempts = 10  # Only blacklist after 10 consecutive failures
```

### 2. Skip Tracking During Rate Limit Cooldown
```python
# Don't count failures during rate limit cooldown (temporary issue)
if self.rate_limit_cooldown_until and datetime.now() < self.rate_limit_cooldown_until:
    logger.debug(f"⏭️ Skipping pair {pair} during rate limit cooldown")
    return
```

### 3. Added Reset Command
New `/reset_skip` command to clear the blacklist without restarting bot:
```
/reset_skip  → Reset skipped pairs blacklist
```

---

## New Commands

### `/reset_skip` (Admin Only)
Resets the skipped/invalid pairs blacklist.

**Response:**
```
🔄 Skipped Pairs Reset!

• 4 pairs removed from skip list
• Bot will retry polling these pairs

💡 Pairs will be re-tested on next poll cycle
```

---

## Files Modified

| File | Changes |
|------|---------|
| `price_poller.py` | - `max_invalid_attempts`: 2 → 10<br>- Added rate limit cooldown check<br>- Added `reset_invalid_pairs()` method |
| `bot.py` | - Added `/reset_skip` command handler |

---

## How It Works Now

### Before Fix:
```
Bot starts → Polls pairs
→ Timeout/rate limit on SUPERIDR (attempt 1)
→ Timeout/rate limit on SUPERIDR (attempt 2)
→ 🚫 SUPERIDR BLACKLISTED FOREVER ❌
→ "⏭️ Skipping 4 invalid pair(s): SUPERIDR, ..."
```

### After Fix:
```
Bot starts → Polls pairs
→ Timeout on SUPERIDR (attempt 1/10) → NOT blacklisted
→ Success! → Counter reset ✅
→ SUPERIDR continues to be polled

If genuinely invalid:
→ 10 consecutive failures → Added to skip list
→ Use /reset_skip to retry
```

---

## Usage

### Reset Skipped Pairs:
```
/reset_skip
```

### Check Skipped Pairs:
Watch logs for:
```
💡 Total skipped pairs: 4 - SUPERIDR, ORDERIDR, DIDR, RAVEIDR
```

### After Reset:
Bot will re-test these pairs on next poll cycle. If they're valid, they'll be polled normally. If still invalid, they'll be re-skipped after 10 failures.

---

## Testing

1. **Restart bot** (clears in-memory blacklist automatically)
2. **Or use `/reset_skip`** to clear without restart
3. **Watch logs** for skipped pairs message
4. **Verify** valid pairs are being polled again

---

**Status:** ✅ **FIXED**
