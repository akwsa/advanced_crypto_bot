# Telegram Access Control Policy

Date: 2026-05-22

## Goal

Pastikan bot hanya diakses oleh user yang sudah terdaftar / diizinkan.

## Prinsip

- **Default-Deny**: semua update Telegram ditolak kecuali pengirim terdaftar di whitelist.
- **Multi-layer**: Config, DB, dan in-memory cache saling mengisi.
- **Role-based**: admin (dari `ADMIN_IDS`) bisa semua fitur; user biasa sesuai role.

## Arsitektur

```
Handler Registry (handler_registry.py)
  └── _guard_callback()       ← sematkan _require_authorized ke semua handler
       └── _require_authorized()
            ├── tolak jika bukan private chat
            ├── tolak jika user_id tidak di allowed_user_ids
            ├── admin_only? → hanya ADMIN_IDS yang lolos
            ├── catat user ke telegram_users (upsert)
            └── return True / deny
```

## Lapisan

### A. `Config.ADMIN_IDS` (env)
- Dari environment variable.
- Admin selalu memiliki akses penuh tanpa registrasi.

### B. `Config.ALLOWED_USER_IDS` (env)
- Dari environment variable.
- User yang sudah dikenal, langsung diizinkan tanpa invite code.

### C. `Config.TELEGRAM_INVITE_CODE` (env)
- Kode undangan untuk self-registrasi via `/register <code>`.
- User biasa harus memberikan kode yang cocok agar terdaftar.

### D. `telegram_users` table (DB)
- Tabel persistent untuk menyimpan seluruh user terdaftar.
- Saat startup, user aktif dari DB dimerge ke `self.allowed_user_ids`.

### E. `_require_authorized()` (helper di `bot.py`)
- Dipanggil **sebelum** handler command/callback/text/dashboard.

## Flow Registrasi

```
User /register <kode>
  → kode cocok TELEGRAM_INVITE_CODE
    → user_id disimpan ke telegram_users
    → user_id ditambahkan ke allowed_user_ids in-memory
    → pesan "Registrasi berhasil"
  → kode tidak cocok
    → ditolak
    → logged
```

## Perintah yang bebas otorisasi

- `/register` — satu-satunya command yang boleh tanpa terdaftar.

Semua command lain (`/start`, `/signal`, callback buttons, scalper, text input) wajib melewati `_require_authorized()`.

## Batasan tambahan

- Semua chat harus `type = private`; group/channel ditolak.
- Admin-only commands tetap dicek 2× — di `_require_authorized(admin_only=True)` dan di handler internal.

## Logging

Setiap akses ditolak dicatat:

```text
🔒 Telegram access denied user=<id> chat=<id> admin_only=<bool>
```

## Test Coverage

Lihat: `tests/test_telegram_access_control.py`

| Test | Coverage |
|---|---:|
| Admin always authorized | ✅ |
| Allowed user authorized | ✅ |
| User not admin for admin_only commands | ✅ |
| Unknown user denied | ✅ |
| Require authorized allows registered admin | ✅ |
| Require authorized denies unknown private chat | ✅ |
| Require authorized denies callback query | ✅ |
| Require authorized denies group chat | ✅ |
| Register success with valid invite code | ✅ |
| Register admin without invite | ✅ |
| Register denied with invalid code | ✅ |
| Allowed user IDs merged from config + DB | ✅ |

## Setup .env

```bash
# Admin IDs (required)
ADMIN_IDS=123456789

# Whitelist user IDs (optional)
ALLOWED_USER_IDS=111111111,222222222

# Invite code for self-registration (optional)
TELEGRAM_INVITE_CODE=rahasia2026
```

## File yang disentuh

- `core/config.py` — tambah `ALLOWED_USER_IDS`, `TELEGRAM_INVITE_CODE`
- `core/database.py` — tabel `telegram_users` + method CRUD
- `core/handler_registry.py` — wrapper `_guard_callback` untuk semua command/callback
- `bot.py` — helper `_load_telegram_access_control`, `_is_authorized`, `_require_authorized`, `register_access`
- `.env.example` — tambah env baru
- `tests/test_telegram_access_control.py` — test suite