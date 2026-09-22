
"""Regression tests for Bayesian Kelly sizing integration.

1. risk_manager.bayesian_kelly_position_size output contract.
2. The Kelly override in the autotrade path applies to BOTH DRY RUN and REAL
   trading (it sits before the is_dry_run split).
3. Engine warmup from DB trade history so a fresh process does not start with
   an empty slate (which forces the prior_only fallback).
"""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch


class TestKellySizingContract(unittest.TestCase):
    """The method must always return (value, amount, meta) with stable keys."""

    def _rm(self):
        from autotrade.risk_manager import RiskManager
        return RiskManager(SimpleNamespace())

    def test_meta_keys_always_present(self):
        rm = self._rm()
        value, amount, meta = rm.bayesian_kelly_position_size(
            pair="btcidr",
            balance=10_000_000,
            entry_price=1_500_000_000,
            ml_confidence=0.8,
            volatility_pct=1.5,
            current_drawdown_pct=0.0,
            kelly_engine=None,
        )
        self.assertIsInstance(value, float)
        self.assertIsInstance(amount, float)
        for key in ("method", "kelly_fraction", "position_value",
                    "position_amount", "clamped", "reason"):
            self.assertIn(key, meta)

    def test_invalid_input_returns_zero(self):
        rm = self._rm()
        for balance, price in ((0, 100.0), (100.0, 0), (-5, 100.0)):
            value, amount, meta = rm.bayesian_kelly_position_size(
                pair="btcidr", balance=balance, entry_price=price,
                kelly_engine=None,
            )
            self.assertEqual(value, 0.0)
            self.assertEqual(amount, 0.0)
            self.assertEqual(meta["method"], "disabled")

    def test_safety_clamps_apply(self):
        """Position must be clamped to [min_order, max_fraction * balance]."""
        from quant.bayesian_kelly import BayesianKellyEngine, KellyResult
        engine = BayesianKellyEngine()

        # Patch calculate_position_size to return an oversized value so the
        # clamp path is exercised deterministically.
        def fake_calc(**kwargs):
            return KellyResult(
                pair=kwargs["pair"], position_value=kwargs["balance"] * 2.0,
                position_amount=(kwargs["balance"] * 2.0) / kwargs["entry_price"],
                kelly_fraction=0.5, raw_kelly_pct=0.5, bayesian_win_rate=0.6,
                win_loss_ratio=1.5, confidence_factor=1.0,
                volatility_factor=1.0, drawdown_factor=1.0,
                total_trades=10, effective_trades=10.0, method="bayesian_kelly",
            )
        engine.calculate_position_size = fake_calc

        rm = self._rm()
        value, amount, meta = rm.bayesian_kelly_position_size(
            pair="btcidr", balance=10_000_000, entry_price=1_000_000_000,
            kelly_engine=engine,
        )
        self.assertLessEqual(value, 10_000_000 * 0.25)
        self.assertTrue(meta["clamped"])
        self.assertEqual(meta["reason"], "safety_clamp_applied")


class TestKellyEngineWarmup(unittest.TestCase):
    """load_from_trade_history must replay closed trades into the engine."""

    def test_warmup_populates_history(self):
        from quant.bayesian_kelly import BayesianKellyEngine, MIN_TRADES_FOR_KELLY
        engine = BayesianKellyEngine()
        rows = [
            {"pair": "btcidr", "profit_loss_pct": 3.0},
            {"pair": "btcidr", "profit_loss_pct": -1.5},
            {"pair": "ethidr", "profit_loss_pct": 2.2},
        ]
        replayed = engine.load_from_trade_history(rows)
        self.assertEqual(replayed, 3)
        stats = engine.get_pair_stats("btcidr")
        self.assertEqual(stats["total_trades"], 2)

    def test_warmup_crosses_min_trades_threshold(self):
        """After warmup the pair must be usable by Kelly (>= MIN_TRADES)."""
        from quant.bayesian_kelly import BayesianKellyEngine, MIN_TRADES_FOR_KELLY
        engine = BayesianKellyEngine()
        rows = [
            {"pair": "btcidr", "profit_loss_pct": 2.0}
            for _ in range(MIN_TRADES_FOR_KELLY + 2)
        ]
        engine.load_from_trade_history(rows)
        result = engine.calculate_position_size(
            pair="btcidr", balance=10_000_000, entry_price=1_000_000_000,
            ml_confidence=0.7, volatility_pct=2.0,
        )
        self.assertEqual(result.method, "bayesian_kelly")

    def test_warmup_skips_rows_without_pnl(self):
        from quant.bayesian_kelly import BayesianKellyEngine
        engine = BayesianKellyEngine()
        rows = [
            {"pair": "btcidr"},                       # no pnl
            {"pair": None, "profit_loss_pct": 1.0},   # no pair
            {"pair": "ethidr", "profit_loss_pct": None},  # pnl None
            {"pair": "ethidr", "profit_loss_pct": "n/a"},  # pnl invalid
        ]
        self.assertEqual(engine.load_from_trade_history(rows), 0)

    def test_warmup_is_read_only_for_db_rows(self):
        """sqlite3.Row-like objects (missing keys) must not raise."""
        from quant.bayesian_kelly import BayesianKellyEngine
        engine = BayesianKellyEngine()

        class Row(dict):
            def get(self, key, default=None):
                return self[key] if key in self else default

        rows = [Row(pair="btcidr", profit_loss_pct=1.5)]
        self.assertEqual(engine.load_from_trade_history(rows), 1)


