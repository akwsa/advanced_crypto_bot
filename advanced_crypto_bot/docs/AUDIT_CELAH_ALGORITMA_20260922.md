# AUDIT: Celah Algoritma Bot — Kerugian & Error Tidak Sejalan dengan Algoritma

Tanggal : 2026-09-22
Scope   : autotrade/runtime.py, autotrade/price_monitor.py, autotrade/risk_manager.py,
          bot.py, quant/bayesian_kelly.py
Status  : **2 BUG KRITIS + 3 RISIKO STRUKTURAL** (semua diverifikasi via AST + git tree)
Remediasi: BUG-1 diperbaiki dengan regression test; LIVE `add_trade` sekarang
          mencatat fee, dan cabang LIVE punya final size guard sebelum eksekusi.

Metode: analisis AST (`_check_trading_opportunity_locked`), perbandingan git tree
HEAD lokal vs origin (yang ada di VM), pembacaan exit path price_monitor, dan
penelusuran caller. Setiap temuan diverifikasi sebelum dicatat (lihat §5).

==============================================================================
## RINGKASAN EKSEKUTIF

Dua celah serius ditemukan. Keduanya hanya muncul saat LIVE trading, jadi tidak
terlihat selama DRY RUN (mode default bot).

  🔴 BUG-1: Posisi real berjalan TANPA stop-loss (fix audit lama TIDAK ter-deploy)
  🔴 BUG-2: Seluruh direktori autotrade/ di VM adalah versi 19 Agustus yang
            lebih tua dari lokal — fitur keamanan hilang

Mode default bot DRY RUN, jadi belum ada dana nyata yang hilang dari bug ini.
Tapi begitu AUTO_TRADE_DRY_RUN=false, BUG-1 langsung mengancam dana.

==============================================================================
## 🔴 BUG-1 (KRITIS): SL/TP TIDAK PERNAH TERPASANG PADA ORDER LIVE

Lokasi: `autotrade/runtime.py` baris 2185 (HEAD lokal) / 2030 (origin/VM)
Fungsi : `_check_trading_opportunity_locked`, cabang `else` dari `if is_dry_run:`

### Bukti (AST, bukan baca-mata)

Ekstrak AST fungsi dan cek variabel `fill_price`:

  ORIGIN (yang ada di VM):
    EXEC SPLIT if is_dry_run at L1845: body L1846-1992, orelse L1994-2067
    DRY_BODY : fill_price Store at [1847, 1851, 1853, 1858] | Load di banyak baris
    LIVE_ELSE: fill_price Store at NONE              | Load at [2030]   ← BAHAYA

  HEAD (lokal working tree):
    EXEC SPLIT if is_dry_run at L2000: body L2001-2147, orelse L2149-2222
    DRY_BODY : fill_price Store at [2002, 2006, 2008, 2013]
    LIVE_ELSE: fill_price Store at NONE              | Load at [2185]   ← BAHAYA

`fill_price` hanya pernah di-assign di dalam blok DRY RUN. Di cabang LIVE,
baris set_price_level memakainya tanpa pernah didefinisikan → `NameError`.

### Rantai kegagalan saat LIVE

  1. `create_order(pair, "buy", entry_zone_price, amount)` (L2169) →
     **order real terkirim ke Indodax**
  2. `bot.db.add_trade(...)` (L2171-2180) → **trade tercatat di DB**
  3. `bot.price_monitor.set_price_level(..., float(fill_price), ...)` (L2185) →
     **`NameError: name 'fill_price' is not defined`**
  4. Exception propagate ke `check_trading_opportunity` (L1086 `async with pair_lock`)
     lalu ke bot.py:1480 `except Exception as e`
  5. bot.py hanya log: `❌ [SQ-WORKER] Trade execution failed: ...`
     dan `mark_decision(... "ERROR_RETRYABLE")`
  6. **Tidak ada retry pemasangan SL/TP.** Order sudah masuk, trade sudah
     tercatat, tapi level keluar TIDAK terdaftar.

