# Telegram Bot Security - Setup & Operations Guide

**Version:** 1.0  
**Date:** 2026-05-22  
**Status:** Production Ready

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Configuration Guide](#configuration-guide)
4. [User Management](#user-management)
5. [Security Features](#security-features)
6. [Troubleshooting](#troubleshooting)
7. [Database Schema](#database-schema)
8. [API Reference](#api-reference)
9. [Best Practices](#best-practices)

---

## Overview

Bot menerapkan **default-deny access control** untuk melindungi trading bot dari akses tidak authorized. Hanya user yang terdaftar yang dapat menggunakan bot.

### Security Model

```
┌─────────────────────────────────────────┐
│           Telegram Update               │
└──────────────┬──────────────────────────┘
               │
               ▼
         ┌─────────────┐
         │  Private?   │
         └──────┬──────┘
                │ Yes
                ▼
      ┌──────────────────┐
      │  Authorized?     │
      │  • ADMIN_IDS     │
      │  • ALLOWED_IDS   │
      │  • DB registered │
      └──────┬───────────┘
             │ Yes
             ▼
    ┌────────────────────┐
    │  Execute Handler   │
    │  (Trading Logic)   │
    └────────────────────┘
```

### Three Ways to Grant Access

| Method | When | How |
|--------|------|-----|
| **Admin** | Setup time | Add user_id to `ADMIN_IDS` in `.env` |
| **Whitelist** | Setup time | Add user_id to `ALLOWED_USER_IDS` in `.env` |
| **Self-Registration** | Runtime | User sends `/register <code>` |

---

## Quick Start

### 1. Setup Admin

Edit `.env`:
```bash
ADMIN_IDS=123456789
```

**How to get your Telegram user ID:**
1. Open Telegram
2. Search for `@userinfobot`
3. Send `/start`
4. Bot will reply with your user ID

### 2. (Optional) Setup Invite Code

Edit `.env`:
```bash
TELEGRAM_INVITE_CODE=mySecretCode2026
```

### 3. Restart Bot

```bash
cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
python bot.py
```

### 4. Verify

Check logs for:
```
🔐 Telegram access control loaded: X allowed users (Y admin, Z active registered)
```

### 5. Test Access

As admin, send to bot:
```
/start
```

You should see the welcome message.

As non-registered user, send:
```
/start
```

You should see:
```
❌ Access denied.
```

---

## Configuration Guide

### Environment Variables

#### ADMIN_IDS (Required)

```bash
# Single admin
ADMIN_IDS=123456789

# Multiple admins (comma-separated)
ADMIN_IDS=123456789,987654321,555555555
```

**Purpose:**
- Full bot access
- No registration needed
- Can use all commands
- Auto-registered on first use

**Best Practice:**
- Use your personal Telegram user ID
- Keep this list small (1-3 people)
- Never share admin credentials

#### ALLOWED_USER_IDS (Optional)

```bash
# Pre-approved users (comma-separated)
ALLOWED_USER_IDS=111111111,222222222,333333333
```

**Purpose:**
- Grant access without registration
- Good for trusted team members
- No invite code needed

**Best Practice:**
- Use for permanent team members
- Verify user IDs before adding
- Document who each ID belongs to

#### TELEGRAM_INVITE_CODE (Optional)

```bash
# Invite code for self-registration
TELEGRAM_INVITE_CODE=MySecret2026
```

**Purpose:**
- Allow users to self-register
- Control access via shared secret
- Can be rotated periodically

**Best Practice:**
- Use strong, unique code
- Change periodically (monthly)
- Don't share publicly
- Use different codes for different groups

### Configuration Examples

#### Scenario 1: Solo Trader

```bash
ADMIN_IDS=123456789
ALLOWED_USER_IDS=
TELEGRAM_INVITE_CODE=
```

Only you can use the bot.

#### Scenario 2: Small Team

```bash
ADMIN_IDS=123456789
ALLOWED_USER_IDS=111111111,222222222
TELEGRAM_INVITE_CODE=
```

You (admin) + 2 permanent team members.

#### Scenario 3: Growing Team with Invite System

```bash
ADMIN_IDS=123456789,987654321
ALLOWED_USER_IDS=
TELEGRAM_INVITE_CODE=TeamAlpha2026
```

2 admins + unlimited users via invite code.

#### Scenario 4: Hybrid Approach

```bash
ADMIN_IDS=123456789
ALLOWED_USER_IDS=111111111,222222222
TELEGRAM_INVITE_CODE=InviteCode2026
```

1 admin + 2 whitelisted + invite for others.

---

## User Management

### Register New User

**As User:**
```
/register MySecret2026
```

**Response:**
```
✅ Registrasi berhasil. Akses bot sudah aktif.
```

### Check Registered Users (Database)

```bash
cd /home/officer/advanced_crypto_bot/advanced_crypto_bot
sqlite3 data/trading.db

SELECT user_id, username, first_name, role, is_active, registered_at 
FROM telegram_users 
WHERE is_active = 1 
ORDER BY registered_at DESC;
```

Example output:
```
123456789|admin_user|Admin|admin|1|2026-05-22 10:30:00
111111111|trader1|John|user|1|2026-05-22 11:45:00
222222222|trader2|Jane|user|1|2026-05-22 12:15:00
```

### Deactivate User (Database)

```bash
sqlite3 data/trading.db

UPDATE telegram_users 
SET is_active = 0, 
    blocked_reason = 'Policy violation', 
    last_seen_at = CURRENT_TIMESTAMP 
WHERE user_id = 111111111;
```

User will be denied access immediately (cached in-memory).

### Rotate Invite Code

1. Edit `.env`:
```bash
TELEGRAM_INVITE_CODE=NewCode2026
```

2. Restart bot:
```bash
python bot.py
```

Old code will no longer work for new registrations.

### Export User List

```bash
sqlite3 data/trading.db -header -csv \
  "SELECT * FROM telegram_users WHERE is_active = 1" \
  > registered_users_$(date +%Y%m%d).csv
```

---

## Security Features

### 1. Default-Deny Access Control

**Implementation:**
- All Telegram updates rejected by default
- Only whitelisted users allowed
- Enforced at handler layer (before business logic)

**Coverage:**
- ✅ All commands (100+)
- ✅ Callback query handlers
- ✅ Text input handlers
- ✅ Unknown command handlers

**Exception:**
- `/register` — only command that bypasses auth

### 2. Private Chat Restriction

**Rule:**
- Bot only responds in private chats
- Group chats: denied
- Channel messages: denied

**Implementation:**
```python
if chat.type != "private":
    return deny()
```

### 3. Role-Based Access

| Role | Source | Capabilities |
|------|--------|--------------|
| **Admin** | `ADMIN_IDS` | Full access, admin commands |
| **User** | `ALLOWED_USER_IDS` or registered | Standard commands, no admin features |

**Admin-only commands** (examples):
- `/retrain` — ML model retraining
- `/emergency_stop` — emergency trading halt
- System configuration commands

### 4. Persistent User Registry

**Database Table:** `telegram_users`

**Tracked Information:**
- User ID (primary key)
- Username (Telegram @username)
- First name (display name)
- Role (admin/user)
- Active status (1=active, 0=blocked)
- Registration timestamp
- Last seen timestamp
- Block reason (if deactivated)

**Auto-Update:**
- Every authorized access updates `last_seen_at`
- Tracks user activity automatically

### 5. Access Denial Logging

**Log Format:**
```
🔒 Telegram access denied user=<user_id> chat=<chat_id> admin_only=<bool>
```

**Example:**
```
2026-05-22 10:45:23 WARNING 🔒 Telegram access denied user=999999 chat=999999 admin_only=False
```

**Use Cases:**
- Detect unauthorized access attempts
- Monitor security incidents
- Audit access patterns

### 6. Multi-Layer Authorization

```
Layer 1: Environment Config
├─ ADMIN_IDS
└─ ALLOWED_USER_IDS

Layer 2: Database Registry
└─ telegram_users (is_active=1)

Layer 3: In-Memory Cache
└─ Merged whitelist (startup + runtime updates)

Layer 4: Handler Guard
└─ _guard_callback() wrapper
    └─ _require_authorized() gate
```

---

## Troubleshooting

### User Can't Access Bot

**Symptom:** User sends `/start`, gets `❌ Access denied.`

**Diagnosis:**
1. Check if user is admin:
   ```bash
   grep ADMIN_IDS .env
   ```

2. Check if user is whitelisted:
   ```bash
   grep ALLOWED_USER_IDS .env
   ```

3. Check database:
   ```bash
   sqlite3 data/trading.db \
     "SELECT * FROM telegram_users WHERE user_id = <USER_ID>;"
   ```

4. Check logs:
   ```bash
   grep "Telegram access denied" logs/bot.log | tail -20
   ```

**Solution:**
- Add to `ADMIN_IDS` or `ALLOWED_USER_IDS` in `.env`
- Or: Share invite code for `/register`
- Then restart bot

### Admin Can't Use Admin Commands

**Symptom:** Admin user gets denied for admin-only commands.

**Diagnosis:**
```bash
# Check ADMIN_IDS format
grep ADMIN_IDS .env

# Check for typos (spaces, quotes)
cat .env | grep ADMIN_IDS | od -c
```

**Solution:**
```bash
# Correct format (no spaces, no quotes)
ADMIN_IDS=123456789,987654321

# Wrong formats:
ADMIN_IDS= 123456789, 987654321  # ❌ spaces
ADMIN_IDS="123456789"             # ❌ quotes
```

### Bot Log Shows "0 allowed users"

**Symptom:**
```
🔐 Telegram access control loaded: 0 allowed users (0 admin, 0 active registered)
```

**Diagnosis:**
```bash
# Check .env exists and is loaded
cat .env | grep ADMIN_IDS

# Check file permissions
ls -l .env
```

**Solution:**
1. Verify `.env` file exists in working directory
2. Check `ADMIN_IDS` is set
3. Restart bot
4. If still fails, check for `.env.local` or other env files

### Access Denied in Group Chat

**Symptom:** Bot doesn't respond in group.

**Solution:** This is by design. Bot only works in private chat.

**Workaround:**
1. Start private chat with bot
2. Send commands there
3. Group restrictions cannot be bypassed

### User Registered but Still Denied

**Symptom:** User successfully registered but still gets denied.

**Diagnosis:**
```bash
# Check registration was saved
sqlite3 data/trading.db \
  "SELECT user_id, is_active, registered_at FROM telegram_users WHERE user_id = <USER_ID>;"

# Check in-memory cache
# (requires bot restart to reload)
```

**Solution:**
1. Restart bot to reload user cache
2. Verify `is_active = 1` in database
3. Check logs for any errors during startup

### How to Find User's Telegram ID

**Method 1: Using @userinfobot**
1. User opens Telegram
2. Search for `@userinfobot`
3. Send `/start`
4. Bot replies with user ID

**Method 2: From Bot Logs**
```bash
# User tries to access bot (will be denied)
# Check logs for their user_id
grep "Telegram access denied" logs/bot.log | tail -5
```

**Method 3: From Database** (if previously accessed)
```bash
sqlite3 data/trading.db \
  "SELECT user_id, username, first_name FROM telegram_users;"
```

---

## Database Schema

### Table: telegram_users

```sql
CREATE TABLE telegram_users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    role TEXT DEFAULT 'user',
    is_active INTEGER DEFAULT 1,
    invite_code TEXT,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP,
    blocked_reason TEXT
);
```

### Column Descriptions

| Column | Type | Purpose |
|--------|------|---------|
| `user_id` | INTEGER | Telegram user ID (primary key) |
| `username` | TEXT | Telegram @username (nullable) |
| `first_name` | TEXT | Display name (nullable) |
| `role` | TEXT | 'admin' or 'user' |
| `is_active` | INTEGER | 1=active, 0=blocked |
| `invite_code` | TEXT | Code used during registration (nullable) |
| `registered_at` | TIMESTAMP | When user was first registered |
| `last_seen_at` | TIMESTAMP | Last bot interaction (auto-updated) |
| `blocked_reason` | TEXT | Why user was blocked (nullable) |

### Common Queries

**List all active users:**
```sql
SELECT user_id, username, role, registered_at 
FROM telegram_users 
WHERE is_active = 1 
ORDER BY registered_at DESC;
```

**Count users by role:**
```sql
SELECT role, COUNT(*) as count 
FROM telegram_users 
WHERE is_active = 1 
GROUP BY role;
```

**Find recent registrations:**
```sql
SELECT user_id, username, registered_at 
FROM telegram_users 
WHERE registered_at > datetime('now', '-7 days') 
ORDER BY registered_at DESC;
```

**Find inactive users:**
```sql
SELECT user_id, username, last_seen_at 
FROM telegram_users 
WHERE is_active = 1 
  AND last_seen_at < datetime('now', '-30 days') 
ORDER BY last_seen_at ASC;
```

**Audit blocked users:**
```sql
SELECT user_id, username, blocked_reason, last_seen_at 
FROM telegram_users 
WHERE is_active = 0 
ORDER BY last_seen_at DESC;
```

---

## API Reference

### Bot Methods

#### `_is_authorized(user_id: int, admin_only: bool = False) -> bool`

Check if user is authorized.

**Parameters:**
- `user_id` — Telegram user ID
- `admin_only` — If True, only admins pass

**Returns:**
- `True` — User is authorized
- `False` — User is not authorized

**Example:**
```python
if self._is_authorized(user_id):
    # User can proceed
    pass
```

#### `_require_authorized(update, context, admin_only: bool = False) -> bool`

Gate helper for handlers. Checks authorization and sends denial message if needed.

**Parameters:**
- `update` — Telegram Update object
- `context` — Telegram Context object
- `admin_only` — If True, require admin role

**Returns:**
- `True` — User authorized, proceed
- `False` — User denied, message sent

**Example:**
```python
async def my_handler(self, update, context):
    if not await self._require_authorized(update, context):
        return
    # Handler logic here
```

#### `register_access(update, context)`

Handler for `/register <code>` command.

**Flow:**
1. Check if user is admin (skip invite code)
2. Verify invite code matches `TELEGRAM_INVITE_CODE`
3. Register user in database
4. Add to in-memory cache
5. Send confirmation message

---

### Database Methods

#### `upsert_telegram_user(...)`

Create or update a user record.

**Parameters:**
- `user_id` — Telegram user ID (required)
- `username` — Telegram @username (optional)
- `first_name` — Display name (optional)
- `role` — 'admin' or 'user' (default: 'user')
- `is_active` — 1 or 0 (default: 1)
- `invite_code` — Registration code (optional)
- `blocked_reason` — Block reason (optional)

#### `get_telegram_user(user_id: int)`

Fetch user record by ID.

**Returns:** SQLite Row object or None

#### `get_active_telegram_users() -> List[int]`

Get list of all active user IDs.

**Returns:** List of integers

#### `register_telegram_user(...)`

Register a new user (calls `upsert_telegram_user` with `is_active=1`).

#### `deactivate_telegram_user(user_id: int, reason: str = None)`

Block a user.

**Parameters:**
- `user_id` — User to deactivate
- `reason` — Optional reason for blocking

---

## Best Practices

### Security

1. **Keep Admin List Small**
   - Only trusted individuals
   - 1-3 admins maximum
   - Regular audit of admin access

2. **Rotate Invite Codes**
   - Change monthly or after sharing widely
   - Use different codes for different groups
   - Track code usage if possible

3. **Monitor Access Logs**
   - Check for denied access attempts
   - Alert on suspicious patterns
   - Review logs weekly

4. **Use Strong Invite Codes**
   - Minimum 12 characters
   - Mix of letters and numbers
   - Avoid dictionary words
   - Example: `Tr4d3B0t_2026_Alpha`

5. **Regular User Audit**
   - Review registered users monthly
   - Deactivate inactive accounts
   - Remove departed team members

### Operations

1. **Backup User Database**
   ```bash
   cp data/trading.db data/trading.db.backup.$(date +%Y%m%d)
   ```

2. **Document User IDs**
   - Keep internal mapping of user_id → real name
   - Store securely (encrypted file or password manager)

3. **Test Access After Changes**
   - After editing `.env`, test with a non-admin account
   - Verify denials work as expected

4. **Use Environment-Specific Codes**
   ```bash
   # Production
   TELEGRAM_INVITE_CODE=ProdSecret2026
   
   # Staging
   TELEGRAM_INVITE_CODE=StagingTest123
   ```

5. **Log Rotation**
   - Keep access denial logs for audit
   - Rotate logs monthly
   - Archive for compliance if needed

### Maintenance

1. **Monthly Tasks**
   - Review registered users
   - Rotate invite code
   - Audit access logs
   - Backup user database

2. **Quarterly Tasks**
   - Review admin list
   - Clean up inactive users
   - Test registration flow
   - Update documentation

3. **After Incidents**
   - Rotate all codes immediately
   - Review access logs for breach
   - Deactivate compromised accounts
   - Consider regenerating bot token

---

## Migration Notes

### Upgrading from Unprotected Bot

**Before (anyone can use):**
```python
# No authorization checks
async def start(self, update, context):
    await update.message.reply_text("Welcome!")
```

**After (default-deny):**
```python
# Automatic authorization via _guard_callback()
async def start(self, update, context):
    # _require_authorized() already called by wrapper
    await update.message.reply_text("Welcome!")
```

**Migration Steps:**

1. **Add your admin ID to `.env`**
2. **Restart bot**
3. **Test your access** (should work)
4. **Test unauthorized access** (should deny)
5. **Add other users** as needed

**Existing users:** Will be denied until added to whitelist or registered.

---

## Support & Resources

### Documentation Files

- `docs/telegram-access-control.md` — Architecture & design
- `CHANGELOG-telegram-access-control.md` — Implementation details
- `COMMAND_REFERENCE.md` — Command documentation
- `tests/test_telegram_access_control.py` — Test coverage

### Helpful Commands

```bash
# View access logs
grep "access denied" logs/bot.log

# Check configuration
cat .env | grep -E "(ADMIN_IDS|ALLOWED_USER_IDS|INVITE_CODE)"

# List registered users
sqlite3 data/trading.db "SELECT * FROM telegram_users;"

# Test database connection
sqlite3 data/trading.db "SELECT COUNT(*) FROM telegram_users;"
```

### Testing

Run security tests:
```bash
python -m pytest tests/test_telegram_access_control.py -v
```

Run all tests:
```bash
python -m pytest tests/ -v
```

---

**Document Version:** 1.0  
**Last Updated:** 2026-05-22  
**Maintained By:** Security Team