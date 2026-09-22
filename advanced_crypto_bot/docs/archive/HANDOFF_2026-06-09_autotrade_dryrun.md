# HANDOFF — Autotrade DRY RUN Investigation, 2026-06-09

State per akhir session jam ~14:25 WIB. Lanjut besok dari sini.

## TL;DR

Bot di Google VM jalan normal (PID 14578, branch `fix/autotrade-dryrun-no-entry-vm-20260609`, commit tip `ee83a46`). 4 fix sudah deploy berlapis tapi masih **0 entry DRY RUN**. Investigasi mengungkap **2 bug fundamental yang baru ketahuan di iterasi terakhir**, harus dipecahkan dulu sebelum tuning lain.

## Apa yang sudah selesai (commit history)

```
ee83a46 fix(autotrade): relax MI filter thresholds (1.3→1.1, 1.2→1.05)
1b92bb6 fix(autotrade): snapshot pre_sr_recommendation BEFORE Quality Engine
5dc1c05 merge: bring in parent updates (audit-2026-06-07 fixes, dashboard, docs)
2197c3a fix(autotrade): zero entries in DRY RUN — bid=0, silent skips, S/R threshold
```

Semua sudah pushed ke GitHub branch `fix/autotrade-dryrun-no-entry-vm-20260609` dan deployed ke VM. Tests 60+/60+ pass.

## 2 Bug Fundamental yang BARU ketahuan (akhir session)

Dari log VM setelah commit `ee83a46` deploy (sample 2.5 menit, 49 scan):

### Bug 1 — Spread NEGATIF
Trace homeidr 14:19:28:
```
Market intelligence for homeidr: Volume=1.0x, OB=BEARISH,
                                  Signal=NEUTRAL, Filter=FAIL,
                                  Spread=-51.572%
```
Spread `(ask - bid) / mid = -51%` artinya **bid > ask**. Itu crossed market yang impossible kecuali:
- API quirk Indodax kembalikan data yang swap bids ↔ asks untuk pair tertentu
- Ada bug parsing di pemrosesan orderbook
- Format orderbook bedaya antara pair likuid (BTCIDR) vs low-cap

Padahal patch B (`autotrade/runtime.py`) sudah filter price ≤ 0. Bug-nya bukan di sana.

### Bug 2 — Volume ratio SELALU 1.0
Semua sample MI menunjukkan `Volume=1.0x`, di SEMUA pair, di SEMUA waktu. Mencurigakan banget. Hipotesis:
- `df["volume"].iloc[-1]` ambil candle yang sedang berjalan (volume akumulasi belum penuh)
- `historical_data` tidak update real-time, hanya snapshot awal startup
- Atau perhitungan `current_volume / avg_volume` ada bug pembagian

Jika volume ratio selalu = 1.0, **threshold MI_VOLUME_SPIKE_MIN apapun tidak terlewati** — itu sebabnya tuning 1.3→1.1 nyaris tanpa efek (cuma 1 dari 37 jadi MODERATE).

## Distribusi outcome di sample terakhir

```
MI Signal=BULLISH:    0       ← masih nol
MI Signal=MODERATE:   1       ← cuma 1
MI Signal=NEUTRAL:   36       ← 95% block
MI Filter=PASS:       1
MI Filter=FAIL:      24

DRY RUN scans:       49
Entry blocked:       24 (12 MI fail, 1 V4, 11 lain)
Skipping HOLD:       21
Entry SUCCESS:        0
```

## Decision yang BELUM diambil

User tanyakan sebelum break:
1. **Revert MI tuning** (1.3/1.2 lagi) lalu fokus 2 bug → recommend
2. **Keep tuning** + investigate bug paralel
3. **Stop dulu, review code bareng**

Diserahkan ke besok.

## File yang perlu dibaca pertama besok

1. `autotrade/runtime.py:1099-1260` — `analyze_market_intelligence()`
2. `autotrade/runtime.py:1108-1117` — volume ratio calc (`df["volume"].iloc[-1]` vs `df["volume"].iloc[-20:].mean()`)
3. `autotrade/runtime.py:1120-1226` — orderbook fetch + spread calc
4. Cari di `bot.py` siapa yang update `bot.historical_data` — dan apakah dia merge candle live atau tunggu candle close
5. `data/indodax.py` (kalau ada) — get_orderbook return format check, terutama struktur bids vs asks

## Actionable backlog kalau lanjut

A. **Spread negatif investigation** — saya curiga `bot.indodax.get_orderbook()` mengembalikan struct yang bisa swap bids/asks untuk pair tertentu. Cek ke data layer dan log raw response untuk 1-2 pair (homeidr, dlcidr).

B. **Volume stagnant investigation** — ambil snapshot `bot.historical_data["homeidr"].tail(3)` di runtime untuk lihat apakah candle terakhir update atau frozen.

C. Setelah 2 bug dipecahkan:
   - Re-evaluate MI threshold (mungkin perlu balik ke 1.3/1.2 atau intermediate)
   - Re-jalankan bot dan validate entry SUCCESS minimal 1-2

## State environment

- WSL: `/home/officer/advanced_crypto_bot/advanced_crypto_bot/` (working tree clean)
- VM: `gcloud compute ssh wkagung@instance-20260609-044439 --zone=asia-east2-c --project=project-a8fe20b8-0906-4445-aff`
- VM bot: PID 14578, branch `fix/autotrade-dryrun-no-entry-vm-20260609`, commit `ee83a46`
- Log file: `~/advanced_crypto_bot/advanced_crypto_bot/logs/trading_bot.log`
- Backup logs di VM:
  - `.before-fix-20260609`
  - `.before-merge-20260609`
  - `.before-pre-sr-fix-20260609`
  - `.before-mi-tune-20260609`

## Side topics yang dibahas (parkir, belum action)

- **Telegram bot di Hermes Agent**: user tertarik install. Status: gateway sudah running di laptop, butuh `TELEGRAM_BOT_TOKEN` dari @BotFather + user ID dari @userinfobot. Belum dieksekusi.
- **VM resource untuk Hermes**: dicek, VM cukup luas (5.4 GB free RAM, 54 GB disk). Bisa add Hermes ke VM yang sama tanpa ganggu bot trading. Belum dieksekusi.
- **Approvals mode `off`**: ditawarkan, user pilih TIDAK ubah (manual prompt tetap aktif).

## Cara resume besok

```
"lanjut dari handoff 2026-06-09, baca dulu docs/archive/HANDOFF_2026-06-09_autotrade_dryrun.md"
```

Atau saya bisa otomatis cari file ini dengan `search_files`.