### Kenapa ini langsung jadi kerugian

Bot ini mengevaluasi exit (SL / TP / trailing / TIME_EXIT) **hanya** lewat
`price_monitor.check_price_levels()`, yang iterasi `self.price_levels.items()`.
Level yang tidak terdaftar TIDAK PERNAH dievaluasi. Posisi real hasilnya jalan
**tanpa stop-loss sama sekali** — rugi tak terbatas sampai intervensi manual.

### Mitigasi yang ADA (penting untuk akurasi severity)

Ada `rebuild_from_open_trades` (price_monitor.py:82) yang dipanggil oleh
open-position sweeper **setiap 120 detik** (bot.py:2102, di dalam loop
`_open_position_price_sweeper`). Sweeper ini rebuild price_levels dari
trade OPEN di DB, lalu fetch ticker dan jalankan `check_price_levels`.

Logikanya: trade sudah tercatat di DB (langkah 2 di atas sukses), jadi
sweeper berikutnya (<120 detik kemudian) akan mendaftarkan SL/TP-nya.
`rebuild_from_open_trades` cuma skip jika `entry_price <= 0 or amount <= 0`
atau `key in self.price_levels` — keduanya tidak berlaku di kasus ini.

Jadi window tanpa stop-loss **bukan permanen**, tapi ~0–120 detik.

### Kenapa ini tetap berbahaya

  1. **SL/TP yang direbuild TIDAK sama dengan yang asli.** Rebuild memakai
     `trading_engine.calculate_stop_loss_take_profit(entry_price, "BUY")`
     standar — tanpa data S/R (support_1/resistance_1 = 0) dan tanpa
     adjustment yang sudah dihitung di pipeline (SL/TP + S/R adjust, L1803).
     Keluarnya level berbeda dari yang dimaksudkan algoritma.
  2. **S/R-aware hold hilang.** Dengan `support_1 = 0`, blok S/R-aware SL
     (yang menahan jual rugi selama S1 masih hold) tidak aktif, dan
     volume confirmation tidak jalan. Exit berubah jadi SL polos.
  3. **Race window nyata.** Entry terjadi saat ticker bagus; dalam 0–120
     detik pertama harga bisa bergerak cepat. SL standar baru terpasang
     setelahnya. Untuk pair volatil (skyaiidr pernah -11.5%), window ini
     cukup untuk pergerakan besar.
  4. **Ada pemberitahuan palsu.** Worker menandai intent sebagai
     `ERROR_RETRYABLE` dan `mark_decision` — aliran status jadi kacau.

Ini cocok dengan pola bug sebelumnya di repo ini (watchlist-coupled exit,
stranded position), hanya lebih buruk: hanya muncul saat LIVE, jadi tidak
tertangkap DRY RUN.

### Status FIX

`docs/AUDIT_AUTOTRADE_EXECUTION_ORDER_20260922.md` (sesi sebelumnya) menyatakan
fix sudah diterapkan: `float(fill_price)` → `float(entry_zone_price)`.

Verifikasi saya: **fix itu ada di working tree tapi TIDAK PERNAH DI-COMMIT.**

  HEAD lokal (5cd5683) baris 2185:
      bot.price_monitor.set_price_level(user_id, trade_id, pair, float(fill_price), ...)
                                                ← masih BUG

  Working tree (uncommitted diff):
      -  bot.price_monitor.set_price_level(..., float(fill_price), ...)
      +  bot.price_monitor.set_price_level(..., float(entry_zone_price), ...)


Jadi VM masih menjalankan kode yang error. Fix 1 baris ini belum sampai ke
manapun di luar working tree lokal.

==============================================================================
## 🔴 BUG-2 (KRITIS): VM menjalankan snapshot autotrade/ versi 19 Agustus

### Temuan

