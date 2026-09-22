"""Regression test untuk integrity guard di MLTradingModelV2.load_model().

Audit 2026-06-09: model V2 production memiliki mismatch internal — scaler
dilatih dengan 47 fitur tapi `_trained_feature_names` berisi 58 nama. Akibatnya
SEMUA call predict() gagal di scaler.transform() dan silent fallback ke
(False, 0.5, 'HOLD'). Test ini memastikan load_model() men-detect mismatch dan
men-set `_is_fitted=False` sehingga downstream pipeline bisa fallback eksplisit.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analysis.ml_model_v2 import MLTradingModelV2  # noqa: E402


def _build_dummy_pickle(scaler_features: int, name_count: int, path: str) -> None:
    """Tulis pickle V2 dengan jumlah fitur scaler dan feature_names yang ditentukan."""
    rng = np.random.RandomState(42)
    X_scaler = rng.rand(50, scaler_features)
    scaler = StandardScaler().fit(X_scaler)

    X_model = rng.rand(50, scaler_features)
    y_model = rng.randint(0, 2, 50)
    rf = RandomForestClassifier(n_estimators=3, random_state=42).fit(X_model, y_model)
    gb = GradientBoostingClassifier(n_estimators=3, random_state=42).fit(X_model, y_model)

    feature_names = [f"f{i}" for i in range(name_count)]

    joblib.dump(
        {
            "version": "2.0",
            "model": {"rf": rf, "gb": gb},
            "scaler": scaler,
            "feature_names": feature_names,
            "last_trained": datetime.now(),
        },
        path,
    )


class MLV2IntegrityGuardTests(unittest.TestCase):
    def test_load_model_marks_unfitted_when_scaler_features_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trading_model_v2.pkl")
            _build_dummy_pickle(scaler_features=47, name_count=58, path=path)

            m = MLTradingModelV2()
            m.model_path = path
            ok = m.load_model()

            self.assertTrue(ok, "load_model harus tetap return True untuk fail-safe")
            self.assertFalse(
                m._is_fitted,
                "Mismatch scaler vs feature_names harus men-flag _is_fitted=False "
                "agar downstream fallback eksplisit ketimbang silent HOLD.",
            )

    def test_load_model_marks_fitted_when_features_consistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "trading_model_v2.pkl")
            _build_dummy_pickle(scaler_features=47, name_count=47, path=path)

            m = MLTradingModelV2()
            m.model_path = path
            ok = m.load_model()

            self.assertTrue(ok)
            self.assertTrue(
                m._is_fitted,
                "Model konsisten harus tetap fitted, guard tidak boleh false-positive.",
            )


if __name__ == "__main__":
    unittest.main()
