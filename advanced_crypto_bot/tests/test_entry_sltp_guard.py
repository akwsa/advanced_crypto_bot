"""Regression: hasil ``calculate_stop_loss_take_profit`` wajib di-guard sebelum
dipakai, karena helper itu mengembalikan ``None`` pada input invalid.

BUG-3 (2026-09-23): ``_check_trading_opportunity_locked`` langsung mengambil
``tp_data["stop_loss"]`` / ``take_profit_1`` / ``take_profit_2`` tanpa validasi.
``autotrade/trading_engine.py::calculate_stop_loss_take_profit`` mengembalikan
``{'stop_loss': None, ...}`` ketika:
  - entry_price bukan angka atau <= 0
  - trade_type tidak dikenali
  - exception di blok kalkulasi

Tanpa guard, baris penyesuaian S/R (``stop_loss < nearest_support``) melempar
``TypeError`` -- ``None`` vs ``float`` tidak bisa dibandingkan di Python 3.
Crash terjadi SEBELUM order dikirim, jadi tidak menciptakan posisi tanpa stop,
tapi intent berakhir ERROR_RETRYABLE tanpa block reason yang terbaca, sehingga
diagnosis "kenapa tidak ada trade" jadi sulit.

Test ini bersifat source-level (AST) karena bug ada di cabang input-invalid
yang tidak dijangkau test fungsional normal.
"""
import ast
import unittest

SRC_PATH = "autotrade/runtime.py"
PRICE_MONITOR_PATH = "autotrade/price_monitor.py"
FN_NAME = "_check_trading_opportunity_locked"


def _load_fn():
    src = open(SRC_PATH, encoding="utf-8").read()
    tree = ast.parse(src)
    fn = next(
        n for n in tree.body
        if getattr(n, "name", None) == FN_NAME
    )
    return src, fn


class TestEntrySlTpGuard(unittest.TestCase):

    def _entry_level_lines(self, fn):
        """Baris-baris di area kalkulasi SL/TP awal (sebelum penyesuaian S/R)."""
        lines = []
        for node in ast.walk(fn):
            if isinstance(node, ast.If) and ast.unparse(node.test).startswith("not tp_data"):
                lines.append(node)
        return lines

    def test_guard_exists_after_sltp_calculation(self):
        """Harus ada guard None/invalid tepat setelah calculate_stop_loss_take_profit."""
        src, fn = _load_fn()
        fn_src = ast.unparse(fn)

        # ast.unparse normalizes string literals to single quotes.
        self.assertTrue(
            ("calculate_stop_loss_take_profit(current_price, 'BUY'" in fn_src)
            or ('calculate_stop_loss_take_profit(current_price, "BUY"' in fn_src),
            "entry SL/TP calculation call not found")
        self.assertIn("ENTRY_LEVELS", fn_src,
                      "missing ENTRY_LEVELS block reason for invalid SL/TP")
        # ast.unparse re-quotes to single quotes; match either form.
        self.assertTrue(
            ("tp_data.get('stop_loss') is None" in fn_src)
            or ('tp_data.get("stop_loss") is None' in fn_src),
            "guard must explicitly check stop_loss is None")
        # ast.unparse may wrap long conditions in parens; verify each level is
        # actually present rather than relying on one contiguous substring.
        for level in ("stop_loss", "take_profit_1", "take_profit_2"):
            self.assertIn(f"tp_data.get('{level}') is None", fn_src,
                          f"guard must explicitly check {level} for None")

    def test_guard_precedes_sltp_consumption(self):
        """Guard harus muncul SEBELUM stop_loss/tp di-assign dari tp_data."""
        src, fn = _load_fn()

        calc_lines = [n.lineno for n in ast.walk(fn)
                      if isinstance(n, ast.Call)
                      and getattr(n.func, "attr", None) == "calculate_stop_loss_take_profit"]
        guard_lines = [n.lineno for n in ast.walk(fn)
                       if isinstance(n, ast.If)
                       and "tp_data.get" in ast.unparse(n.test)]
        # ``stop_loss = tp_data["stop_loss"]`` -- the target is a plain Name,
        # the subscript is on the value side.
        consume_lines = [n.lineno for n in ast.walk(fn)
                         if isinstance(n, ast.Assign)
                         and any(isinstance(t, ast.Name) and t.id == "stop_loss"
                                 for t in n.targets)
                         and "tp_data" in ast.unparse(n.value)]

        self.assertTrue(calc_lines, "SL/TP calculation call missing")
        self.assertTrue(guard_lines, "None guard missing")
        self.assertTrue(consume_lines, "stop_loss assignment missing")

        self.assertLess(min(calc_lines), min(guard_lines),
                        "guard must come AFTER the calculation")
        self.assertLess(min(guard_lines), min(consume_lines),
                        "guard must come BEFORE consuming stop_loss from tp_data")

    def test_guard_records_block_reason_and_returns(self):
        """Guard harus blok entry (return) + catat alasan, bukan lanjut."""
        src, fn = _load_fn()
        guards = [n for n in ast.walk(fn)
                  if isinstance(n, ast.If)
                  and "tp_data.get" in ast.unparse(n.test)]
        self.assertTrue(guards, "no tp_data None guard found")

        guard = guards[0]
        body_src = ast.unparse(ast.Module(body=guard.body, type_ignores=[]))
        self.assertIn("_remember_autotrade_block_reason", body_src,
                      "guard must record a block reason")
        self.assertIn("return", body_src,
                      "guard must return (block the entry)")
        # Guard must not set stop_loss/take_profit inside itself
        self.assertNotIn("stop_loss =", body_src,
                         "guard body must not assign stop_loss")

    def test_guard_covers_all_three_levels(self):
        """Guard harus cek ketiga level: stop_loss, take_profit_1, take_profit_2."""
        src, fn = _load_fn()
        guards = [n for n in ast.walk(fn)
                  if isinstance(n, ast.If)
                  and "tp_data.get" in ast.unparse(n.test)]
        self.assertTrue(guards)
        test_src = ast.unparse(guards[0].test)
        for level in ("stop_loss", "take_profit_1", "take_profit_2"):
            self.assertIn(level, test_src,
                          f"guard must check {level} for None")