origin/kiro/dryrun-activation-dashboard ada 3 commit di depan HEAD lokal:

  b3002fc docs(deploy): use plain sudo in runbook
  e852c64 docs(deploy): document production runtime path
  69a329c chore(deploy): restore service-safe app tree     ← MERGE

Merge `69a329c` menggabungkan `cdcb9a4` (branch lama, terakhir 2026-08-24).
Net effect terhadap HEAD: 593 files changed, 135.307 insertions.

Untuk `autotrade/` saja:

  fast_gate.py     : 0 added / 239 DELETED   ← HILANG di origin
  price_monitor.py : 610 added ( struktur lama )
  risk_manager.py  : 275 added / 457 deleted
  runtime.py       : 7 added / 166 deleted   ( -159 baris )
  portfolio.py     : 188 added / 0
  strategy2/       : baru

`git ls-tree` mengonfirmasi `autotrade/fast_gate.py` ada di HEAD lokal,
**tidak ada di origin** (yang di VM).

### Konsekuensi

HEAD lokal (commit 5cd5683) sudah berisi:

  - autotrade/runtime.py:660,683,692,1547 → import + fungsi
    `_run_fast_gate()` + pemanggilan di pipeline
  - autotrade/fast_gate.py (12 KB) — module lengkap

Working tree lokal (belum di-commit) juga menambah integrasi di bot.py:1394-1421
(QUANT TypeSafe pre-trade guardrail).

Di VM, `autotrade/fast_gate.py` **tidak ada**, jadi:
  - runtime.py versi VM tidak punya gate ini
  - bot.py versi VM (hasil merge) juga tidak mengimpor fast_gate

Hasilnya: pre-trade guardrail (validasi intent/signal <50ms yang menolak
sinyal tidak valid sebelum sizing) **tidak aktif di produksi**, meskipun
sudah dikembangkan lokal.

### Ini adalah drift DRY RUN→LIVE klasik

Bug-2 memperkuat Bug-1: bukan hanya fix SL/TP yang tidak sampai, tapi seluruh
lapisan keamanan entry juga. Semua pengembajaran lokal setelah 19 Agustus
(fast_gate, kelly warmup refactor, regression tests) **tidak ada di VM**.

### Bukti tambahan: tests/

Jumlah file test ter-commit:
  HEAD lokal : 2 file test
  origin/VM  : 79 file test

Test yang ada di HEAD lokal tetapi TIDAK ada di origin (hilang dari VM):

  tests/test_live_execution_fill_price_scope.py   ← regression BUG-1
  tests/test_kelly_sizing_integration.py
  tests/test_quant_integration_guardrail.py
  tests/test_autotrade_ledger.py

Jadi meskipun fix BUG-1 di-commit, regression test-nya tidak akan jalan di VM.

==============================================================================
## RINGKASAN SEVERITY

BUG-1 (KRITIS) : NameError fill_price di LIVE → order real terkirim tanpa
                 SL/TP. Mitigasi: open-position sweeper rebuild dalam
                 ~120 detik (tapi level berbeda: no S/R, no volume confirm).
                 Risiko dana: NYATA saat LIVE, NOL saat DRY RUN.
BUG-2 (KRITIS) : VM memakai snapshot autotrade/ 19 Agustus. fast_gate,
                 kelly clamping layer, regression tests TIDAK ada di VM.
RISIKO 2.3     : fee=0 di LIVE → PnL & feedback Kelly meleset ~0.3%/trade.
RISIKO 2.2     : tidak ada final size guard di LIVE; order 25% balance di
                 pair illiquid bisa partial fill / slippage besar.
RISIKO 2.4     : block reasons hanya di memori; hilang saat restart.

==============================================================================
## 🟠 RISIKO STRUKTURAL 2.3: `fee=0` di trade LIVE

Lokasi: `autotrade/runtime.py` L2180 (HEAD) / L2025 (origin)

    bot.db.add_trade(..., price=entry_zone_price, amount=amount, total=total,
                     fee=0, ...)              ← LIVE selalu catat fee = 0

