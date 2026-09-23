# Audit Checkpoint AutoTrade Dry-Run — 14 Agustus 2026

Checkpoint awal: 13 Agustus 2026 pukul 16:33 WIB

Audit aktual: 14 Agustus 2026 pukul 22:30 WIB

Target: Google Compute Engine `instance-20260609-044439`

Branch runtime: `kiro/dryrun-activation-dashboard`

Commit runtime: `ab4b7c7`

## Kesimpulan

AutoTrade tidak lagi mengalami kondisi nol posisi. Sejak rekonsiliasi equity peak
pada 12 Agustus 2026, bot membuat 9 BUY fill dan 9 SELL fill, menghasilkan sembilan
round-trip yang seluruhnya telah ditutup. Karena kondisi pemicu "tetap 0 posisi"
tidak terjadi, threshold tidak diubah dan counterfactual `NO_ENTRY` tidak menjadi
syarat remediasi checkpoint ini.

Hasil trading awal belum baik: satu transaksi menang, delapan kalah, dengan total
realized P&L dry-run `-Rp274.657,63`. Sampel sembilan transaksi belum cukup untuk
menyimpulkan profitabilitas strategi, tetapi cukup untuk membuktikan execution
spine sekarang membuka dan menutup posisi.

## Bukti runtime dan queue

| Pemeriksaan | Hasil |
|---|---:|
| Service | `active/running` |
| Proses `bot.py` | 1 |
| `NRestarts` | 0 |
| Queue pending | 0 |
| Queue inflight | 0 |
| Runtime/queue exception pada log aktif | 0 |
| Circuit-breaker block pada log aktif | 0 |
| Database locked pada log aktif | 0 |

## Ledger

| Entitas | Jumlah |
|---|---:|
| Intent total | 7.633 |
| Intent sejak rekonsiliasi | 7.632 |
| Normalized orders | 20 |
| Normalized fills | 18 |
| Normalized position rows | 7 |
| Posisi OPEN saat audit | 0 |
| Posisi CLOSED | 7 |
| Legacy trades | 9 |
| Legacy pending orders | 2 |
| Rejection envelopes | 21 |

Invariant ledger yang diperiksa seluruhnya lulus:

- tidak ada order dengan `total != limit_price × quantity`;
- tidak ada fill dengan `total != price × quantity`;
- tidak ada fill orphan;
- tidak ada FILLED order tanpa fill;
- tidak ada OPEN position dengan quantity nol;
- tidak ada CLOSED position dengan quantity nonzero.

## Kinerja awal

| Metrik | Hasil |
|---|---:|
| Closed trades | 9 |
| Menang | 1 |
| Kalah | 8 |
| Win rate | 11,11% |
| Realized P&L | -Rp274.657,63 |
| Rata-rata P&L | -1,6505% per trade |
| Terburuk | -4,0998% |
| Terbaik | +1,4840% |
| Fee simulasi | Rp95.490,82 |
| Gross turnover | Rp31.830.274,68 |

Semua posisi ditutup dalam periode relatif singkat. Evaluasi strategi berikutnya
harus menguji apakah exit terlalu cepat, entry terlambat, atau biaya 0,3% per sisi
meniadakan edge. Jangan mengubah threshold berdasarkan sembilan trade saja.

## Distribusi keputusan

Sejak rekonsiliasi:

| Recommendation | Status | Reason code | Jumlah |
|---|---|---|---:|
| SELL | NO_ENTRY | `NO_ORDER_CREATED` | 4.543 |
| BUY | NO_ENTRY | `NO_ORDER_CREATED` | 1.937 |
| BUY | NO_ENTRY | `ENTRY_QUALITY` | 615 |
| BUY | NO_ENTRY | `OTHER` | 404 |
| BUY | NO_ENTRY | `V4_FILTER` | 109 |
| BUY | FILLED | `DRYRUN_FILL` | 9 |
| SELL | FILLED | `DRYRUN_SELL_FILL` | 9 |
| BUY | NO_ENTRY | `ENTRY_EDGE` | 6 |

`ENTRY_QUALITY` terutama berasal dari tren MTF yang tidak selaras. `V4_FILTER`
berasal dari prediksi `BAD_BUY`. Sebagian besar `OTHER` sebenarnya berisi alasan
`Edge score too low (< 56)`, sehingga taxonomy reason code belum cukup presisi.

`NO_ORDER_CREATED` pada SELL umumnya konsisten dengan tidak adanya posisi yang
bisa dijual. Namun 1.937 BUY dengan reason generik menunjukkan beberapa cabang
runtime masih return tanpa merekam block reason spesifik. Ini adalah observability
gap, bukan bukti threshold perlu diturunkan.

## Temuan engineering

### F1 — Normalized pending order tidak mengikuti cancellation

Dua order (`aihidr` dan `homeidr`) berstatus `CANCELLED` pada `pending_orders`,
tetapi tetap `PENDING` pada `autotrade_orders`. Intent terkait kemudian berakhir
sebagai `NO_ORDER_CREATED`.

Risiko:

- dashboard/rekonsiliasi normalized menampilkan pending palsu;
- invariant lifecycle berbeda antara legacy dan normalized ledger;
- retry atau cleanup dapat mengambil keputusan dari status stale.

Rekomendasi: cancellation harus memperbarui legacy pending, normalized order,
dan intent dalam satu transaction boundary dengan reason terminal yang spesifik.

### F2 — Equity peak dry-run mengalami double counting

Setelah equity peak direkonsiliasi ke Rp50.000.000, nilai peak meningkat menjadi
Rp52.004.523 ketika posisi dry-run dibuka. `users.balance` tetap Rp50.000.000,
sementara `_calculate_equity()` menambahkan nilai semua posisi terbuka ke saldo
tersebut. Karena dry-run BUY tidak mendebit saldo, posisi dihitung dua kali.

Risiko:

- peak equity semu;
- drawdown palsu ketika posisi ditutup;
- circuit breaker dapat berhenti lagi walaupun kerugian aktual belum mencapai
  batas maksimum.

Rekomendasi: gunakan satu accounting model konsisten:

1. debit/credit virtual cash pada setiap dry-run fill; atau
2. jika balance merupakan total portfolio NAV, jangan tambahkan position value
   lagi dalam `_calculate_equity()`.

Perbaikan harus disertai migration/reconciliation peak dan regression test untuk
BUY, unrealized mark-to-market, SELL, dan restart.

### F3 — Reason-code taxonomy terlalu generik

`OTHER` menampung edge-score rejection dan `NO_ORDER_CREATED` menampung banyak
BUY return path tanpa block reason. Ini menghambat counterfactual serta tuning
berbasis bukti.

Rekomendasi:

- map edge score menjadi `ENTRY_EDGE`;
- setiap early return runtime wajib memanggil block-reason recorder;
- tambahkan reason khusus `NO_OPEN_POSITION` untuk SELL tanpa posisi;
- acceptance test memastikan tidak ada actionable BUY berakhir generik.

## Keputusan checkpoint

- AutoTrade dry-run tetap aktif.
- Tidak ada threshold yang diturunkan.
- Tidak ada aktivasi live trading.
- Tidak ada reset drawdown tambahan.
- Prioritas implementasi berikutnya adalah F2, lalu F1, lalu F3.
- Evaluasi profitabilitas dilanjutkan setelah ledger equity valid dan minimal
  30–50 closed trades bersih tersedia.
