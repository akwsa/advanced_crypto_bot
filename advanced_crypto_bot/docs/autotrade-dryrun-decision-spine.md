# AutoTrade Dry-Run Decision/Execution Spine

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

## Operasi dan rollback

Mode harus tetap `AUTO_TRADE_DRY_RUN=true`. Jangan aktifkan private-order API.
Pantau pending/skipped/decision queue dan reason code sebelum tuning gate.
Rollback aplikasi cukup mengembalikan kode lama; schema additive boleh dibiarkan
karena tidak mengubah tabel legacy. Jangan menghapus tabel/data historis.

Jika replay atau acceptance test gagal, hentikan rollout. Dokumentasikan bukti
dan susun Strategi 2 dari sumber primer/GitHub sebelum perubahan strategi;
jangan melonggarkan gate hanya untuk menghasilkan posisi.