class TestPriceMonitorNoDeadBranch(unittest.TestCase):
    """BUG-4: elif yang sama persis dengan `if` di atasnya tidak boleh ada lagi."""

    @staticmethod
    def _check_price_levels_fn():
        src = open(PRICE_MONITOR_PATH, encoding="utf-8").read()
        tree = ast.parse(src)
        # check_price_levels is a method, not a top-level function.
        for cls in tree.body:
            if isinstance(cls, ast.ClassDef):
                for item in cls.body:
                    if getattr(item, "name", None) == "check_price_levels":
                        return src, item
        raise AssertionError("check_price_levels method not found")

    def test_no_duplicate_stop_loss_condition(self):
        src, fn = self._check_price_levels_fn()

        # Collect every if/elif condition in the hit_type decision chain.
        conds = []
        for node in ast.walk(fn):
            if isinstance(node, ast.If):
                test = ast.unparse(node.test)
                if "hit_type" in test and "stop_loss" in test:
                    conds.append(test)

        # There must be exactly one STOP_LOSS condition (the S/R-aware one),
        # not a duplicated unreachable elif.
        sl_conds = [c for c in conds
                    if "current_price <= level['stop_loss']" in c
                    or 'current_price <= level["stop_loss"]' in c]
        self.assertEqual(len(sl_conds), 1,
                         f"expected exactly 1 STOP_LOSS condition, got {len(sl_conds)}: {sl_conds}")

    def test_exit_chain_still_complete(self):
        """Hapus dead branch tidak boleh memutus rantai exit."""
        src = open(PRICE_MONITOR_PATH, encoding="utf-8").read()
        fn_src = src  # full source; check the decision chain by hand-mapping

        # Trailing stop -> SL -> partial TP1 -> partial TP2 (TAKE_PROFIT)
        for marker in ("hit_type = 'TRAILING_STOP'",
                       "hit_type = 'STOP_LOSS'",
                       "hit_type = 'PARTIAL_TP_1'",
                       "hit_type = 'TAKE_PROFIT'",
                       "hit_type = \"TIME_EXIT\"",
                       "INDEPENDENT TIME_EXIT"):
            self.assertIn(marker, fn_src,
                          f"exit chain broken: {marker} missing")

    def test_sr_hold_and_volume_confirmation_preserved(self):
        """Mekanisme perlindungan yang ada tidak boleh hilang."""
        src = open(PRICE_MONITOR_PATH, encoding="utf-8").read()
        for marker in ("SR-HOLD",          # S/R-aware hold (max 3x)
                       "LOSS-CAP",         # max loss cap
                       "VOL-CONFIRM",      # volume confirmation on S1 break
                       "SR_MAX_HOLD_LOSS_PCT"):
            self.assertIn(marker, src,
                          f"protection mechanism lost: {marker}")


if __name__ == "__main__":
    unittest.main()
