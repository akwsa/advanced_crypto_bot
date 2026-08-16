# AutoTrade Dry-Run Decision/Execution Spine

> Status deployment, hotfix runtime, rekonsiliasi circuit breaker, bukti test,
> dan rollback terbaru tersedia di
> [Handoff 2026-08-12](HANDOFF_2026-08-12_autotrade_execution_repair.md).

Jalur eksekusi resmi adalah market scan → Redis `SignalQueue` → `TradeIntent`
→ runtime policy → dry-run order/fill → ledger position. Queue menyimpan snapshot
semantik lengkap; worker tidak boleh menggantinya dengan `signal=None`. Envelope
dengan ID unik diklaim atomik ke inflight, di-ack setelah outcome durable, dan
dipulihkan saat restart. Backlog tidak dihapus; payload malformed dicatat skipped.

## Kontrak dan reason code

Setiap intent memiliki `version`, `correlation_id`, dan `idempotency_key` stabil.
Payload invalid dicatat sebagai skipped dengan reason `MISSING_PAIR`,
`INVALID_RECOMMENDATION`, `INVALID_PRICE`, `STALE_SIGNAL`, atau
`UNSUPPORTED_CONTRACT_VERSION`. Outcome runtime disimpan di
`signal_queue:decisions`. Fill dan pending order memakai `DRYRUN_FILL` dan
`DRYRUN_LIMIT_PENDING`.

## Ledger

Tabel `autotrade_intents`, `autotrade_orders`, `autotrade_fills`, dan
`autotrade_positions` bersifat additive. Unique key mencegah logical order/fill
ganda. Invariant wajib: price dan quantity positif, `total = price × quantity`,
fee non-negatif, dan position dapat dihitung ulang dari fills. Tabel `trades`
tetap dipertahankan sebagai projection kompatibilitas.
BUY menambah position; SELL mengurangi quantity/cost basis dan menutupnya saat
quantity nol. Projection dapat dibangun kembali dari jurnal fill terurut.

### Accounting kas dan equity

`users.balance` adalah kas virtual canonical, bukan total NAV. BUY fill mendebit
`total + fee`; SELL fill mengkredit `proceeds - fee`. Equity circuit breaker
selalu dihitung sebagai kas tersebut ditambah mark-to-market seluruh posisi
OPEN. Debit/kredit berada dalam transaksi yang sama dengan order, fill, dan
position sehingga replay tidak mengubah kas dua kali dan kegagalan me-rollback
seluruh ledger.

Deployment dari versi lama wajib menjalankan backup database dan preflight
jumlah posisi OPEN. Hanya state closed-only yang boleh direkonsiliasi melalui
`Database.reconcile_closed_dryrun_cash(user_id, baseline_cash)`. Fungsi ini
membangun kas deterministik dari normalized BUY/SELL fills, menyetel peak ke
equity baru, idempotent, dan menolak migrasi jika salah satu ledger masih OPEN.

### Pending cancellation dan taxonomy NO_ENTRY

Cancellation adalah terminal settlement tunggal. `pending_orders` dan
`autotrade_orders` berubah menjadi `CANCELLED`, sedangkan intent berubah menjadi
`NO_ENTRY` dengan `PENDING_CHASE_CANCELLED` atau
`PENDING_TIMEOUT_CANCELLED` dalam transaksi database yang sama.

Reason code terminal yang dipakai untuk counterfactual meliputi
`NO_OPEN_POSITION`, `ENTRY_EDGE`, `ENTRY_QUALITY`, `PRICE_INVALID`,
`POSITION_SIZING`, `LIQUIDITY`, `PAIR_GUARD`, `CORRELATION`,
`CHASE_PREVENTION`, `COST_AWARE`, `R/R_FLOOR`, `V4_FILTER`, `DRAWDOWN`, dan
`DAILY_LOSS`, `CVAR`, `PAIR_FILTER`, `MARKET_INTELLIGENCE`, `SIGNAL_INVALID`,
`NON_ACTIONABLE_SIGNAL`, `DUPLICATE_SIGNAL`, `DUPLICATE_POSITION`,
`EXECUTION_VETO`, dan `WATCH_ONLY`. `OTHER` hanya diperbolehkan untuk kegagalan
internal yang belum dikenali; jalur BUY/SELL yang diketahui harus merekam reason
spesifik sebelum return.

## Operasi dan rollback

Mode harus tetap `AUTO_TRADE_DRY_RUN=true`. Jangan aktifkan private-order API.
Pantau pending/skipped/decision queue dan reason code sebelum tuning gate.
Rollback aplikasi cukup mengembalikan kode lama; schema additive boleh dibiarkan
karena tidak mengubah tabel legacy. Jangan menghapus tabel/data historis.
Setelah rollback accounting, jangan meneruskan trading dengan balance hasil
model baru memakai kode lama: hentikan service atau pulihkan backup database
bersama rollback kode untuk mencegah model kas tercampur.

Jika replay atau acceptance test gagal, hentikan rollout. Dokumentasikan bukti
dan susun Strategi 2 dari sumber primer/GitHub sebelum perubahan strategi;
jangan melonggarkan gate hanya untuk menghasilkan posisi.