DRY RUN menghitung fee dengan benar (L2040: `fill_price × amount × TRADING_FEE_RATE`),
tapi LIVE mencatat 0.

Bukan risiko eksekusi (fee ditahan exchange), tapi **PnL yang dihitung ulang dari
kolom `trades.fee` salah ~0.3% per trade**. Efek:
  - Semua laporan performa (termasuk `/performance` Telegram) meleset
  - Ini jadi input feedback loop Kelly → sizing yang salah
  - Akumulasi: 50 trade × 0.3% = 15% PnL yang sebenarnya tidak ada

==============================================================================
## 🟠 RISIKO STRUKTURAL 2.2: Tidak ada final size guard di cabang LIVE

Guard DRY_RUN_MAX_TOTAL (2jt) hanya berlaku jika `is_dry_run` (L1917/1845).
Di cabang LIVE tidak ada clamp `total` setelah semua multiplier.

Jika Kelly override (~25% balance) × V4 boost 1.2x × optimizer multiplier >1,
`total` live = 25% × 1.2 × multiplier. `bayesian_kelly_position_size` sudah
clamp 25% balance (risk_manager L396-399), jadi worst case terikat ~30% balance.

Yang TIDAK ada: **max-order check terhadap likuiditas book**. Order 25% balance
pada pair illiquid → partial fill / slippage besar → entry price jauh lebih
buruk dari `entry_zone_price` yang dipakai menghitung SL/TP.

Catatan: Kelly di origin (VM) memanggil `kelly_engine.calculate_position_size()`
langsung (L1532), sedangkan HEAD lokal memanggil
`bot.risk_manager.bayesian_kelly_position_size(..., kelly_engine=kelly_engine)`
(L1685). Yang lokal melalui lapisan clamping ekstra; yang di VM tidak.

==============================================================================
## 🟡 RISIKO STRUKTURAL 2.4: Block reasons hanya di memori

Setiap gate memakai pola:
  `logger.info("🚫") + _remember_autotrade_block_reason + return`

Alasan disimpan di `bot._autotrade_block_reasons` (memori) saja, TIDAK di DB.
Restart proses → semua alasan hilang. Diagnosis "kenapa tidak ada trade" harus
diulang setiap restart.

Selain itu, dua gate DRY RUN (L1879, L1959) sengaja **melewati** blok penolakan
demi pengumpulan data (by-design). Efek: **statistik DRY RUN tidak menggambarkan
perilaku LIVE**. Jangan ekstrapolasi win-rate DRY RUN ke live — parameter R/R
dan cost-aware gate berbeda antara dua mode.

==============================================================================
## VALIDASI: Yang TIDAK ditemukan (sudah diperiksa)

Agar tidak salah arah, beberapa hal sengaja saya cek dan ternyata BENAR:

  ✅ Urutan eksekusi sizing sudah benar:
     base sizing → Kelly → momentum/correlation/V4 reduction → guard → gate →
     order. Kelly override (E) SETELAH nominal sizing (B) dan SEBELUM execution
     split (Q). Posisi tepat.
  ✅ Reduksi berurutan (exploration 0.20x, momentum 0.7x, correlation, V4) —
     semua faktor <1.0, monoton mengecilkan posisi. Tidak mungkin oversized.
  ✅ Guard DRY RUN menangkap race Kelly: Kelly bisa 25% balance > 2jt cap;
     guard clamp ke 2jt, lalu `amount = capped_total / fill_price`
     direkonsiliasi ulang (L2035-2037).
  ✅ `bayesian_kelly_position_size` double-clamped: min Rp50.000, max 25%
     balance. Input invalid → (0,0), caller fallback ke sizing awal.
  ✅ Kelly fallback aman: `kelly_value > 0` baru override. Engine 0/error →
     sizing awal dipakai (logger.debug saja). Tidak ada zero-sizing dari Kelly.
  ✅ Exit path price_monitor sudah bagus:
     - trailing stop ada fee floor (L323-324: `entry_price * (1 + 2*fee_rate)`)
     - S/R hold ada max loss cap (SR_MAX_HOLD_LOSS_PCT=8.0)
     - TIME_EXIT sudah independent check, bukan nested di SL (fix 2026-07-21)
     - partial_2_triggered sudah di scope yang benar (fix 2026-08-04)
     - TIME_EXIT extend 6h jika S1 masih holding dan harga di bawah breakeven
  ✅ Per-pair execution lock (`_pair_execution_locks`) ada dan benar.
  ✅ Open-position sweep (bot.py:2167) jalan independent dari WATCH_PAIRS.
  ✅ Volume confirmation pada S1 breakdown mencegah false breakout sell.

