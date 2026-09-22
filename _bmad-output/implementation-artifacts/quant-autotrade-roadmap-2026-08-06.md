# Quant AutoTrade Hardening Roadmap — 2026-08-06

Tujuan: meningkatkan kualitas dry-run/live candidate tanpa mengganti seluruh logic sinyal sekaligus.

## Implemented first slice

- Entry-quality filter untuk BUY/STRONG_BUY:
  - trend 5m/15m/1h/4h searah atau tidak;
  - volume spike;
  - orderbook imbalance;
  - spread/liquidity abnormal.
- Cost-aware gate:
  - estimasi biaya round-trip = fee buy/sell + slippage + spread;
  - entry diblokir jika expected TP1 edge tidak cukup melewati cost floor;
  - R/R after fees rendah sekarang bisa memblokir dry-run juga.
- Offline quant evaluator:
  - walk-forward replay metrics;
  - model-promotion pass/fail gate;
  - meta-label `prob_good_trade` by pair/recommendation/confidence bucket;
  - probability calibration bins, ECE, dan Brier score.

## Next implementation order

1. Walk-forward replay + model promotion gate
   - sudah ada evaluator CLI awal: `scripts/evaluate_autotrade_quant_gates.py`;
   - berikutnya hubungkan evaluator ini ke flow `/retrain` agar model baru tidak otomatis promote;
   - tambahkan fee/slippage/spread yang lebih rinci per trade bila data orderbook historis tersedia.

2. Meta-labeling `prob_good_trade`
   - sudah ada baseline smoothed group probability dari closed trade outcomes;
   - sudah terintegrasi sebagai runtime gate dengan sample-size guard;
   - berikutnya ganti baseline group probability menjadi model meta-label khusus bila sample cukup.

3. Probability calibration
   - sudah ada calibration report awal: confidence bins, ECE, dan Brier score;
   - sudah terintegrasi sebagai runtime calibration gate dengan sample-size guard;
   - berikutnya kalibrasi confidence model dengan sigmoid/isotonic bila sample cukup.

4. Regime-aware sizing dan adaptive exit
   - runtime sudah punya trend/range/high-vol size multiplier;
   - trailing stop sekarang adaptive terhadap volatilitas historis;
   - berikutnya ATR/volatility-based stop distance yang lebih formal;
   - block atau reduce size saat regime tidak cocok dengan signal.

5. Advanced exploration
   - fitur multi-timeframe/orderbook sederhana sudah runtime;
   - transformer/orderbook sequence feature explorer sudah offline;
   - model sequence hanya boleh masuk runtime setelah replay + calibration sehat.
