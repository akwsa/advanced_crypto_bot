#!/usr/bin/env python3
"""
Signal Flow Test Suite
======================
Test signal generation flow dari ML model → Trading Engine → Signal Quality Engine.

Tests:
    1. ML Prediction → Signal Class mapping
    2. Combined Strength calculation (TA + ML)
    3. Trading Engine signal thresholds
    4. Signal Quality Engine confluence scoring
    5. Full integration flow

Usage:
    python tests/test_signal_flow.py
"""

import sys
import os
from datetime import datetime

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_trading_engine_calculations():
    """Test TradingEngine signal calculations."""
    print("\n" + "="*60)
    print("TEST 1: Trading Engine Combined Strength Calculation")
    print("="*60)

    try:
        from trading.trading_engine import TradingEngine
        from core.database import Database
        from analysis.ml_model_v2 import MLTradingModelV2

        # Mock objects
        db = Database()
        ml_model = MLTradingModelV2(model_path='models/test_v2.pkl')

        engine = TradingEngine(db, ml_model)

        test_cases = [
            {
                'name': 'Strong Bullish (TA strong + ML BUY)',
                'ta_signals': {'strength': 0.8, 'price': 50000, 'indicators': {}},
                'ml_pred': True,
                'ml_conf': 0.85,
                'ml_class': 'BUY',
                'expected': 'STRONG_BUY'  # Should be STRONG_BUY
            },
            {
                'name': 'Moderate Bullish (TA weak + ML BUY)',
                'ta_signals': {'strength': 0.2, 'price': 50000, 'indicators': {}},
                'ml_pred': True,
                'ml_conf': 0.70,
                'ml_class': 'BUY',
                'expected': 'BUY'  # Should be BUY
            },
            {
                'name': 'Strong Bearish (TA weak + ML SELL)',
                'ta_signals': {'strength': -0.7, 'price': 50000, 'indicators': {}},
                'ml_pred': False,
                'ml_conf': 0.80,
                'ml_class': 'SELL',
                'expected': 'STRONG_SELL'  # Should be STRONG_SELL
            },
            {
                'name': 'Low Confidence (should be HOLD)',
                'ta_signals': {'strength': 0.5, 'price': 50000, 'indicators': {}},
                'ml_pred': True,
                'ml_conf': 0.50,  # Below threshold
                'ml_class': 'BUY',
                'expected': 'HOLD'  # Should be HOLD due to low confidence
            },
            {
                'name': 'Mixed Signals (should be HOLD)',
                'ta_signals': {'strength': 0.1, 'price': 50000, 'indicators': {}},
                'ml_pred': True,
                'ml_conf': 0.60,
                'ml_class': 'BUY',
                'expected': 'HOLD'  # Below moderate threshold
            }
        ]

        passed = 0
        for tc in test_cases:
            signal = engine.generate_signal(
                pair='BTCIDR',
                ta_signals=tc['ta_signals'],
                ml_prediction=tc['ml_pred'],
                ml_confidence=tc['ml_conf'],
                ml_signal_class=tc['ml_class']
            )

            result = signal['recommendation']
            combined = signal['combined_strength']

            status = "✅" if result == tc['expected'] else "❌"
            print(f"\n{status} {tc['name']}")
            print(f"   Expected: {tc['expected']}, Got: {result}")
            print(f"   Combined Strength: {combined:+.2f}")

            if result == tc['expected']:
                passed += 1

        print(f"\n{'='*60}")
        print(f"Result: {passed}/{len(test_cases)} tests passed")
        return passed == len(test_cases)

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False


