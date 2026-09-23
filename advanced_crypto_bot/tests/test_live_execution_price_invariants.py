"""Regression: cabang LIVE (is_dry_run=False) wajib mendaratkan order pada
triple (price, amount, total) yang konsisten DAN level SL/TP yang dianchor
ke harga eksekusi aktual.

BUG-1: SL/TP dihitung dari ``current_price`` (market saat sinyal), dan smart
routing (default ON) menimpa ``current_price = avg_price`` SETELAH kalkulasi.
Di DRY RUN level direcompute dari fill_price via ``tp_fill``; di LIVE tidak.
Hasilnya level keluar LIVE tidak relatif terhadap harga masuk sungguhan.

BUG-2: smart routing set ``amount = total_filled`` dan
``total = total_filled * avg_price``, tapi ``add_trade(price=entry_zone_price)``
-- ``price != total / amount``. Rekonstruksi qty (original_total/price) dan
PnL% yang menjadi feedback Kelly jadi meleset.

Kedua bug hanya muncul saat LIVE, jadi DRY RUN (mode default) tidak pernah
menampakkannya.
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
    return src, tree, fn


def _execution_split(fn):
    """If `is_dry_run` yang percabangannya ke add_trade/create_order."""
    for node in ast.walk(fn):
        if isinstance(node, ast.If) and ast.unparse(node.test) == "is_dry_run":
            body_src = ast.unparse(node)
            if "add_trade" in body_src or "create_atomic_dryrun_fill" in body_src:
                return node
    return None


def _live_module(fn):
    split = _execution_split(fn)
    assert split and split.orelse, "LIVE branch (else) missing"
    return ast.Module(body=split.orelse, type_ignores=[])


def _call_by_method(mod, method):
    return [c for c in ast.walk(mod)
            if isinstance(c, ast.Call) and getattr(c.func, "attr", None) == method]


class TestLiveExecutionPriceInvariants(unittest.TestCase):

    # ---------------------------------------------------------------- BUG-2

    def test_live_branch_records_execution_price_not_entry_zone(self):
        """add_trade di LIVE harus pakai harga eksekusi aktual, bukan limit."""
        _, _, fn = _load_fn()
        live = _live_module(fn)

        calls = _call_by_method(live, "add_trade")
        self.assertTrue(calls, "LIVE branch must record the real order as a trade")
        for call in calls:
            price_kw = next((kw for kw in call.keywords if kw.arg == "price"), None)
            self.assertIsNotNone(price_kw, "LIVE add_trade must pass price explicitly")
            self.assertEqual(ast.unparse(price_kw.value), "execution_price",
                             "LIVE add_trade price must be execution_price (the "
                             "volume-weighted fill price), not entry_zone_price")

    def test_live_branch_maintains_price_amount_total_invariant(self):
        """total harus direcompute = execution_price * amount setelah order."""
        _, _, fn = _load_fn()
        live = _live_module(fn)

        for call in _call_by_method(live, "add_trade"):
            kw = next((kw for kw in call.keywords if kw.arg == "total"), None)
            self.assertIsNotNone(kw, "LIVE add_trade must pass total explicitly")

        # The invariant is structural: ``total = execution_price * amount``
        # must be assigned inside the LIVE branch before add_trade. ``total``
        # is a plain Name at the call site, so the assignment is the real
        # contract -- it makes price == total / amount exactly.
        assigns = [a for a in ast.walk(live)
                   if isinstance(a, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "total" for t in a.targets)]
        reassigns = [ast.unparse(a.value) for a in assigns
                     if "execution_price" in ast.unparse(a.value)]
        self.assertTrue(reassigns,
                        "LIVE branch must assign total = execution_price * amount; "
                        f"found assignments: {[ast.unparse(a.value) for a in assigns]}")

    def test_live_branch_does_not_fabricate_split_order_id(self):
        """routing fallback tidak boleh menghasilkan order_id fiksi."""
        _, tree, fn = _load_fn()
        live = _live_module(fn)
        live_src = ast.unparse(live)
        self.assertNotIn('"SPLIT-ORDER"', live_src,
                         'LIVE branch still fabricates "SPLIT-ORDER" order_id')
        self.assertNotIn("'SPLIT-ORDER'", live_src,
                         "LIVE branch still fabricates 'SPLIT-ORDER' order_id")

    # ---------------------------------------------------------------- BUG-1

    def test_live_branch_reanchors_sltp_to_execution_price(self):
        """SL/TP LIVE harus direcompute dari harga eksekusi (mirror DRY RUN)."""
        _, _, fn = _load_fn()
        live = _live_module(fn)
        live_src = ast.unparse(live)

        self.assertIn("tp_live", live_src,
                      "LIVE branch must recompute SL/TP (tp_live) before set_price_level")
        self.assertIn("calculate_stop_loss_take_profit", live_src,
                      "LIVE branch must call calculate_stop_loss_take_profit after execution")

        # The recompute must pass execution_price as the anchor, not current_price
        calls = [c for c in ast.walk(live)
                 if isinstance(c, ast.Call)
                 and getattr(c.func, "attr", None) == "calculate_stop_loss_take_profit"]
        self.assertTrue(calls, "LIVE branch must recompute SL/TP from the fill")
        anchors = [ast.unparse(a) for c in calls for a in c.args]
        self.assertTrue(any("execution_price" in a for a in anchors),
                        f"SL/TP recompute must anchor to execution_price, got {anchors}")

    def test_live_branch_set_price_level_uses_execution_price(self):
        """entry_price level harus harga eksekusi, bukan entry_zone/market."""
        _, _, fn = _load_fn()
        live = _live_module(fn)

        calls = _call_by_method(live, "set_price_level")
        self.assertTrue(calls, "LIVE branch must register SL/TP price level")
        for call in calls:
            args = [ast.unparse(a) for a in call.args]
            self.assertTrue(any("execution_price" in a for a in args),
                            f"LIVE set_price_level must use execution_price, got {args}")

    def test_live_branch_applies_sr_adjustment_after_reanchor(self):
        """Penyesuaian S/R harus diterapkan ulang setelah re-anchor."""
        _, _, fn = _load_fn()
        live = _live_module(fn)
        live_src = ast.unparse(live)

        self.assertIn("nearest_support", live_src,
                      "LIVE branch must re-apply S/R adjustments after re-anchor")
        self.assertIn("nearest_resistance", live_src,
                      "LIVE branch must re-apply S/R adjustments after re-anchor")

    def test_live_branch_guards_none_sltp(self):
        """Recompute SL/TP yang return None harus diboikot, bukan crash."""
        _, _, fn = _load_fn()
        live = _live_module(fn)
        live_src = ast.unparse(live)

        self.assertIn("LIVE_LEVELS", live_src,
                      "LIVE branch must block when SL/TP recompute returns None")
        self.assertIn("is None", live_src,
                      "LIVE branch must explicitly check for None SL/TP")

    # ------------------------------------------------- DRY RUN unaffected

    def test_dry_run_branch_still_owns_fill_price_recompute(self):
        """Sanity: DRY RUN tetap merecompute SL/TP dari fill_price (tp_fill)."""
        _, _, fn = _load_fn()
        split = _execution_split(fn)
        dry_src = ast.unparse(split)
        self.assertIn("tp_fill", dry_src,
                      "DRY RUN branch must still recompute SL/TP from fill_price")
        self.assertIn("fill_price", dry_src)


if __name__ == "__main__":
    unittest.main()
