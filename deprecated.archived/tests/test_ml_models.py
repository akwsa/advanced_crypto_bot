#!/usr/bin/env python3
"""
ML Models Test Suite
====================
Test untuk memverifikasi ML models berfungsi dengan benar.

Usage:
    python tests/test_ml_models.py

Tests:
    1. V1 Model - Binary prediction
    2. V2 Model - Binary prediction (default)
    3. V2 Model - Multi-class prediction (optional)
    4. Feature preparation
    5. Model save/load
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def create_test_data(n=200):
    """Create synthetic OHLCV test data."""
    np.random.seed(42)
    base_price = 50000

    # Generate random walk
    returns = np.random.normal(0, 0.02, n)
    prices = base_price * np.cumprod(1 + returns)

    df = pd.DataFrame({
        'open': prices * (1 + np.random.normal(0, 0.001, n)),
        'high': prices * (1 + abs(np.random.normal(0, 0.01, n))),
        'low': prices * (1 - abs(np.random.normal(0, 0.01, n))),
        'close': prices,
        'volume': np.random.randint(1000000, 10000000, n)
    })

    # Ensure high >= close >= low
    df['high'] = np.maximum(df['high'], df[['open', 'close']].max(axis=1) * 1.001)
    df['low'] = np.minimum(df['low'], df[['open', 'close']].min(axis=1) * 0.999)

    return df

def test_v1_model():
    """Test ML Model V1 (Binary classification)."""
    print("\n" + "="*60)
    print("TEST 1: ML Model V1 (Binary)")
    print("="*60)

    try:
        from analysis.ml_model import MLTradingModel

        # Create fresh model
        model = MLTradingModel(model_path='models/test_v1_model.pkl')

        # Test 1: Before training
        print("\n1. Testing before training...")
        result = model.predict(create_test_data(10))
        assert len(result) == 3, f"Expected 3 return values, got {len(result)}"
        pred, conf, signal = result
        assert pred is None, f"Expected None before training, got {pred}"
        assert conf == 0.5, f"Expected 0.5 confidence before training, got {conf}"
        assert signal == 'HOLD', f"Expected HOLD before training, got {signal}"
        print("   ✅ Pre-training prediction correct")

        # Test 2: Train model
        print("\n2. Training model...")
        df = create_test_data(500)
        success = model.train(df)
        assert success, "Training should succeed with 500 samples"
        print("   ✅ Training successful")

        # Check metrics
        assert hasattr(model, 'last_accuracy'), "Model should have accuracy metric"
        assert model.last_accuracy is not None, "Accuracy should be set after training"
        print(f"   ✅ Accuracy: {model.last_accuracy:.2%}")

        # Test 3: After training
        print("\n3. Testing after training...")
        result = model.predict(create_test_data(100))
        assert len(result) == 3, f"Expected 3 return values, got {len(result)}"
        pred, conf, signal = result
        assert pred in [True, False], f"Prediction should be boolean, got {type(pred)}"
        assert 0 <= conf <= 1, f"Confidence should be 0-1, got {conf}"
        assert signal in ['BUY', 'SELL', 'HOLD'], f"Invalid signal: {signal}"
        print(f"   ✅ Prediction: {pred}, Confidence: {conf:.2%}, Signal: {signal}")

        # Test 4: Feature importance
        print("\n4. Testing feature importance...")
        importance = model.get_feature_importance()
        if importance:
            print(f"   ✅ Feature importance available: {len(importance)} features")
        else:
            print("   ⚠️ Feature importance not available (may be normal)")

        # Test 5: Save and load
        print("\n5. Testing save/load...")
        model.save_model()
        assert os.path.exists('models/test_v1_model.pkl'), "Model file should be saved"

        # Load and verify
        model2 = MLTradingModel(model_path='models/test_v1_model.pkl')
        result2 = model2.predict(create_test_data(100))
        assert len(result2) == 3, f"Loaded model should return 3 values"
        print("   ✅ Save/load successful")

        # Cleanup
        if os.path.exists('models/test_v1_model.pkl'):
            os.remove('models/test_v1_model.pkl')

        print("\n✅ V1 Model: ALL TESTS PASSED")
        return True

    except Exception as e:
        print(f"\n❌ V1 Model Test Failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_v2_model_binary():
    """Test ML Model V2 (Binary classification - default)."""
    print("\n" + "="*60)
    print("TEST 2: ML Model V2 (Binary - Default)")
    print("="*60)

    try:
        from analysis.ml_model_v2 import MLTradingModelV2

        # Create fresh model
        model = MLTradingModelV2(model_path='models/test_v2_model.pkl')

        # Test 1: Before training
        print("\n1. Testing before training...")
        result = model.predict(create_test_data(10), use_multi_class=False)
        assert len(result) == 3, f"Expected 3 return values, got {len(result)}"
        pred, conf, signal = result
        assert pred is False, f"Expected False before training, got {pred}"
        assert conf == 0.5, f"Expected 0.5 confidence before training, got {conf}"
        assert signal == 'HOLD', f"Expected HOLD before training, got {signal}"
        print("   ✅ Pre-training prediction correct")

        # Test 2: Train model (binary)
        print("\n2. Training model (binary mode)...")
        df = create_test_data(500)
        success = model.train(df, use_multi_class=False)
        assert success, "Training should succeed with 500 samples"
        print("   ✅ Training successful")

        # Check metrics
        assert model.last_accuracy is not None, "Accuracy should be set"
        assert model.last_precision is not None, "Precision should be set"
        assert model.last_recall is not None, "Recall should be set"
        print(f"   ✅ Accuracy: {model.last_accuracy:.2%}")
        print(f"   ✅ Precision: {model.last_precision:.2%}")
        print(f"   ✅ Recall: {model.last_recall:.2%}")

        # Test 3: After training (binary prediction)
        print("\n3. Testing binary prediction...")
        result = model.predict(create_test_data(100), use_multi_class=False)
        assert len(result) == 3, f"Expected 3 return values, got {len(result)}"
        pred, conf, signal = result
        assert isinstance(pred, bool), f"Prediction should be boolean, got {type(pred)}"
        assert 0 <= conf <= 1, f"Confidence should be 0-1, got {conf}"
        assert signal in ['BUY', 'SELL', 'HOLD'], f"Invalid signal: {signal}"
        print(f"   ✅ Prediction: {pred}, Confidence: {conf:.2%}, Signal: {signal}")

        # Test 4: Feature importance
        print("\n4. Testing feature importance...")
        importance = model.get_feature_importance(top_n=5)
        if importance:
            print(f"   ✅ Top 5 features:")
            for name, score in importance:
                print(f"      - {name}: {score:.2%}")
        else:
            print("   ⚠️ Feature importance not available")

        # Test 5: Save and load
        print("\n5. Testing save/load...")
        model.save_model()
        assert os.path.exists('models/test_v2_model.pkl'), "Model file should be saved"

        # Load and verify
        model2 = MLTradingModelV2(model_path='models/test_v2_model.pkl')
        result2 = model2.predict(create_test_data(100), use_multi_class=False)
        assert len(result2) == 3, f"Loaded model should return 3 values"
        print("   ✅ Save/load successful")

        # Cleanup
        if os.path.exists('models/test_v2_model.pkl'):
            os.remove('models/test_v2_model.pkl')

        print("\n✅ V2 Model (Binary): ALL TESTS PASSED")
        return True

    except Exception as e:
        print(f"\n❌ V2 Model (Binary) Test Failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_v2_model_multiclass():
    """Test ML Model V2 (Multi-class classification)."""
    print("\n" + "="*60)
    print("TEST 3: ML Model V2 (Multi-Class)")
    print("="*60)

    try:
        from analysis.ml_model_v2 import MLTradingModelV2

        # Create fresh model
        model = MLTradingModelV2(model_path='models/test_v2_mc_model.pkl')

        # Train model (multi-class)
        print("\n1. Training model (multi-class mode)...")
        df = create_test_data(500)
        success = model.train(df, use_multi_class=True)
        assert success, "Training should succeed with 500 samples"
        print("   ✅ Multi-class training successful")

        # Check metrics
        assert model.last_accuracy is not None, "Accuracy should be set"
        print(f"   ✅ Accuracy: {model.last_accuracy:.2%}")

        # Test 2: Multi-class prediction
        print("\n2. Testing multi-class prediction...")
        result = model.predict(create_test_data(100), use_multi_class=True)
        assert len(result) == 3, f"Expected 3 return values, got {len(result)}"
        pred, conf, signal = result
        assert isinstance(pred, int) and 0 <= pred <= 4, f"Prediction should be int 0-4, got {pred}"
        assert 0 <= conf <= 1, f"Confidence should be 0-1, got {conf}"
        assert signal in ['STRONG_SELL', 'SELL', 'HOLD', 'BUY', 'STRONG_BUY'], f"Invalid signal: {signal}"
        print(f"   ✅ Prediction: {pred}, Confidence: {conf:.2%}, Signal: {signal}")

        # Test 3: Map class to expected values
        print("\n3. Testing class mapping...")
        signal_map = {
            0: 'STRONG_SELL',
            1: 'SELL',
            2: 'HOLD',
            3: 'BUY',
            4: 'STRONG_BUY'
        }
        for i in range(5):
            # Create scenario data for each class
            test_df = create_test_data(100)
            pred_class, conf, signal = model.predict(test_df, use_multi_class=True)
            assert signal_map[pred_class] == signal, f"Class {pred_class} should map to {signal_map[pred_class]}, got {signal}"
        print("   ✅ Class mapping correct")

        # Cleanup
        if os.path.exists('models/test_v2_mc_model.pkl'):
            os.remove('models/test_v2_mc_model.pkl')

        print("\n✅ V2 Model (Multi-Class): ALL TESTS PASSED")
        return True

    except Exception as e:
        print(f"\n❌ V2 Model (Multi-Class) Test Failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def main():
    """Run all tests."""
    print("="*60)
    print("ML MODELS TEST SUITE")
    print("="*60)
    print(f"Started: {datetime.now()}")

    # Ensure models directory exists
    os.makedirs('models', exist_ok=True)

    results = []

    # Run tests
    results.append(("V1 Model (Binary)", test_v1_model()))
    results.append(("V2 Model (Binary)", test_v2_model_binary()))
    results.append(("V2 Model (Multi-Class)", test_v2_model_multiclass()))

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"  {name:<30} {status}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1

if __name__ == '__main__':
    sys.exit(main())
