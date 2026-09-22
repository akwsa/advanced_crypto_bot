# Tujuan: Test fitur AUTO TP/SL scalper — kalkulasi, auto-apply, trailing stop, override manual.
# Caller: unittest focused scalper test policy.
# Dependensi: scalper.scalper_module, fake Telegram message/callback.
# Main Functions: class TestAutoTpSl.
# Side Effects: Temporary file I/O untuk fallback posisi.
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scalper.scalper_module import ScalperConfig, ScalperModule


# ── Fakes ──────────────────────────────────────────────────────

class _FakeStateManager:
    def __init__(self):
        self._positions_cache = {}

    def get_all_positions(self):
        return dict(self._positions_cache)

    def set_position(self, pair, position):
        pair = pair.lower().replace("/", "").replace("_", "")
        if not pair.endswith("idr"):
            pair += "idr"
        self._positions_cache[pair] = dict(position)

    def clear_positions(self):
        self._positions_cache.clear()

    def is_available(self):
        return False


class _FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class _FakeCallbackQuery:
    def __init__(self, data, user_id=123):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = _FakeMessage()
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.message.replies.append((text, kwargs))


# ── Tests ──────────────────────────────────────────────────────

class TestAutoTpSl(unittest.IsolatedAsyncioTestCase):
    """Tests for AUTO TP/SL feature in ScalperModule."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.positions_file = Path(self.tmpdir.name) / "scalper_positions.json"
        # Save original config values to restore in tearDown
        self._orig_auto_enabled = ScalperConfig.AUTO_TP_SL_ENABLED
        self._orig_auto_tp = ScalperConfig.AUTO_TP_PCT
        self._orig_auto_sl = ScalperConfig.AUTO_SL_PCT
        self._orig_auto_rr = ScalperConfig.AUTO_RISK_REWARD_RATIO
        self._orig_trailing_enabled = ScalperConfig.AUTO_TRAILING_STOP_ENABLED
        self._orig_trailing_dist = ScalperConfig.AUTO_TRAILING_DISTANCE_PCT
        self._orig_trailing_step = ScalperConfig.AUTO_TRAILING_STEP_PCT

    def tearDown(self):
        ScalperConfig.AUTO_TP_SL_ENABLED = self._orig_auto_enabled
        ScalperConfig.AUTO_TP_PCT = self._orig_auto_tp
        ScalperConfig.AUTO_SL_PCT = self._orig_auto_sl
        ScalperConfig.AUTO_RISK_REWARD_RATIO = self._orig_auto_rr
        ScalperConfig.AUTO_TRAILING_STOP_ENABLED = self._orig_trailing_enabled
        ScalperConfig.AUTO_TRAILING_DISTANCE_PCT = self._orig_trailing_dist
        ScalperConfig.AUTO_TRAILING_STEP_PCT = self._orig_trailing_step

    def _scalper(self):
        scalper = ScalperModule.__new__(ScalperModule)
        scalper.admin_ids = [123]
        scalper.state_manager = _FakeStateManager()
        scalper.positions_file = str(self.positions_file)
        scalper.balance = 50_000_000
        scalper.dry_run = True
        scalper.is_real_trading = False
        scalper.indodax = None
        scalper.pairs = []
        scalper.alerted_positions = set()
        scalper.notified_drops = {}
        scalper.last_alert_time = None
        scalper._positions_reset_generation = 0
        return scalper

    def _update(self):
        message = _FakeMessage()
        return SimpleNamespace(
            callback_query=None,
            effective_user=SimpleNamespace(id=123),
            effective_message=message,
        )

    # ── Calculate Auto TP/SL ───────────────────────────────────

    def test_calculate_auto_tp_sl_default(self):
        """Default: TP +3%, SL -2% from entry."""
        scalper = self._scalper()
        ScalperConfig.AUTO_TP_PCT = 0.03
        ScalperConfig.AUTO_SL_PCT = 0.02
        ScalperConfig.AUTO_RISK_REWARD_RATIO = 1.5

        tp, sl = scalper._calculate_auto_tp_sl(1000)

        self.assertAlmostEqual(tp, 1030.0)   # 1000 * 1.03
        self.assertAlmostEqual(sl, 980.0)     # 1000 * 0.98

    def test_calculate_auto_tp_sl_enforces_rr_ratio(self):
        """TP is bumped if TP% < SL% * R/R ratio."""
        scalper = self._scalper()
        ScalperConfig.AUTO_TP_PCT = 0.02     # 2% TP
        ScalperConfig.AUTO_SL_PCT = 0.02     # 2% SL
        ScalperConfig.AUTO_RISK_REWARD_RATIO = 2.0  # Need 2:1

        tp, sl = scalper._calculate_auto_tp_sl(1000)

        # min_tp_pct = 0.02 * 2.0 = 0.04 -> TP should be 1040
        self.assertAlmostEqual(tp, 1040.0)
        self.assertAlmostEqual(sl, 980.0)

    def test_calculate_auto_tp_sl_zero_entry_returns_none(self):
        """Zero or negative entry returns (None, None)."""
        scalper = self._scalper()
        self.assertEqual(scalper._calculate_auto_tp_sl(0), (None, None))
        self.assertEqual(scalper._calculate_auto_tp_sl(-100), (None, None))

    # ── Auto Apply TP/SL ───────────────────────────────────────

    def test_auto_apply_tp_sl_sets_tp_sl_on_new_position(self):
        """Auto apply adds TP/SL + auto_sltp flag to position without TP/SL."""
        scalper = self._scalper()
        ScalperConfig.AUTO_TP_SL_ENABLED = True
        ScalperConfig.AUTO_TP_PCT = 0.03
        ScalperConfig.AUTO_SL_PCT = 0.02

        scalper.active_positions["btcidr"] = {
            "entry": 1000, "time": 1, "amount": 10, "capital": 10000
        }
        scalper._auto_apply_tp_sl("btcidr")

        pos = scalper.active_positions["btcidr"]
        self.assertAlmostEqual(pos["tp"], 1030.0)
        self.assertAlmostEqual(pos["sl"], 980.0)
        self.assertTrue(pos["auto_sltp"])
        self.assertIn("trailing_high", pos)

    def test_auto_apply_tp_sl_skips_when_disabled(self):
        """No TP/SL applied when AUTO_TP_SL_ENABLED is False."""
        scalper = self._scalper()
        ScalperConfig.AUTO_TP_SL_ENABLED = False

        scalper.active_positions["btcidr"] = {
            "entry": 1000, "time": 1, "amount": 10, "capital": 10000
        }
        scalper._auto_apply_tp_sl("btcidr")

        pos = scalper.active_positions["btcidr"]
        self.assertNotIn("tp", pos)
        self.assertNotIn("sl", pos)
        self.assertNotIn("auto_sltp", pos)

    def test_auto_apply_tp_sl_skips_existing_manual_tp(self):
        """Does not overwrite position that already has manual TP set."""
        scalper = self._scalper()
        ScalperConfig.AUTO_TP_SL_ENABLED = True

        scalper.active_positions["btcidr"] = {
            "entry": 1000, "time": 1, "amount": 10, "capital": 10000,
            "tp": 1100, "sl": 950,
        }
        scalper._auto_apply_tp_sl("btcidr")

        pos = scalper.active_positions["btcidr"]
        # Should keep manual values
        self.assertEqual(pos["tp"], 1100)
        self.assertEqual(pos["sl"], 950)
        self.assertNotIn("auto_sltp", pos)

    def test_auto_apply_tp_sl_skips_existing_auto(self):
        """Does not overwrite position that already has auto_sltp set."""
        scalper = self._scalper()
        ScalperConfig.AUTO_TP_SL_ENABLED = True

        scalper.active_positions["btcidr"] = {
            "entry": 1000, "time": 1, "amount": 10, "capital": 10000,
            "tp": 1030, "sl": 980, "auto_sltp": True, "trailing_high": 1000,
        }
        scalper._auto_apply_tp_sl("btcidr")

        pos = scalper.active_positions["btcidr"]
        self.assertEqual(pos["tp"], 1030)
        self.assertEqual(pos["sl"], 980)

    def test_auto_apply_tp_sl_missing_pair_no_error(self):
        """Applying to non-existent pair does not crash."""
        scalper = self._scalper()
        ScalperConfig.AUTO_TP_SL_ENABLED = True
        # Should not raise
        scalper._auto_apply_tp_sl("nonexistentidr")

    # ── Trailing Stop ──────────────────────────────────────────

    def test_trailing_stop_updates_sl_when_price_rises(self):
        """Trailing stop raises SL when price rises above step threshold."""
        scalper = self._scalper()
        ScalperConfig.AUTO_TRAILING_STOP_ENABLED = True
        ScalperConfig.AUTO_TRAILING_DISTANCE_PCT = 0.01  # 1% distance
        ScalperConfig.AUTO_TRAILING_STEP_PCT = 0.005     # 0.5% step

        pos = {
            "entry": 1000, "tp": 1030, "sl": 980,
            "auto_sltp": True, "trailing_high": 1000
        }

        # Price rises by 2% — well above the 0.5% step
        scalper._check_trailing_stop("btcidr", pos, 1020)

        # trailing_high should update
        self.assertAlmostEqual(pos["trailing_high"], 1020.0)
        # SL should be raised to 1020 * 0.99 = 1009.8
        self.assertAlmostEqual(pos["sl"], 1020 * 0.99)

    def test_trailing_stop_does_not_lower_sl(self):
        """Trailing stop never lowers SL, only raises it."""
        scalper = self._scalper()
        ScalperConfig.AUTO_TRAILING_STOP_ENABLED = True
        ScalperConfig.AUTO_TRAILING_DISTANCE_PCT = 0.01
        ScalperConfig.AUTO_TRAILING_STEP_PCT = 0.005

        pos = {
            "entry": 1000, "tp": 1030, "sl": 1010,  # SL already high
            "auto_sltp": True, "trailing_high": 1015
        }

        # Price drops slightly — new_sl would be lower than current sl
        scalper._check_trailing_stop("btcidr", pos, 1012)

        # SL should remain unchanged (1010), not lowered
        self.assertEqual(pos["sl"], 1010)

    def test_trailing_stop_disabled_does_nothing(self):
        """Trailing stop does nothing when disabled."""
        scalper = self._scalper()
        ScalperConfig.AUTO_TRAILING_STOP_ENABLED = False

        pos = {
            "entry": 1000, "tp": 1030, "sl": 980,
            "auto_sltp": True, "trailing_high": 1000
        }
        scalper._check_trailing_stop("btcidr", pos, 1050)

        # Nothing should change
        self.assertEqual(pos["trailing_high"], 1000)
        self.assertEqual(pos["sl"], 980)

    def test_trailing_stop_skips_non_auto_positions(self):
        """Trailing stop skips positions without auto_sltp flag."""
        scalper = self._scalper()
        ScalperConfig.AUTO_TRAILING_STOP_ENABLED = True

        pos = {
            "entry": 1000, "tp": 1030, "sl": 980,
            # No auto_sltp flag
        }
        scalper._check_trailing_stop("btcidr", pos, 1050)

        self.assertEqual(pos["sl"], 980)

    def test_trailing_stop_step_threshold_prevents_micro_updates(self):
        """Price must rise by at least step_pct to trigger trailing update."""
        scalper = self._scalper()
        ScalperConfig.AUTO_TRAILING_STOP_ENABLED = True
        ScalperConfig.AUTO_TRAILING_DISTANCE_PCT = 0.01
        ScalperConfig.AUTO_TRAILING_STEP_PCT = 0.01  # 1% step required

        pos = {
            "entry": 1000, "tp": 1030, "sl": 980,
            "auto_sltp": True, "trailing_high": 1000
        }

        # Price rises by only 0.3% — below the 1% step
        scalper._check_trailing_stop("btcidr", pos, 1003)

        # Should NOT update because step not met
        self.assertEqual(pos["trailing_high"], 1000)
        self.assertEqual(pos["sl"], 980)

    # ── Auto TP/SL Status Text ─────────────────────────────────

    def test_auto_sltp_status_text_auto(self):
        scalper = self._scalper()
        self.assertEqual(scalper._auto_sltp_status_text({"auto_sltp": True}), "🤖 AUTO")

    def test_auto_sltp_status_text_manual(self):
        scalper = self._scalper()
        self.assertEqual(scalper._auto_sltp_status_text({"tp": 1030, "sl": 980}), "✋ MANUAL")

    def test_auto_sltp_status_text_none(self):
        scalper = self._scalper()
        self.assertEqual(scalper._auto_sltp_status_text({}), "—")

    # ── Manual Override Clears Auto ─────────────────────────────

    async def test_set_quick_sltp_clears_auto_flag(self):
        """Manual preset TP/SL clears auto_sltp and trailing_high."""
        scalper = self._scalper()
        ScalperConfig.AUTO_TP_SL_ENABLED = True
        scalper.active_positions["btcidr"] = {
            "entry": 1000, "time": 1, "amount": 10, "capital": 10000,
            "tp": 1030, "sl": 980, "auto_sltp": True, "trailing_high": 1020,
        }
        scalper._auto_apply_tp_sl("btcidr")  # Ensure auto is set

        query = _FakeCallbackQuery("s_set_sltp:btcidr:2:1")
        update = SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=123),
            effective_message=query.message,
        )
        await scalper._set_quick_sltp(query, "btcidr", 2.0, 1.0)

        pos = scalper.active_positions["btcidr"]
        self.assertNotIn("auto_sltp", pos)
        self.assertNotIn("trailing_high", pos)
        # New TP/SL should be applied
        self.assertAlmostEqual(pos["tp"], 1020.0)   # 1000 * 1.02
        self.assertAlmostEqual(pos["sl"], 990.0)     # 1000 * 0.99

    async def test_cmd_sltp_clears_auto_flag(self):
        """Command /s_sltp clears auto_sltp and trailing_high."""
        scalper = self._scalper()
        ScalperConfig.AUTO_TP_SL_ENABLED = True
        scalper.active_positions["btcidr"] = {
            "entry": 1000, "time": 1, "amount": 10, "capital": 10000,
            "tp": 1030, "sl": 980, "auto_sltp": True, "trailing_high": 1020,
        }
        update = self._update()
        await scalper.cmd_sltp(update, SimpleNamespace(args=["btcidr", "1100", "950"]))

        pos = scalper.active_positions["btcidr"]
        self.assertNotIn("auto_sltp", pos)
        self.assertNotIn("trailing_high", pos)
        self.assertEqual(pos["tp"], 1100)
        self.assertEqual(pos["sl"], 950)

    # ── Persistence ─────────────────────────────────────────────

    def test_auto_tp_sl_persists_to_file(self):
        """Auto TP/SL fields are saved and loaded from JSON file."""
        scalper = self._scalper()
        ScalperConfig.AUTO_TP_SL_ENABLED = True

        scalper.active_positions["btcidr"] = {
            "entry": 1000, "time": 1, "amount": 10, "capital": 10000
        }
        scalper._auto_apply_tp_sl("btcidr")
        scalper._save_positions()

        # Load from file
        data = json.loads(self.positions_file.read_text(encoding="utf-8"))
        pos = data["positions"]["btcidr"]
        self.assertTrue(pos["auto_sltp"])
        self.assertAlmostEqual(pos["tp"], 1030.0)
        self.assertAlmostEqual(pos["sl"], 980.0)
        self.assertIn("trailing_high", pos)

    # ── Dry Run Buy + Auto TP/SL ───────────────────────────────

    async def test_dryrun_buy_applies_auto_tp_sl(self):
        """DRY RUN buy auto-applies TP/SL when AUTO_TP_SL_ENABLED."""
        scalper = self._scalper()
        ScalperConfig.AUTO_TP_SL_ENABLED = True
        ScalperConfig.AUTO_TP_PCT = 0.05
        ScalperConfig.AUTO_SL_PCT = 0.03

        update = self._update()
        context = SimpleNamespace(args=["BTCIDR", "1000", "500000"])

        with patch("cache.redis_price_cache.price_cache.get_price_sync", return_value=1000):
            await scalper.cmd_buy(update, context)

        self.assertIn("btcidr", scalper.active_positions)
        pos = scalper.active_positions["btcidr"]
        self.assertAlmostEqual(pos["tp"], 1050.0)
        self.assertAlmostEqual(pos["sl"], 970.0)
        self.assertTrue(pos["auto_sltp"])

        # Check reply shows auto label
        reply_text = update.effective_message.replies[-1][0]
        self.assertIn("🤖", reply_text)
        self.assertIn("TP", reply_text)
        self.assertIn("SL", reply_text)

    async def test_dryrun_buy_no_auto_when_disabled(self):
        """DRY RUN buy does NOT auto-apply when AUTO_TP_SL_ENABLED is False."""
        scalper = self._scalper()
        ScalperConfig.AUTO_TP_SL_ENABLED = False

        update = self._update()
        context = SimpleNamespace(args=["BTCIDR", "1000", "500000"])

        with patch("cache.redis_price_cache.price_cache.get_price_sync", return_value=1000):
            await scalper.cmd_buy(update, context)

        self.assertIn("btcidr", scalper.active_positions)
        pos = scalper.active_positions["btcidr"]
        self.assertNotIn("tp", pos)
        self.assertNotIn("sl", pos)
        self.assertNotIn("auto_sltp", pos)

    # ── /s_auto_sltp Command ───────────────────────────────────

    async def test_cmd_auto_sltp_show_config(self):
        """No args shows current config."""
        scalper = self._scalper()
        ScalperConfig.AUTO_TP_SL_ENABLED = True
        ScalperConfig.AUTO_TP_PCT = 0.03
        ScalperConfig.AUTO_SL_PCT = 0.02

        update = self._update()
        await scalper.cmd_auto_sltp(update, SimpleNamespace(args=[]))

        text = update.effective_message.replies[-1][0]
        self.assertIn("AUTO TP/SL Configuration", text)
        self.assertIn("3.0%", text)
        self.assertIn("2.0%", text)

    async def test_cmd_auto_sltp_toggle_on_off(self):
        """Toggle AUTO TP/SL on and off."""
        scalper = self._scalper()
        ScalperConfig.AUTO_TP_SL_ENABLED = False

        update = self._update()
        await scalper.cmd_auto_sltp(update, SimpleNamespace(args=["on"]))
        self.assertTrue(ScalperConfig.AUTO_TP_SL_ENABLED)
        self.assertIn("Diaktifkan", update.effective_message.replies[-1][0])

        update2 = self._update()
        await scalper.cmd_auto_sltp(update2, SimpleNamespace(args=["off"]))
        self.assertFalse(ScalperConfig.AUTO_TP_SL_ENABLED)
        self.assertIn("Dinonaktifkan", update2.effective_message.replies[-1][0])

    async def test_cmd_auto_sltp_set_tp(self):
        """Set auto TP percentage via command."""
        scalper = self._scalper()
        update = self._update()
        await scalper.cmd_auto_sltp(update, SimpleNamespace(args=["tp", "5"]))

        self.assertAlmostEqual(ScalperConfig.AUTO_TP_PCT, 0.05)
        self.assertIn("5.0%", update.effective_message.replies[-1][0])

    async def test_cmd_auto_sltp_set_sl(self):
        """Set auto SL percentage via command."""
        scalper = self._scalper()
        update = self._update()
        await scalper.cmd_auto_sltp(update, SimpleNamespace(args=["sl", "3"]))

        self.assertAlmostEqual(ScalperConfig.AUTO_SL_PCT, 0.03)
        self.assertIn("3.0%", update.effective_message.replies[-1][0])

    async def test_cmd_auto_sltp_apply_to_position(self):
        """Apply auto TP/SL to existing position via command."""
        scalper = self._scalper()
        ScalperConfig.AUTO_TP_SL_ENABLED = True
        scalper.active_positions["btcidr"] = {
            "entry": 2000, "time": 1, "amount": 5, "capital": 10000
        }

        update = self._update()
        await scalper.cmd_auto_sltp(update, SimpleNamespace(args=["apply", "btcidr"]))

        pos = scalper.active_positions["btcidr"]
        self.assertTrue(pos["auto_sltp"])
        self.assertAlmostEqual(pos["tp"], 2060.0)  # +3%
        self.assertAlmostEqual(pos["sl"], 1960.0)  # -2%
        text = update.effective_message.replies[-1][0]
        self.assertIn("AUTO TP/SL Applied", text)

    async def test_cmd_auto_sltp_non_admin_blocked(self):
        """Non-admin user cannot use /s_auto_sltp."""
        scalper = self._scalper()
        scalper.admin_ids = [999]  # Different user

        message = _FakeMessage()
        update = SimpleNamespace(
            callback_query=None,
            effective_user=SimpleNamespace(id=123),
            effective_message=message,
        )
        await scalper.cmd_auto_sltp(update, SimpleNamespace(args=[]))

        self.assertIn("Akses Ditolak", update.effective_message.replies[-1][0])

    async def test_cmd_auto_sltp_invalid_tp_rejected(self):
        """Invalid TP percentage is rejected."""
        scalper = self._scalper()
        update = self._update()
        await scalper.cmd_auto_sltp(update, SimpleNamespace(args=["tp", "60"]))

        self.assertIn("Format", update.effective_message.replies[-1][0])


if __name__ == "__main__":
    unittest.main()
