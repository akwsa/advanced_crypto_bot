# HANDOFF — 2026-06-10 (Dashboard V2 + Pair Scanner)

**Konteks lanjutan dari:** `HANDOFF_2026-06-09_autotrade_dryrun.md` → spread fix → user request: dashboard revamp + auto pair scanner.

## Status Repo

- **Branch:** `fix/autotrade-dryrun-no-entry-vm-20260609`
- **Last commit local + GitHub:** `c745ad0` — fix(bot): hapus local import threading
- **Commit history relevan:**
  - `c745ad0` fix UnboundLocalError (local import threading shadow module-level)
  - `c4d0f31` port TMA 8080→8090 + auto-start FastAPI dashboard di 8091
  - `fec2502` feat: pair scanner + dashboard revamp v2
  - `6a7f064` fix: spread negatif (detect_spoofing round(price,-3))

Lokal CWD: `/home/officer/advanced_crypto_bot/advanced_crypto_bot`

## Yang Sudah Selesai

### 1. Bug fix spread negatif ✅ DEPLOYED
- Root cause: `microstructure.py::detect_spoofing` pakai `round(price, -3)` rusak presisi pair low-cap
- Fix: `analyze_market_intelligence()` pakai RAW orderbook untuk spread calc
- Volume_ratio default: 1.0 → 0.0 (tidak misleading)
- 12/12 test PASS
- VM verify: 0 spread negatif setelah restart

### 2. Pair Scanner module ✅ COMMITTED
- `autohunter/pair_scanner.py` — `scan_top_volume`, `scan_top_movers`, `build_watchlist_recommendation`, cache 60s
- `autohunter/scanner_commands.py` — Telegram: `/top_volume /top_movers /top_losers /scan_pairs`
- Endpoint dashboard: `GET /api/v1/pairs/top-movers`, `GET /api/v1/pairs/watchlist-recommendation`
- 18 test pair_scanner + 5 test endpoint = 23 test PASS

### 3. Dashboard Revamp V2 ✅ COMMITTED
- Layout: top bar (mode badge + 4 stats) + 3 kolom (pairs tabs | chart+detail | insights)
- Tabs: Watchlist / Top Movers / Top Losers
- Right panel: Live Movers, Recent Signals, Open Positions
- Modern dark theme, gradient cards, animasi PUMPING badge
- Lightweight-charts kept, TradingView widget di-drop
- 12 test layout v2 PASS

### 4. Port restructure ✅ COMMITTED
- TMA legacy: 8080 → **8090** (lepas konflik dengan code-server)
- Dashboard v2 baru: **8091** (auto-start saat bot run via daemon thread)
- Env: `TMA_DASHBOARD_PORT`, `DASHBOARD_API_PORT`

## Status VM (TERAKHIR DICEK)

- Repo VM: di-pull ke commit `c745ad0` ✅
- Dependencies: `uvicorn 0.49.0` + `fastapi 0.136.3` SUDAH ter-install di venv ✅
- **Bot di VM: KEMUNGKINAN MATI** ❌ (tmux session hilang setelah SSH disconnect, port 8090/8091 tidak listening saat last check)
- SSH ke VM saat handoff: TIDAK STABIL (timeout 25s, gcloud return exit 255)

## Blocker Saat Ini

**SSH connectivity ke VM bermasalah** — semua perintah `gcloud compute ssh` lebih dari ~5 detik timeout dengan exit 255. Bukan masalah code, tapi GCP tunneling/IAP.

## Langkah Selanjutnya (saat session lanjut)

### Step 1 — Cek koneksi VM
```bash
gcloud compute ssh wkagung@instance-20260609-044439 --zone=asia-east2-c --project=project-a8fe20b8-0906-4445-aff --command='echo OK'
```

### Step 2 — Restart bot (pakai screen, bukan tmux — lebih survive SSH disconnect)
```bash
gcloud compute ssh wkagung@instance-20260609-044439 --zone=asia-east2-c --project=project-a8fe20b8-0906-4445-aff
# di dalam SSH:
cd ~/advanced_crypto_bot/advanced_crypto_bot
pkill -9 -f bot.py; sleep 2
screen -dmS bot bash -c "cd ~/advanced_crypto_bot/advanced_crypto_bot && venv/bin/python -u bot.py 2>&1 | tee -a /tmp/bot_runtime.log"
sleep 25
pgrep -af "venv/bin/python bot.py"
ss -tlnp | grep -E ':80(90|91)'
```

### Step 3 — Verify dashboard
```bash
curl http://localhost:8091/api/v1/safety/status
curl http://localhost:8091/api/v1/pairs/top-volume?limit=3
curl http://localhost:8091/api/v1/pairs/top-movers?limit=3
```

### Step 4 — Test Telegram commands
Kirim ke bot via Telegram:
- `/top_volume 10`
- `/top_movers 5`
- `/top_losers 5`
- `/scan_pairs` (preview)
- `/scan_pairs add` (auto-add ke watchlist)

### Step 5 — Firewall GCP buka port (kalau mau akses dari luar)
```bash
gcloud compute firewall-rules create allow-bot-dashboards \
  --allow tcp:8090,tcp:8091 \
  --target-tags=http-server \
  --project=project-a8fe20b8-0906-4445-aff
```

### Step 6 — Akses dashboard dari browser
- Dashboard v2 (modern): `http://VM_EXTERNAL_IP:8091/`
- TMA legacy: `http://VM_EXTERNAL_IP:8090/`
- Code-server tetap di: `http://localhost:8080/` (lokal)

## Open Issues (Non-Blocker)

1. **MI Signal=NEUTRAL untuk ~90% pair** — karena scanner jalan jam malam (volume rendah natural). Tunggu 08:00-22:00 WIB untuk lihat behavior real.
2. **R/R floor 1.50 vs actual 1.19** — saharaidr lolos MI tapi diblokir R/R after fees. Mungkin perlu adjust floor untuk DRY RUN, tapi bukan prioritas.
3. **`historical_data` kosong** untuk pair yang tidak di-preload — volume_ratio jadi 0.0 (sekarang correct, dulu misleading 1.0). Bisa diperbaiki nanti dengan refresh historical_data per pair on-demand.

## Catatan Penting

- User pakai bahasa Indonesia, gaya santai-teknis
- User preferensi: "jangan tanya, lakukan semaksimal mungkin"
- DRY RUN mode harus tetap aktif (jangan pernah enable real trading tanpa konfirmasi)
- VM identifiers: `wkagung@instance-20260609-044439` zone `asia-east2-c` project `project-a8fe20b8-0906-4445-aff`
- Bot path VM: `~/advanced_crypto_bot/advanced_crypto_bot/`
- Test command lokal: `venv/bin/python -m pytest -q`
