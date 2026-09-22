# UX Specs Phase 1 — Read-only Dashboard

> Scope: Phase 1 dashboard hanya read-only. Tidak ada tombol buy/sell, trade ticket, save plan, SL/TP write, hunter toggle, emergency stop, atau real-trading control.

---

## 1. Tujuan UX

Dashboard Phase 1 harus membantu user menjawab cepat:

1. Bot/dashboard sedang sehat atau bermasalah?
2. Pair apa saja yang aktif/terpantau?
3. Pair mana yang sedang memiliki posisi trading/scalping OPEN?
4. Sinyal terbaru apa yang muncul?
5. Chart pair terpilih terlihat bagaimana?
6. Apakah semua trading/hunter tetap terkunci dalam DRY RUN?

Prinsip utama: **lihat status dan posisi dengan cepat, tanpa kemampuan mengubah state trading**.

---

## 2. Layout Desktop 4 Panel

```text
┌──────────────────────────────────────────────────────────────┐
│ Health / Safety Bar                                          │
│ DRY RUN LOCKED | API | Bot heartbeat | SQLite | Redis        │
├───────────────────────────────┬──────────────────────────────┤
│ Active Pairs + Open Positions │ Latest Signals               │
│ - pair cards                  │ - signal list/table          │
│ - selected open position      │ - confidence/freshness       │
│ - quick filter/search         │                              │
├───────────────────────────────┴──────────────────────────────┤
│ Chart + Trades                                                │
│ - TradingView selected pair chart                             │
│ - trade history/open positions table                          │
└──────────────────────────────────────────────────────────────┘
```

### Panel A — Health / Safety Bar

Menampilkan:

- `DRY RUN LOCKED` sebagai banner paling menonjol.
- API online/offline.
- Bot heartbeat fresh/stale/offline.
- Trading DB read-only status.
- Signal DB read-only status.
- Redis status jika tersedia.

Tidak boleh ada tombol enable/disable trading.

### Panel B — Active Pairs + Open Positions

Menampilkan:

- daftar pair aktif dari watchlist,
- harga terakhir jika tersedia,
- freshness harga,
- badge jika pair punya posisi OPEN,
- klik pair memilih chart.

Jika ada posisi OPEN, pair tersebut harus mudah terlihat karena ini goal utama user.

### Panel C — Latest Signals

Menampilkan:

- waktu sinyal,
- pair,
- rekomendasi,
- confidence,
- source/freshness,
- state empty/error bila belum ada sinyal.

Tidak boleh ada tombol execute signal.

### Panel D — Chart + Trades

Menampilkan:

- `price_history` read is aligned with `bot.py::_get_chart_history_for_pair` / `Database.get_price_history`: take the latest N candles for the selected active pair, then sort oldest → newest for rendering.
- Dashboard chart rendering uses local Lightweight Charts candlestick + volume data from `/api/v1/pairs/{pair}/chart`; TradingView remains only as a non-editable fallback.
- Chart selection is driven by the pair clicked in Active Pairs; inactive watchlist pairs must return `404 pair_not_active` and must not render a chart.

Tidak boleh ada trade ticket atau save plan di Phase 1.

#### Visual styling chart panel

Goal: chart harus **bersih dan jelas walau garis tipis**, bukan tebal. Garis cukup tipis-kontinu — yang penting tetap satu garis utuh, bukan titik-titik.

- Default `chartModel` adalah `bold-line` (close-price line) supaya pergerakan harga terbaca cepat.
- Garis dan price-line dijaga setipis mungkin namun tetap kontras:
  - `bold-line`: `lineWidth: 1`, `priceLineWidth: 1`, `crosshairMarkerRadius: 2`, warna `#fde68a` (soft yellow) dengan `lastValueVisible: true`.
  - `area-trend`: `lineWidth: 1`, `priceLineWidth: 1`, warna garis `#7dd3fc` (soft sky), fill area opacity sangat rendah (sekitar `0.24` top / `0.03` bottom) supaya garis tipis tetap fokus.
  - `clear-candles`: candlestick dengan body hijau/merah kontras (`#16a34a` / `#dc2626`) dan border/wick lebih terang.
  - `tradingview`: tetap sebagai fallback eksternal dan tidak diatur dari frontend.