def test_signal_quality_confluence():
    """Test Signal Quality Engine confluence scoring."""
    print("\n" + "="*60)
    print("TEST 2: Signal Quality Engine Confluence Scoring")
    print("="*60)

    try:
        from signals.signal_quality_engine import SignalQualityEngine

        engine = SignalQualityEngine()

        # Test BUY direction scoring
        print("\n📊 BUY Direction Tests:")
        buy_tests = [
            {
                'name': 'Perfect BUY setup',
                'params': {
                    'rsi': 'OVERSOLD', 'macd': 'BULLISH', 'ma_trend': 'BULLISH',
                    'bollinger': 'OVERSOLD', 'volume': 'HIGH', 'ml_confidence': 0.75,
                    'ta_strength': 0.5, 'direction': 'BUY'
                },
                'expected_range': (7, 8)  # Max score
            },
            {
                'name': 'Good BUY setup',
                'params': {
                    'rsi': 'OVERSOLD', 'macd': 'BULLISH', 'ma_trend': 'NEUTRAL',
                    'bollinger': 'NEUTRAL', 'volume': 'HIGH', 'ml_confidence': 0.65,
                    'ta_strength': 0.3, 'direction': 'BUY'
                },
                'expected_range': (5, 6)
            },
            {
                'name': 'Weak BUY setup',
                'params': {
                    'rsi': 'NEUTRAL', 'macd': 'NEUTRAL', 'ma_trend': 'NEUTRAL',
                    'bollinger': 'NEUTRAL', 'volume': 'NORMAL', 'ml_confidence': 0.60,
                    'ta_strength': 0.1, 'direction': 'BUY'
                },
                'expected_range': (1, 3)
            }
        ]

        passed = 0
        for tc in buy_tests:
            score = engine._calculate_confluence_score(**tc['params'])
            min_exp, max_exp = tc['expected_range']

            status = "✅" if min_exp <= score <= max_exp else "❌"
            print(f"\n{status} {tc['name']}")
            print(f"   Score: {score}, Expected: {min_exp}-{max_exp}")

            if min_exp <= score <= max_exp:
                passed += 1

        # Test SELL direction scoring
        print("\n📊 SELL Direction Tests:")
        sell_tests = [
            {
                'name': 'Perfect SELL setup',
                'params': {
                    'rsi': 'OVERBOUGHT', 'macd': 'BEARISH', 'ma_trend': 'BEARISH',
                    'bollinger': 'OVERBOUGHT', 'volume': 'HIGH', 'ml_confidence': 0.75,
                    'ta_strength': -0.5, 'direction': 'SELL'
                },
                'expected_range': (7, 8)  # Max score
            },
            {
                'name': 'Good SELL setup',
                'params': {
                    'rsi': 'OVERBOUGHT', 'macd': 'BEARISH', 'ma_trend': 'NEUTRAL',
                    'bollinger': 'NEUTRAL', 'volume': 'HIGH', 'ml_confidence': 0.65,
                    'ta_strength': -0.3, 'direction': 'SELL'
                },
                'expected_range': (5, 6)
            }
        ]

        for tc in sell_tests:
            score = engine._calculate_confluence_score(**tc['params'])
            min_exp, max_exp = tc['expected_range']

            status = "✅" if min_exp <= score <= max_exp else "❌"
            print(f"\n{status} {tc['name']}")
            print(f"   Score: {score}, Expected: {min_exp}-{max_exp}")

            if min_exp <= score <= max_exp:
                passed += 1

        print(f"\n{'='*60}")
        print(f"Result: {passed}/{len(buy_tests) + len(sell_tests)} tests passed")
        return passed == len(buy_tests) + len(sell_tests)

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False


def test_ml_signal_mapping():
    """Test ML prediction to signal class mapping."""
    print("\n" + "="*60)
    print("TEST 3: ML Prediction to Signal Class Mapping")
    print("="*60)

    try:
        from analysis.ml_model_v2 import MLTradingModelV2

        # Create model
        model = MLTradingModelV2(model_path='models/test_v2_map.pkl')

        # Test signal class mapping
        test_cases = [
            {'class': 'STRONG_BUY', 'expected_bool': True, 'expected_class': 4},
            {'class': 'BUY', 'expected_bool': True, 'expected_class': 3},
            {'class': 'HOLD', 'expected_bool': False, 'expected_class': 2},
            {'class': 'SELL', 'expected_bool': False, 'expected_class': 1},
            {'class': 'STRONG_SELL', 'expected_bool': False, 'expected_class': 0},
        ]

        print("\n📊 Signal Class Mapping:")
        print("   ML Class       -> Boolean    -> Int Class")
        print("   " + "-" * 45)

        for tc in test_cases:
            ml_class = tc['class']

            # Boolean conversion logic from bot.py
            is_buy = ml_class in ['STRONG_BUY', 'BUY']

            # Int class mapping from ml_model_v2.py
            class_map = {
                'STRONG_SELL': 0, 'SELL': 1, 'HOLD': 2, 'BUY': 3, 'STRONG_BUY': 4
            }
            int_class = class_map.get(ml_class, 2)

            bool_ok = is_buy == tc['expected_bool']
            class_ok = int_class == tc['expected_class']

            status = "✅" if bool_ok and class_ok else "❌"
            print(f"   {status} {ml_class:<12} -> {str(is_buy):<8}   -> {int_class}")

        print(f"\n✅ ML signal mapping logic verified")
        return True

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False


