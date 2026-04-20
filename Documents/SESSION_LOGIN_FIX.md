# Telegram Session Login Fix

## Problem

Script `fetch_signal_history.py` dan `telegram_signal_saver.py` gagal dengan error:
```
[ERROR] ❌ Session tidak valid. Hapus file session dan jalankan ulang.
```

## Root Cause

- Script menggunakan `telethon` yang memerlukan **session file** (`signal_session.session`)
- Jika file session belum ada atau expired, script **langsung exit** tanpa login
- User tidak punya cara untuk **membuat session baru**

## Solution

### ✅ Auto-Login Flow

Kedua script sekarang akan **otomatis login** jika session belum ada:

```python
if not await client.is_user_authorized():
    logger.warning("⚠️  Session belum ada atau tidak valid!")
    logger.info("📱 Memulai login ke Telegram...")
    
    await client.start(
        phone=lambda: input("Masukkan nomor HP (+62xxx): "),
        password=lambda: input("Masukkan password 2FA (jika ada): "),
        code_callback=lambda: input("Masukkan kode OTP dari Telegram: ")
    )
    logger.info("✅ Login berhasil! Session disimpan.")
```

### ✅ First Time Usage

**Saat pertama kali menjalankan:**

```bash
python fetch_signal_history.py
# atau
python telegram_signal_saver.py
```

**Output yang muncul:**
```
⚠️  Session belum ada atau tidak valid!
📱 Memulai login ke Telegram...
Masukkan nomor HP (+62xxx): +6281234567890
Masukkan kode OTP dari Telegram: 12345
✅ Login berhasil! Session disimpan.
```

**Setelah itu:**
- Session disimpan di `signal_session.session`
- Script langsung connect tanpa perlu login lagi
- Session **persist** sampai di-logout manual atau expire

### ✅ Changes Made

| File | Changes |
|------|---------|
| `fetch_signal_history.py` | Added auto-login flow in `main()` |
| `telegram_signal_saver.py` | Refactored to use async main + auto-login |
| `telegram_signal_saver.py` | Moved event handler to `setup_event_handler()` |
| `telegram_signal_saver.py` | Changed from sync `with client:` to `asyncio.run(main())` |

### ✅ Session Management

**Session file:** `signal_session.session`

**Lokasi:** Same directory as scripts

**Jika ingin reset login:**
```bash
# Hapus session file
rm signal_session.session
# atau di Windows:
del signal_session.session

# Jalankan ulang (akan minta login lagi)
python fetch_signal_history.py
```

### ✅ Security Notes

⚠️  **PENTING:**
- Session file berisi **credential Telegram** kamu
- **JANGAN** commit `signal_session.session` ke Git
- File sudah ada di `.gitignore`
- Jika session dicuri, orang lain bisa akses akun Telegram kamu

**Jika session compromised:**
1. Hapus session file
2. Login ulang dengan nomor HP + OTP baru
3. Aktifkan **2FA** di Telegram settings

---

## Testing

### First Time Setup
```bash
# 1. Jalankan fetch history
python fetch_signal_history.py

# Akan muncul prompt login
Masukkan nomor HP (+62xxx): +6281234567890
Masukkan kode OTP dari Telegram: 54321
✅ Login berhasil! Session disimpan.

# Script lanjut fetch signals
[INFO] Mengambil pesan dari Telegram...
```

### Subsequent Runs
```bash
# Session sudah ada, langsung connect
python fetch_signal_history.py

[INFO] Connection to 149.154.167.51:443/TcpFull complete!
[INFO] Mengambil pesan dari Telegram...
```

### telegram_signal_saver.py
```bash
# Pertama kali
python telegram_signal_saver.py
# Login → Event handler registered → Listening for signals

# Setelah itu
python telegram_signal_saver.py
# Langsung listening (no login needed)
```

---

## Troubleshooting

### "Login gagal: Auth key duplicated"
- Session file corrupt
- **Solusi:** Hapus `signal_session.session`, login ulang

### "FloodWaitError: Wait X seconds"
- Terlalu banyak percobaan login
- **Solusi:** Tunggu X detik, coba lagi

### "Phone number invalid"
- Format nomor salah
- **Solusi:** Gunakan format internasional: `+6281234567890`

### "Code expired"
- OTP kadaluarsa (biasanya 5 menit)
- **Solusi:** Request kode baru, masukkan lebih cepat

### "Session expired" setelah beberapa hari
- Session Telethon bisa expire
- **Solusi:** Hapus session file, login ulang

---

## Related Files

- `fetch_signal_history.py` - Fetch old signals from Telegram
- `telegram_signal_saver.py` - Monitor and save new signals
- `signal_session.session` - Session credential (auto-created)
- `signal_alerts.xlsx` - Output Excel file
