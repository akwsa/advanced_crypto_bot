# Roadmap — Autotrade Dry-Run Menuju Profitability Evidence

## Outcome

Membangun sistem dry-run yang menghasilkan trade secara terkontrol dan dapat
membuktikan apakah suatu strategi memiliki net expectancy positif. Profit tidak
dijanjikan; yang dijamin oleh roadmap ini adalah hasil eksperimen tidak lagi
terdistorsi oleh ledger drift, biaya yang tidak realistis, missing outcomes, atau
tuning pada data yang sama.

## Kondisi awal terukur — 24 Agustus 2026

| Bukti VM | Nilai |
| --- | ---: |
| Closed legacy auto trades | 19 |
| Net realized P&L | -Rp586.049 |
| Average return | -1,648% per trade |
| Trade outcomes lengkap | 4/19 |
| Normalized positions masih OPEN | 3 / Rp6.000.000 cost basis |
| Generic `NO_ORDER_CREATED` | 12.611 |
| Generic `OTHER` | 1.109 |
| Strategy 2 shadow decisions | 0 |

Circuit breaker 12,3% bukan bukti drawdown portfolio yang valid: normalized cash
sudah didebit untuk tiga posisi, tetapi kalkulasi equity membaca legacy trades yang
sudah ditandai CLOSED dan tidak menambahkan nilai posisi tersebut.

## Phase 0 — Pulihkan truth layer dan operasi

Estimasi: 2–4 hari engineering.

1. Jadikan fill journal, normalized positions, dan virtual cash sebagai sumber tunggal.
2. Perbaiki semua jalur SELL/partial SELL/stop/trailing agar menutup legacy projection
   dan normalized position dalam transaksi yang sama.
3. Ubah equity dan circuit breaker agar membaca normalized portfolio.
4. Tambahkan invariant auditor yang membandingkan journal, projections, cash, dan legacy.
5. Rekonsiliasi database VM melalui migration tervalidasi dan backup; jangan reset peak manual.
6. Migrasikan money fields target ke integer IDR/fixed-scale quantity dan tambahkan
   conservation checks pada setiap settlement.
7. Terapkan Redis writer lease + fencing token; hentikan runtime WSL dengan token/queue
   produksi sehingga VM menjadi single writer.
8. Perbaiki event-loop boundary Telegram agar worker tidak memakai client dari loop lain.
9. Kunci dependency environment dan simpan environment-manifest hash per experiment.

Acceptance gate:

- Given replay BUY → partial SELL → full SELL, when proses diulang, then cash,
  positions, legacy projection, dan equity identik serta idempotent.
- Tidak ada posisi `CLOSED` di legacy yang `OPEN` di normalized ledger atau sebaliknya.
- Circuit breaker memakai cash + mark-to-market dan tetap mengizinkan exit.
- Satu Telegram poller dan satu scheduler produksi; stale fencing token ditolak.
- Backup, reconciliation report, dan post-migration invariant audit tersedia.
- Full acceptance suite lulus di WSL dan VM.

## Phase 1 — Bangun evaluation and counterfactual spine

Estimasi: 4–7 hari engineering, lalu data berjalan kontinu.

1. Simpan snapshot canonical untuk setiap candidate sebelum gate pertama.
2. Ganti semua normal-path `NO_ORDER_CREATED`/`OTHER` dengan taxonomy spesifik.
3. Label accepted dan rejected candidate pada horizon 15m, 1h, 4h, dan 24h.
4. Hitung executable net return setelah fee, spread, slippage, dan latency.
5. Buat laporan per gate: candidates seen, rejected, avoided loss, missed profit,
   incremental expectancy, dan confidence interval.
6. Perbaiki outcome worker agar coverage terminal trade mencapai 100%.
7. Bekukan definisi executable entry/exit, latency, horizon, dan `UNSCORABLE` untuk
   quote yang stale/missing.

Acceptance gate:

- 100% actionable candidates memiliki terminal reason dan outcome labels setelah horizon matang.
- Generic reason di bawah 0,5% dan hanya untuk internal error.
- Laporan dapat menjawab apakah `ENTRY_QUALITY`, `MARKET_INTELLIGENCE`, dan `V4_FILTER`
  menambah atau mengurangi net expectancy.

