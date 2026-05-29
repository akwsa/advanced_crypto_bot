# CATATAN_BMAD_GEMINI_ML_SCALPING_INDODAX_2026-05-29

## Sumber

User meminta mencatat dan meneliti percakapan dengan Gemini tentang model Machine Learning untuk bot scalping Indodax.

Inti rekomendasi Gemini:

1. **XGBoost / LightGBM** paling praktis untuk scalping karena ringan, cepat inferensi, dan kuat untuk data tabular.
2. **LSTM / GRU** cocok untuk time-series sequence, tetapi lebih berat, rawan overfitting, dan butuh data besar.
3. **Reinforcement Learning / PPO** paling mutakhir secara konsep, tetapi sulit karena butuh environment realistis termasuk fee, slippage, spread, dan order execution.
4. Untuk Indodax, fitur penting tidak cukup hanya OHLC/candlestick:
   - order book imbalance / bid-ask depth,
   - spread IDR yang berubah-ubah,
   - fee maker/taker,
   - target profit harus lebih besar dari biaya transaksi dan risiko slippage.

## Analisis terhadap kondisi project saat ini

Status dari inspeksi repo saat catatan dibuat:

- Model ML existing sudah berbasis scikit-learn ensemble:
  - `analysis/ml_model_v2.py` memakai `RandomForestClassifier` + `GradientBoostingClassifier`.
  - `analysis/ml_model_v4.py` juga memakai `RandomForestClassifier` + `GradientBoostingClassifier`, dengan label outcome trade/signal.
- Belum terlihat penggunaan LightGBM/XGBoost di kode aktif.
- V2 sudah punya fitur teknikal OHLCV cukup luas: returns, SMA, volatility/ATR, volume anomaly, RSI, MACD, Bollinger, support/resistance, regime.
- V4 lebih fokus ke outcome signal/trade: harga signal, confidence, recommendation encoding, waktu, symbol hash, dan label GOOD/BAD/NEUTRAL BUY/SELL.
- Project sudah punya market-intelligence berbasis orderbook di `autotrade/runtime.py`:
  - `analyze_market_intelligence()` mengambil `bot.indodax.get_orderbook(pair, limit=20)`.
  - Menghitung notional bid/ask dan `buy_sell_ratio`.
  - Mengubah pressure menjadi `BULLISH` / `BEARISH` / `NEUTRAL` memakai `Config.MI_ORDERBOOK_BULLISH_MIN`.
  - Entry bisa diblokir bila `passes_entry_filter` gagal.
- Project sudah punya fee-aware gating:
  - `Config.TRADING_FEE_RATE` dipakai di autotrade untuk `effective_tp`, `effective_sl`, dan `rr_after_fees`.
  - `core/profit_optimizer.py` memblokir setup jika `rr_after_fees` di bawah dynamic floor.
  - `scalper/scalper_module.py` memakai `ScalperConfig.TRADING_FEE_PCT = 0.003` untuk PnL dan sizing scalper.
- Project sudah punya decision-layer user-facing di `signals/signal_decision_layer.py` untuk membedakan raw ML signal dari final/actionable label, sejalan dengan catatan sebelumnya bahwa raw ML BUY/SELL tidak boleh langsung jadi action.

## Kesimpulan teknis

Rekomendasi Gemini **searah** dengan arah project saat ini, terutama pada tiga hal:

1. **Model tabular cepat lebih cocok sebagai baseline scalping** daripada deep learning berat.
2. **Orderbook/market microstructure wajib masuk decision process**, bukan hanya candle OHLCV.
3. **Fee dan spread harus menjadi hard gate**, karena profit scalping kecil mudah habis oleh biaya transaksi.

Namun, project saat ini belum perlu langsung melompat ke LSTM/RL. Jalur paling realistis adalah memperkuat pipeline tabular existing terlebih dahulu.

## Rangkuman perubahan yang diperlukan / direkomendasikan

### Prioritas 1 — Validasi & dokumentasi fitur existing

Tidak harus menulis ulang model. Pertama, verifikasi bahwa fitur berikut benar-benar masuk ke path final decision/autotrade:

- orderbook pressure / bid-ask imbalance,
- volume ratio/spike,
- fee-aware risk-reward,
- liquidity/spread guard,
- position-aware decision layer.

Jika ada gap, tambahkan test terfokus sebelum ubah kode.

### Prioritas 2 — Tambah spread guard eksplisit

Gemini menekankan spread Indodax yang melebar. Repo sudah punya orderbook pressure dan fee-aware R/R, tetapi perlu audit apakah ada **spread percentage hard gate** eksplisit sebelum entry.

Rekomendasi rule:

- hitung `best_bid`, `best_ask`, `mid_price`, `spread_pct`,
- blokir scalping jika `spread_pct` melebihi target profit minimum atau threshold config,
- log alasan sebagai `SPREAD_TOO_WIDE`,
- tampilkan di dashboard/status agar user tahu pair ditolak karena spread, bukan ML lemah.

### Prioritas 3 — Kandidat upgrade model: LightGBM sebagai eksperimen, bukan pengganti langsung

Karena V2/V4 sudah memakai RandomForest + GradientBoosting, LightGBM dapat diuji sebagai eksperimen offline:

- jangan mengganti model live langsung,
- buat trainer/evaluator terpisah,
- bandingkan win-rate, precision GOOD_BUY, profit factor, expectancy, dan latency inferensi,
- gunakan data yang sama dengan V2/V4 agar perbandingan adil,
- hanya promote jika metrik trading membaik, bukan hanya accuracy.

XGBoost juga mungkin, tetapi LightGBM lebih menarik untuk training cepat dan dataset tabular besar.

### Prioritas 4 — Jangan prioritaskan LSTM/GRU dulu

LSTM/GRU baru layak setelah dataset historis besar, bersih, dan memiliki label outcome yang stabil. Risiko saat ini:

- overfitting,
- training/inferensi lebih berat,
- maintenance lebih kompleks,
- belum tentu lebih baik dari ensemble tabular untuk Indodax scalping.

### Prioritas 5 — RL/PPO hanya long-term research

RL/PPO sebaiknya dicatat sebagai riset jangka panjang saja. Syarat minimum sebelum dicoba:

- simulator Indodax realistis,
- fee maker/taker,
- spread dan slippage,
- partial fills/orderbook depth,
- latency/order cancellation,
- reward berbasis net PnL dan drawdown.

Tanpa environment realistis, PPO cenderung menghasilkan strategi yang bagus di simulasi tetapi gagal live.

## Dampak safety

- Tidak ada perubahan kode dilakukan oleh catatan ini.
- Default safety tetap: AutoTrade/SmartHunter/AutoHunter DRY RUN kecuali user eksplisit mengubahnya.
- Untuk scalper real-trading lane, rekomendasi spread/fee guard justru mengurangi risiko entry buruk.

## Next step yang disarankan

1. Audit apakah `analyze_market_intelligence()` sudah menghitung spread best bid/ask; jika belum, tambahkan sebagai test + implementation.
2. Tambahkan `SPREAD_TOO_WIDE` sebagai block reason agar muncul di status diagnostic.
3. Buat eksperimen offline LightGBM untuk membandingkan dengan V2/V4, tanpa mengubah model live.
4. Setelah data cukup, baru evaluasi apakah sequence model atau RL layak masuk backlog riset.