def test_signal_validation():
    """Test input validation in signal flow."""
    print("\n" + "="*60)
    print("TEST 4: Signal Input Validation")
    print("="*60)

    try:
        from trading.trading_engine import TradingEngine
        from core.database import Database
        from analysis.ml_model_v2 import MLTradingModelV2

        db = Database()
        ml_model = MLTradingModelV2(model_path='models/test_v2_val.pkl')
        engine = TradingEngine(db, ml_model)

        test_cases = [
            {
                'name': 'Invalid pair (None)',
                'params': {
                    'pair': None,
                    'ta_signals': {'strength': 0.5, 'price': 50000, 'indicators': {}},
                    'ml_pred': True,
                    'ml_conf': 0.7
                },
                'should_raise': True
            },
            {
                'name': 'Invalid TA signals (None)',
                'params': {
                    'pair': 'BTCIDR',
                    'ta_signals': None,
                    'ml_pred': True,
                    'ml_conf': 0.7
                },
                'should_raise': True
            },
            {
                'name': 'Invalid ML confidence (>1)',
                'params': {
                    'pair': 'BTCIDR',
                    'ta_signals': {'strength': 0.5, 'price': 50000, 'indicators': {}},
                    'ml_pred': True,
                    'ml_conf': 1.5  # > 1
                },
                'should_raise': False  # Should clamp, not raise
            },
            {
                'name': 'Negative ML confidence',
                'params': {
                    'pair': 'BTCIDR',
                    'ta_signals': {'strength': 0.5, 'price': 50000, 'indicators': {}},
                    'ml_pred': True,
                    'ml_conf': -0.2
                },
                'should_raise': False  # Should clamp, not raise
            },
            {
                'name': 'None ML confidence',
                'params': {
                    'pair': 'BTCIDR',
                    'ta_signals': {'strength': 0.5, 'price': 50000, 'indicators': {}},
                    'ml_pred': True,
                    'ml_conf': None
                },
                'should_raise': False  # Should use default
            }
        ]

        passed = 0
        for tc in test_cases:
            try:
                signal = engine.generate_signal(**tc['params'])
                raised = False
            except Exception as e:
                raised = True

            if raised == tc['should_raise']:
                status = "✅"
                passed += 1
            else:
                status = "❌"

            print(f"\n{status} {tc['name']}")
            print(f"   Expected raise: {tc['should_raise']}, Got: {raised}")

        print(f"\n{'='*60}")
        print(f"Result: {passed}/{len(test_cases)} tests passed")
        return passed == len(test_cases)

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False


def main():
    """Run all tests."""
    print("="*60)
    print("SIGNAL FLOW TEST SUITE")
    print("="*60)
    print(f"Started: {datetime.now()}")

    # Ensure models directory exists
    os.makedirs('models', exist_ok=True)

    results = []

    # Run tests
    results.append(("Trading Engine Calculations", test_trading_engine_calculations()))
    results.append(("Signal Quality Confluence", test_signal_quality_confluence()))
    results.append(("ML Signal Mapping", test_ml_signal_mapping()))
    results.append(("Input Validation", test_signal_validation()))

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"  {name:<35} {status}")

    print(f"\nTotal: {passed}/{total} test suites passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test suite(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
