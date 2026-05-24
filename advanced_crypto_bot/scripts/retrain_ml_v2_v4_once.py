#!/usr/bin/env python3
"""One-shot ML V2/V4 retrain with model backups and progress logging.

Safe defaults:
- Does not start the trading bot.
- Does not enable real trading.
- Backs up existing model artifacts before training.
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.ml_model_v2 import MLTradingModelV2  # noqa: E402
from analysis.ml_model_v4 import MLTradingModelV4  # noqa: E402
from analysis.ml_signal_trainer import SignalOutcomeLabeler  # noqa: E402
from bot import AdvancedCryptoBot  # noqa: E402
from core.config import Config  # noqa: E402
from core.database import Database  # noqa: E402

LOG_DIR = ROOT / "logs"
BACKUP_DIR = ROOT / "models" / "backups"
RUN_DIR = ROOT / "logs" / "ml_retrain"


def setup_logging() -> Path:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    log_path = RUN_DIR / f"retrain_v2_v4_{datetime.now():%Y%m%d_%H%M%S}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler(sys.stdout)],
    )
    return log_path


def backup_models() -> dict[str, str]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backups: dict[str, str] = {}
    for name in ("trading_model_v2.pkl", "trading_model_v4.pkl"):
        src = ROOT / "models" / name
        if src.exists():
            dst = BACKUP_DIR / f"{src.stem}_before_retrain_{stamp}{src.suffix}"
            shutil.copy2(src, dst)
            backups[name] = str(dst.relative_to(ROOT))
            logging.info("backup %s -> %s", src.relative_to(ROOT), dst.relative_to(ROOT))
        else:
            logging.info("backup skipped, missing %s", src.relative_to(ROOT))
    return backups


def collect_v2_training_data(limit: int = 2000) -> tuple[pd.DataFrame, list[str]]:
    bot = AdvancedCryptoBot.__new__(AdvancedCryptoBot)
    bot.db = Database()
    logging.info("collecting normalized V2 training data: pairs=%s limit=%s", len(Config.WATCH_PAIRS), limit)
    frames, summary = AdvancedCryptoBot._collect_normalized_training_data(
        bot,
        pairs_to_check=Config.WATCH_PAIRS,
        limit=limit,
        min_candles=100,
        include_small_groups=False,
        include_zero_summary=False,
    )
    data = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    logging.info("collected V2 data: groups=%s candles=%s", len(frames), len(data))
    logging.info("V2 summary head: %s", summary[:10])
    return data, summary


def train_v2(data: pd.DataFrame) -> dict[str, object]:
    if len(data) < 200:
        raise RuntimeError(f"not enough V2 candles: {len(data)}")
    model = MLTradingModelV2()
    logging.info("training V2 start: candles=%s", len(data))
    started = time.time()
    ok = model.train(data)
    elapsed = time.time() - started
    metrics = {
        "ok": bool(ok),
        "elapsed_sec": round(elapsed, 2),
        "last_trained": str(getattr(model, "last_trained", None)),
        "accuracy": getattr(model, "last_accuracy", None),
        "precision": getattr(model, "last_precision", None),
        "recall": getattr(model, "last_recall", None),
        "f1": getattr(model, "last_f1", None),
        "win_rate": getattr(model, "last_win_rate", None),
        "profit_factor": getattr(model, "last_profit_factor", None),
        "undersample_info": getattr(model, "last_undersample_info", None),
    }
    logging.info("training V2 done: %s", json.dumps(metrics, default=str, ensure_ascii=False))
    return metrics


def train_v4(days_back: int = 30) -> dict[str, object]:
    labeler = SignalOutcomeLabeler()
    logging.info("labeling V4 outcomes start: days_back=%s", days_back)
    started = time.time()
    outcomes = labeler.label_all_signals(tp_pct=3, sl_pct=2, window=10, days_back=days_back)
    stats = labeler.get_label_stats(outcomes)
    logging.info("labeling V4 outcomes done: outcomes=%s stats=%s", len(outcomes), stats)
    if not outcomes:
        return {"ok": False, "reason": "no outcomes", "outcomes": 0, "stats": stats}

    model = MLTradingModelV4()
    logging.info("training V4 start: outcomes=%s", len(outcomes))
    ok = model.train_from_outcomes(outcomes)
    elapsed = time.time() - started
    status = model.get_status()
    result = {
        "ok": bool(ok),
        "elapsed_sec": round(elapsed, 2),
        "outcomes": len(outcomes),
        "stats": stats,
        "status": status,
    }
    logging.info("training V4 done: %s", json.dumps(result, default=str, ensure_ascii=False))
    return result


def main() -> int:
    log_path = setup_logging()
    logging.info("ML retrain started; log=%s", log_path)
    logging.info("project=%s", ROOT)
    backups = backup_models()
    result: dict[str, object] = {"log": str(log_path), "backups": backups}
    try:
        data, summary = collect_v2_training_data(limit=2000)
        result["v2_summary_count"] = len(summary)
        result["v2_candles"] = len(data)
        result["v2"] = train_v2(data)
        result["v4"] = train_v4(days_back=30)
        logging.info("ML retrain complete: %s", json.dumps(result, default=str, ensure_ascii=False))
        print("FINAL_RESULT", json.dumps(result, default=str, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        logging.exception("ML retrain failed: %s", exc)
        result["error"] = str(exc)
        print("FINAL_RESULT", json.dumps(result, default=str, ensure_ascii=False), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