- Volume histogram di-render sebagai layer sekunder di bawah price (margin atas ~0.82) dengan warna semi-transparan (hijau/merah opacity ~0.34) supaya tidak menutupi line/candle.
- Static regression test (`tests/test_dashboard_frontend_static.py::test_frontend_chart_graphics_use_clean_thin_high_contrast_lines`) menjaga preferensi setipis-mungkin-tetap-jelas ini dan menolak regresi ke `lineWidth: 2`/`3`/`4`, `priceLineWidth: 2`/`3`, atau `crosshairMarkerRadius: 3`/`4`/`6`.

Catatan: penyesuaian visual ini murni frontend; tidak menambah tombol trading, tidak mengubah endpoint chart, dan tetap dalam scope Phase 1 read-only.

---

## 3. State Wajib per Panel

Setiap panel harus punya state berikut:

| State | Arti | Tampilan |
|---|---|---|
| `fresh` | data terbaru masih valid | badge hijau/normal |
| `stale` | data ada tapi melewati TTL | badge kuning + timestamp |
| `offline` | sumber data tidak bisa dihubungi | badge merah + fallback info |
| `empty` | source sehat tetapi belum ada data | empty state ramah |
| `unknown` | source optional belum tersedia | badge abu-abu |
| `error` | request gagal | pesan error tanpa crash UI |

UI tidak boleh blank tanpa penjelasan.

---

## 4. Mobile Responsive Basic

Untuk layar kecil:

```text
1. Health / DRY RUN bar
2. Open Positions
3. Active Pairs
4. Chart selected pair
5. Latest Signals
6. Trades History
```

Interaksi minimal:

- tap pair/position untuk mengganti chart,
- tabel boleh menjadi card list,
- tidak ada sidebar wajib,
- semua informasi safety tetap terlihat di atas.

---

## 5. Realtime UX

Phase 1 memakai native SSE/EventSource:

- jika SSE connect: panel update dari event,
- jika SSE putus: tampilkan `reconnecting`/`stale`,
- fallback polling tiap 10 detik,
- tidak memakai Socket.IO.

SSE hanya membaca/mengirim event status. Tidak ada command dari frontend ke bot.

---

## 6. Guardrails UX

Yang tidak boleh muncul di Phase 1:

- tombol BUY/SELL,
- tombol approve order,
- trade ticket calculator,
- save trade plan,
- SL/TP write form,
- SmartHunter/AutoHunter toggle,
- AutoTrade toggle,
- emergency stop,
- input API key/secret,
- real trading enable/disable.

Jika konsep ini diperlukan nanti, pindahkan ke Phase 1.5+/Future dan butuh approval baru.

---

## 7. Acceptance Criteria UX

### AC-UX-1 — Safety selalu terlihat

Given dashboard dibuka
When data API berhasil dimuat
Then user melihat banner `DRY RUN LOCKED`
And tidak ada tombol untuk membuka real trading.

### AC-UX-2 — Posisi open mudah ditemukan

Given ada trade dengan status OPEN
When user membuka dashboard
Then pair tersebut muncul di panel open positions
And klik pair menampilkan chart TradingView pair tersebut.

### AC-UX-3 — Source bermasalah tidak membuat layar kosong

Given Redis atau SQLite sedang offline/locked
When panel memuat data
Then panel menampilkan state `offline`, `stale`, atau `error`
And UI tetap bisa digunakan untuk panel lain.

### AC-UX-4 — Tidak ada write control

Given user membuka seluruh dashboard Phase 1
When user melihat semua panel
Then tidak ada tombol/form untuk POST/PUT/PATCH/DELETE trading state.