class TestRuntimeWarmupWiring(unittest.TestCase):
    """_get_quant_kelly must warm the engine from bot.db on first use."""

    def test_warmup_called_on_engine_init(self):
        import autotrade.runtime as rt
        bot = SimpleNamespace(
            db=SimpleNamespace(
                get_trade_history=Mock(return_value=[
                    {"pair": "btcidr", "profit_loss_pct": 2.0},
                ]),
            ),
            subscribers={123: ["btcidr"]},
        )
        with patch.object(rt, "_warmup_kelly_from_db") as warm:
            engine = rt._get_quant_kelly(bot)
        self.assertIsNotNone(engine)
        warm.assert_called_once()
        bot._quant_kelly_engine = None  # cleanup

    def test_warmup_replays_history_into_engine(self):
        import autotrade.runtime as rt
        from quant.bayesian_kelly import BayesianKellyEngine
        engine = BayesianKellyEngine()
        bot = SimpleNamespace(
            db=SimpleNamespace(
                get_trade_history=Mock(return_value=[
                    {"pair": "btcidr", "profit_loss_pct": 2.0},
                    {"pair": "btcidr", "profit_loss_pct": 1.0},
                ]),
            ),
            subscribers={123: ["btcidr"]},
        )
        rt._warmup_kelly_from_db(bot, engine)
        stats = engine.get_pair_stats("btcidr")
        self.assertEqual(stats["total_trades"], 2)

    def test_warmup_tolerates_missing_db(self):
        import autotrade.runtime as rt
        from quant.bayesian_kelly import BayesianKellyEngine
        # bot with no db attribute at all
        bot = SimpleNamespace(subscribers={123: ["btcidr"]})
        # must not raise
        rt._warmup_kelly_from_db(bot, BayesianKellyEngine())


class TestKellyOverrideSourceOrder(unittest.TestCase):
    """Kelly override must run before the final dry-run execution split."""

    def test_override_precedes_final_dry_run_execution_branch(self):
        '''Kelly override must run before the EXECUTION split.

        There is an earlier is_dry_run block that swaps in the DRY RUN
        nominal size. Do not assert against that nominal-sizing branch; the
        property that matters is that Kelly runs before the final dry-run
        branch that fills or registers the order, so it can adjust size for
        real trades too.
        '''
        import ast
        src = open('''autotrade/runtime.py''').read()
        tree = ast.parse(src)
        fn = next(n for n in tree.body
                  if getattr(n, '''name''', None) == '''_check_trading_opportunity_locked''')
        kelly_line = None
        nominal_branch = None
        exec_branch = None
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and getattr(node.func, '''attr''', None) == '''bayesian_kelly_position_size''':
                kelly_line = node.lineno
            if isinstance(node, ast.If) and ast.unparse(node.test) == '''is_dry_run''':
                body_src = ast.unparse(node)
                if '''_calculate_dry_run_total_from_price''' in body_src:
                    nominal_branch = node.lineno
                if '''simulated_order_id''' in body_src and (
                    '''add_trade''' in body_src or '''create_atomic_dryrun_fill''' in body_src
                ):
                    exec_branch = node.lineno
        self.assertIsNotNone(kelly_line)
        self.assertIsNotNone(nominal_branch)
        self.assertIsNotNone(exec_branch)
        self.assertLess(nominal_branch, exec_branch)
        self.assertLess(kelly_line, exec_branch,
                        '''Kelly override must run before the final dry-run execution split''')
if __name__ == "__main__":
    unittest.main()