## Phase 2 — Tetapkan champion sederhana dan simulator realistis

Estimasi: 4–6 hari engineering.

1. Pisahkan policy Strategy 1 dari side effect runtime melalui adapter typed intent.
2. Version-kan satu simulator fill yang dipakai replay dan live dry-run.
3. Batasi universe pada pair dengan liquidity, spread, history completeness, dan listing age memadai.
4. Buat baseline sederhana: regime filter + momentum/mean-reversion yang eksplisit,
   satu entry, satu hard invalidation, satu time stop, satu profit protection.
5. Bekukan parameter champion selama satu evaluation window; tidak ada adaptive tuning intrawindow.
6. Tambahkan aggregate sequence/CAS dan idempotent retry pada seluruh lifecycle event.

Acceptance gate:

- Replay deterministik menghasilkan fill dan P&L yang sama dengan input sama.
- Setiap fill membukukan seluruh biaya dan memenuhi tick/size precision.
- Baseline mengalahkan no-trade dan random-entry benchmark setelah biaya pada validation window.

## Phase 3 — Selesaikan Strategy 2 sebagai challenger penuh

Estimasi: 5–8 hari engineering.

1. Ubah shadow hook menjadi pure policy yang menghasilkan intent/rejection.
2. Jalankan lifecycle isolated: CANDIDATE → ARMED → PENDING → OPEN_RISK → protection → CLOSED.
3. Pakai simulator yang sama dengan champion, tetapi cash/positions terpisah.
4. Tambahkan invalidation, time stop, stale-data handling, dan portfolio exposure constraints.
5. Simpan attribution setiap keputusan dan hasil per strategy/config version.

Acceptance gate:

- Strategy 2 menghasilkan closed shadow trades dan equity curve tanpa menyentuh Strategy 1.
- Snapshot yang sama dapat direplay tanpa keputusan/fill ganda.
- Seluruh state transition dan accounting invariant lulus property/regression tests.

## Phase 4 — Walk-forward shadow experiment

Durasi minimum awal: `[ASSUMPTION]` 30 hari dan 100 closed trades per kandidat.

1. Tuning hanya pada train window; validation dan test berjalan ke depan dengan embargo.
2. Bandingkan champion, Strategy 2, no-trade, dan benchmark sederhana pada snapshot sama.
3. Laporkan net expectancy, profit factor, win/loss payoff, max drawdown, turnover,
   exposure time, tail loss, stability per regime, dan bootstrap confidence interval.
4. Jangan mengubah parameter selama satu run; perubahan membuat experiment version baru.

Promotion gate awal `[ASSUMPTION]`:

- net expectancy > 0 setelah seluruh biaya;
- profit factor ≥ 1,20;
- max drawdown ≤ 10%;
- sekurangnya 100 closed trades dan 30 hari multi-regime;
- bootstrap probability bahwa expectancy positif ≥ 95%;
- tidak ada satu pair yang menyumbang >35% total profit;
- challenger mengalahkan champion pada out-of-sample, bukan hanya aggregate history.

## Phase 5 — Promotion dan operasi berkelanjutan

1. Promotion adalah perubahan konfigurasi/version yang dapat di-rollback, bukan edit inline.
2. Jalankan champion lama sebagai shadow selama masa probation.
3. Auto-demote jika data integrity gagal, drawdown melewati limit, atau rolling expectancy negatif.
4. Dashboard menampilkan health data, ledger invariants, strategy comparison, dan promotion state.
5. Promotion fail-closed atas sealed report; metric yang hilang atau approval yang belum ada
   selalu menolak promotion.

## Urutan implementasi yang direkomendasikan

Mulai dengan Phase 0 dalam tiga slice reviewable:

1. **Canonical equity:** normalized portfolio valuation dan circuit-breaker tests.
2. **Atomic close:** satukan seluruh SELL/stop/trailing settlement dan reconciliation auditor.
3. **Single writer:** VM-only runtime plus Telegram event-loop repair.

Jangan menurunkan gate atau mereset drawdown sebelum ketiga slice tersebut selesai.
Trade yang lebih banyak pada accounting yang salah hanya memperbesar data yang tidak dapat dipercaya.