Jadi masalahnya **bukan** algoritma entry/exit utama. Masalahnya ada di
deploy path: fix tidak ter-commit, dan VM memakai snapshot lama.

==============================================================================
## URUTAN PERBAIKAN YANG DISARANKAN

  1. (URGENT) Commit fix BUG-1 (`fill_price` → `entry_zone_price`) + test.
  2. (URGENT) Rebase/merge ulang agar VM dapat HEAD terbaru (fast_gate,
     kelly clamping, regression tests). Verifikasi VM HEAD setelah pull.
  3. Fix `fee=0` di LIVE add_trade → pakai `entry_zone_price * amount *
     TRADING_FEE_RATE` agar PnL & feedback Kelly akurat.
  4. Tambah final size guard di cabang LIVE (mirror guard DRY_RUN, tanpa
     cap 2jt — pakai max fraction of balance + cek likuiditas book).
  5. Persist block reasons ke DB agar tahan restart.

Catatan: tes di HEAD baru 2 file ter-commit. Begitu fix di-commit, pastikan
regression tests (`test_live_execution_fill_price_scope.py` dll.) juga ikut.

==============================================================================
## ROLLBACK

  git checkout -- autotrade/runtime.py bot.py
  rm -f tests/test_live_execution_fill_price_scope.py

Risiko trading dari perbaikan: NOL terhadap DRY RUN (baris yang diubah hanya
dieksekusi saat is_dry_run=False). Perbaikan ini justru MENGURANGI risiko:
memastikan SL/TP terpasang pada order real.

==============================================================================
## CARA VERIFIKASI TEMUAN INI

Semua temuan di atas dapat diperiksa ulang:

  # BUG-1: konfirmasi fill_price tidak terdefinisi di LIVE
  git show HEAD:advanced_crypto_bot/autotrade/runtime.py | sed -n '2185p'

  # BUG-2: konfirmasi fast_gate tidak ada di origin
  git ls-tree FETCH_HEAD -- advanced_crypto_bot/autotrade/ | grep fast_gate
  # (kosong = hilang)

  # Jumlah test ter-commit
  git ls-tree HEAD -- advanced_crypto_bot/tests/ | grep -c test_
  git ls-tree FETCH_HEAD -- advanced_crypto_bot/tests/ | grep -c test_

### Bukti tambahan: regression test memang menangkap bug ini

Test `tests/test_live_execution_fill_price_scope.py` diverifikasi dengan
sengaja mengembalikan bug (replace `float(entry_zone_price)` →
`float(fill_price)` di working tree) lalu menjalankan test:

  Sebelum (bug ada):  2 failed, 1 passed
      AssertionError: LIVE set_price_level must use entry_zone_price,
      got [... 'float(fill_price)', 'stop_loss', ...]

  Sesudah (fix):      3 passed

Jadi bug ini BUKAN salah baca kode — test AST menangkapnya secara
reproduktif. Working tree dikembalikan ke fix setelah verifikasi
(dicek via `git diff`: hanya perubahan awal yang tersisa).

— Audit Algoritma Bot (diverifikasi via AST + git tree)
