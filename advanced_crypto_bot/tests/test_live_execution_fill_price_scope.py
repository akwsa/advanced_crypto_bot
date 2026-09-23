"""Regression: cabang LIVE (is_dry_run=False) tidak boleh mereferensikan
`fill_price`, yang hanya didefinisikan di dalam cabang DRY RUN.

Sebelum fix, baris set_price_level pada cabang LIVE memakai `float(fill_price)`
sebagai entry price. Karena `fill_price` hanya pernah di-assign di blok
`if is_dry_run:` (runtime.py:2002), cabang LIVE akan raise NameError saat order
real sudah ter-placement — order terkirim tapi SL/TP tidak terpasang.
"""
import ast
import unittest


SRC_PATH = "autotrade/runtime.py"
FN_NAME = "_check_trading_opportunity_locked"


def _load_fn():
    src = open(SRC_PATH, encoding="utf-8").read()
    tree = ast.parse(src)
    fn = next(
        n for n in tree.body
        if getattr(n, "name", None) == FN_NAME
    )
    return src, fn


def _execution_split(fn):
    """If `is_dry_run` yang percabangannya ke add_trade/create_order."""
    for node in ast.walk(fn):
        if isinstance(node, ast.If) and ast.unparse(node.test) == "is_dry_run":
            body_src = ast.unparse(node)
            if "add_trade" in body_src or "create_atomic_dryrun_fill" in body_src:
                return node
    return None


class TestLiveBranchFillPriceScope(unittest.TestCase):

    def test_live_branch_does_not_reference_dry_run_fill_price(self):
        _, fn = _load_fn()
        split = _execution_split(fn)
        self.assertIsNotNone(split, "execution split (if is_dry_run) not found")
        self.assertTrue(split.orelse, "LIVE branch (else) missing")

        live_branch = ast.Module(body=split.orelse, type_ignores=[])
        live_src = ast.unparse(live_branch)
        self.assertNotIn("fill_price", live_src,
                         "LIVE branch references fill_price (DRY-RUN-only var)")

        for node in ast.walk(live_branch):
            if isinstance(node, ast.Name):
                self.assertNotEqual(node.id, "fill_price",
                                    "LIVE branch references dry-run-only fill_price")

    def test_live_branch_registers_price_level_with_execution_price(self):
        """LIVE entry_price level = harga eksekusi (VWAP / limit fill).

        BUG-1 (2026-09-23): level SL/TP dianchor ke current_price (market saat
        sinyal) dan smart routing menimpa current_price=avg_price SETELAH
        kalkulasi, jadi level keluar tidak relatif terhadap harga masuk
        sungguhan. Setelah fix, LIVE branch merecompute level dari
        execution_price -- identik dengan DRY RUN yang memakai fill_price.
        """
        _, fn = _load_fn()
        split = _execution_split(fn)
        live_branch = ast.Module(body=split.orelse, type_ignores=[])

        calls = [c for c in ast.walk(live_branch)
                 if isinstance(c, ast.Call)
                 and getattr(c.func, "attr", None) == "set_price_level"]
        self.assertTrue(calls, "LIVE branch must register SL/TP price level")
        for call in calls:
            args = [ast.unparse(a) for a in call.args]
            self.assertTrue(any("execution_price" in a for a in args),
                            f"LIVE set_price_level must use execution_price, got {args}")

    def test_live_branch_records_nonzero_fee_from_total(self):
        _, fn = _load_fn()
        split = _execution_split(fn)
        live_branch = ast.Module(body=split.orelse, type_ignores=[])

        calls = [c for c in ast.walk(live_branch)
                 if isinstance(c, ast.Call)
                 and getattr(c.func, "attr", None) == "add_trade"]
        self.assertTrue(calls, "LIVE branch must record the real order as a trade")
        for call in calls:
            fee_kw = next((kw for kw in call.keywords if kw.arg == "fee"), None)
            self.assertIsNotNone(fee_kw, "LIVE add_trade must pass fee explicitly")
            self.assertNotEqual(ast.unparse(fee_kw.value), "0",
                                "LIVE add_trade must not hard-code fee=0")
            self.assertIn("live_fee", ast.unparse(fee_kw.value))

    def test_live_branch_has_final_size_guard(self):
        _, fn = _load_fn()
        split = _execution_split(fn)
        fn_src = ast.unparse(fn)

        self.assertIn("LIVE_SIZE_GUARD", fn_src)
        self.assertIn("MAX_TRADE_AMOUNT", fn_src)
        self.assertIn("MIN_TRADE_AMOUNT", fn_src)

        max_guard_lines = [
            n.lineno for n in ast.walk(fn)
            if isinstance(n, ast.Constant) and n.value == "MAX_TRADE_AMOUNT"
        ]
        self.assertTrue(max_guard_lines, "LIVE guard must reference MAX_TRADE_AMOUNT")
        self.assertLess(min(max_guard_lines), split.lineno,
                        "LIVE size guard must run before the final execution split")

    def test_dry_run_branch_still_owns_fill_price(self):
        """Sanity: DRY RUN branch tetap memakai fill_price (slippage fill)."""
        _, fn = _load_fn()
        split = _execution_split(fn)
        dry_src = ast.unparse(split)
        self.assertIn("fill_price", dry_src)


if __name__ == "__main__":
    unittest.main()
