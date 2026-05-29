# Tujuan: Test posisi scalper dry-run, persistence, dan tampilan saldo.
# Caller: unittest focused scalper test policy.
# Dependensi: scalper.scalper_module, fake Telegram message/callback.
# Main Functions: class TestScalperDryRunPositions.
# Side Effects: Temporary file I/O untuk fallback posisi.
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from scalper.scalper_module import ScalperConfig, ScalperModule


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


class _FakeIndodax:
    def __init__(self, idr_balance=123_456, balances=None, balance_hold=None, open_orders=None, trade_history=None, tickers=None):
        self.idr_balance = idr_balance
        self.balances = dict(balances or {})
        self.balance_hold = dict(balance_hold or {})
        self.open_orders = open_orders if open_orders is not None else []
        self.trade_history = dict(trade_history or {})
        self.tickers = list(tickers or [])
        self.orders = []

    def get_balance(self):
        balance = {"idr": str(self.idr_balance)}
        balance.update({asset: str(amount) for asset, amount in self.balances.items()})
        return {
            "balance": balance,
            "balance_hold": {asset: str(amount) for asset, amount in self.balance_hold.items()},
        }

    def get_open_orders(self):
        return self.open_orders

    def get_trade_history(self, pair=None, limit=100):
        normalized = str(pair or "").lower().replace("/", "").replace("_", "")
        if normalized and not normalized.endswith("idr"):
            normalized += "idr"
        return self.trade_history.get(normalized, [])

    def get_all_tickers(self):
        return list(self.tickers)

    def create_order(self, pair, order_type, price, amount):
        normalized = str(pair or "").lower().replace("/", "").replace("_", "")
        if normalized and not normalized.endswith("idr"):
            normalized += "idr"
        self.orders.append({
            "pair": normalized,
            "type": order_type,
            "price": float(price),
            "amount": float(amount),
        })
        return {"success": 1, "return": {"order_id": "sell-123"}}


class _FakeRedisStateManager(_FakeStateManager):
    def __init__(self):
        super().__init__()
        self.redis_positions = {}

    def get_all_positions(self):
        self._positions_cache.update(self.redis_positions)
        return dict(self._positions_cache)

    def set_position(self, pair, position):
        super().set_position(pair, position)
        self.redis_positions[pair] = dict(position)

    def clear_positions(self):
        super().clear_positions()
        self.redis_positions.clear()

    def is_available(self):
        return True


class _FakeMessage:
    def __init__(self):
        self.replies = []
        self.edits = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return self

    async def edit_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class _FakeCallbackQuery:
    def __init__(self, data, user_id=123):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = _FakeMessage()
        self.answers = []
        self.edits = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class TestScalperDryRunPositions(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.positions_file = Path(self.tmpdir.name) / "scalper_positions.json"

        self.old_initial_balance = ScalperConfig.INITIAL_BALANCE
        ScalperConfig.INITIAL_BALANCE = 50_000_000

    def tearDown(self):
        ScalperConfig.INITIAL_BALANCE = self.old_initial_balance

    def _scalper(self, real=False, indodax=None):
        scalper = ScalperModule.__new__(ScalperModule)
        scalper.admin_ids = [123]
        scalper.state_manager = _FakeStateManager()
        scalper.positions_file = str(self.positions_file)
        scalper.balance = 50_000_000
        scalper.dry_run = not real
        scalper.is_real_trading = bool(real)
        scalper.indodax = indodax
        scalper.force_real_trading = bool(real)
        scalper.indodax_key = "key" if real else ""
        scalper.indodax_secret = "secret" if real else ""
        scalper.pairs = []
        scalper.alerted_positions = set()
        scalper.notified_drops = {}
        scalper.last_alert_time = None
        return scalper

    def _update(self):
        message = _FakeMessage()
        return SimpleNamespace(
            callback_query=None,
            effective_user=SimpleNamespace(id=123),
            effective_message=message,
        )

    def _callback_update(self, data):
        query = _FakeCallbackQuery(data)
        return SimpleNamespace(
            callback_query=query,
            effective_user=SimpleNamespace(id=123),
            effective_message=query.message,
        )

    async def test_real_only_buy_command_blocks_without_client_and_no_autotrade_dryrun_hint(self):
        scalper = self._scalper(real=True)
        scalper.indodax = None
        update = self._update()

        await scalper.cmd_buy(update, SimpleNamespace(args=["jellyjellyidr", "805", "50000"]))

        self.assertEqual(scalper.balance, 50_000_000)
        self.assertNotIn("jellyjellyidr", scalper.active_positions)
        reply = update.effective_message.replies[-1][0]
        self.assertIn("REAL BUY DIBATALKAN", reply)
        self.assertIn("tidak punya mode DRY RUN lagi", reply)
        self.assertNotIn("/autotrade dryrun", reply)

    async def test_real_only_sell_command_blocks_without_client_and_keeps_position(self):
        scalper = self._scalper(real=True)
        scalper.indodax = None
        scalper.active_positions["jellyjellyidr"] = {
            "entry": 800,
            "time": 0,
            "amount": 62.0,
            "capital": 50_000,
        }
        update = self._update()

        await scalper.cmd_sell(update, SimpleNamespace(args=["jellyjellyidr", "805"]))

        self.assertIn("jellyjellyidr", scalper.active_positions)
        self.assertEqual(scalper.balance, 50_000_000)
        reply = update.effective_message.replies[-1][0]
        self.assertIn("REAL SELL DIBATALKAN", reply)
        self.assertNotIn("/autotrade dryrun", reply)

    async def test_dryrun_buy_persists_position_and_sell_finds_uppercase_pair(self):
        scalper = self._scalper()

        buy_update = self._update()
        buy_context = SimpleNamespace(args=["HYPEIDR", "2940", "5000000"])
        await scalper.cmd_buy(buy_update, buy_context)

        self.assertIn("hypeidr", scalper.active_positions)
        self.assertEqual(scalper.balance, 45_000_000)
        saved = json.loads(self.positions_file.read_text(encoding="utf-8"))
        self.assertIn("hypeidr", saved["positions"])

        sell_update = self._update()
        amount = scalper.active_positions["hypeidr"]["amount"]
        sell_context = SimpleNamespace(args=["HYPEIDR", "2990", str(amount)])
        await scalper.cmd_sell(sell_update, sell_context)

        self.assertNotIn("hypeidr", scalper.active_positions)
        self.assertNotIn("Tidak ada posisi", sell_update.effective_message.replies[-1][0])
        self.assertGreater(scalper.balance, 45_000_000)

    async def test_pairs_dashboard_uses_same_order_for_list_and_buttons(self):
        scalper = self._scalper()
        scalper.pairs = ["solidr", "btcidr"]
        scalper.active_positions = {
            "ethidr": {
                "entry": 200,
                "amount": 10,
                "capital": 2000,
                "time": 1,
            }
        }
        scalper._get_signal_for_pair = lambda pair: {"recommendation": "HOLD"}

        update = self._update()
        prices = {"btcidr": 100, "ethidr": 200, "solidr": 300}
        with patch("scalper.scalper_module.price_cache.get_prices_batch", new=AsyncMock(return_value=prices)):
            await scalper.cmd_pairs(update, SimpleNamespace(args=[]))

        text, kwargs = update.effective_message.replies[-1]
        self.assertLess(text.index("BTCIDR"), text.index("ETHIDR"))
        self.assertLess(text.index("ETHIDR"), text.index("SOLIDR"))

        keyboard = kwargs["reply_markup"].inline_keyboard
        action_labels = [(row[0].text, row[1].text) for row in keyboard[:3]]
        self.assertEqual(
            action_labels,
            [
                ("⬇️ BUY BTCIDR", "⬆️ SELL BTCIDR"),
                ("⬇️ BUY ETHIDR", "⬆️ SELL ETHIDR"),
                ("⬇️ BUY SOLIDR", "⬆️ SELL SOLIDR"),
            ],
        )

    async def test_dryrun_average_down_displays_equity_not_zero_cash_only(self):
        scalper = self._scalper()
        scalper.balance = 30_000_000
        scalper.active_positions["l3idr"] = {
            "entry": 214,
            "time": 1,
            "amount": (20_000_000 * (1 - ScalperConfig.TRADING_FEE_PCT)) / 214,
            "capital": 20_000_000,
        }

        buy_update = self._update()
        buy_context = SimpleNamespace(args=["l3idr", "180", "30000000"])
        await scalper.cmd_buy(buy_update, buy_context)

        reply = buy_update.effective_message.replies[-1][0]
        self.assertEqual(scalper.balance, 0)
        self.assertIn("AVERAGE DOWN L3IDR", reply)
        self.assertNotIn("💰 Saldo: 0 IDR", reply)
        self.assertIn("🏦 Kas IDR: 0 IDR", reply)

    def test_load_positions_resets_corrupt_empty_dryrun_balance(self):
        self.positions_file.write_text(
            json.dumps({"balance": 5_000_000, "positions": {}}),
            encoding="utf-8",
        )
        scalper = self._scalper()

        scalper._load_positions()

        self.assertEqual(scalper.balance, 50_000_000)
        saved = json.loads(self.positions_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["balance"], 50_000_000)

    async def test_quick_buy_button_blocks_when_scalper_real_only_and_client_is_none(self):
        scalper = self._scalper(real=True)
        scalper.indodax = None
        scalper.pairs = ["jellyjellyidr"]
        update = self._callback_update("s_confirm_buy:JELLYJELLYIDR:805:50000:0:0")
        context = SimpleNamespace(args=[])

        await scalper.menu_callback(update, context)

        self.assertEqual(scalper.balance, 50_000_000)
        self.assertNotIn("jellyjellyidr", scalper.active_positions)
        reply = update.callback_query.edits[-1][0]
        self.assertIn("REAL BUY DIBATALKAN", reply)
        self.assertIn("tidak punya mode DRY RUN lagi", reply)
        self.assertNotIn("/autotrade dryrun", reply)
        self.assertNotIn("NoneType", reply)
        self.assertFalse(self.positions_file.exists())

    async def test_posisi_shows_scalping_action_buttons_and_summary(self):
        scalper = self._scalper()
        scalper._get_price_from_api_only = lambda pair: 210
        scalper.active_positions["l3idr"] = {
            "entry": 200,
            "time": 1,
            "amount": 100,
            "capital": 20_000,
            "tp": 220,
            "sl": 190,
        }

        update = self._update()
        await scalper.cmd_posisi(update, SimpleNamespace(args=[]))

        text, kwargs = update.effective_message.replies[-1]
        buttons = [
            button.text
            for row in kwargs["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("RINGKASAN", text)
        self.assertIn("L3IDR", text)
        self.assertIn("Kas IDR", text)
        self.assertTrue(any("Sell" in button for button in buttons))
        self.assertTrue(any("Avg" in button for button in buttons))
        self.assertTrue(any("TP/SL" in button for button in buttons))
        self.assertTrue(any("SL BE" in button for button in buttons))

    async def test_posisi_real_mode_uses_indodax_balance_and_mode_label_without_dryrun_cash(self):
        scalper = self._scalper(real=True, indodax=_FakeIndodax(idr_balance=765_432))
        scalper.balance = 50_000_000
        scalper._get_price_from_api_only = lambda pair: 805
        scalper.active_positions["pippinidr"] = {
            "entry": 710,
            "time": 1,
            "amount": 100,
            "capital": 71_000,
        }

        update = self._update()
        with patch("cache.redis_price_cache.price_cache.get_price_sync", return_value=None):
            await scalper.cmd_posisi(update, SimpleNamespace(args=[]))

        text = update.effective_message.replies[-1][0]
        self.assertIn("Mode: 🔴 REAL", text)
        self.assertIn("Saldo Indodax", text)
        self.assertIn("765,432", text)
        self.assertNotIn("DRY RUN", text)
        self.assertNotIn("Kas IDR", text)
        self.assertNotIn("50,000,000", text)

    async def test_refresh_posisi_real_mode_uses_indodax_balance_and_mode_label_without_dryrun_cash(self):
        scalper = self._scalper(real=True, indodax=_FakeIndodax(idr_balance=765_432))
        scalper.balance = 50_000_000
        scalper._get_price_from_api_only = lambda pair: 805
        scalper.active_positions["pippinidr"] = {
            "entry": 710,
            "time": 1,
            "amount": 100,
            "capital": 71_000,
        }

        update = self._callback_update("s_refresh_posisi")
        with patch("cache.redis_price_cache.price_cache.get_price_sync", return_value=None):
            await scalper.refresh_posisi_callback(update, SimpleNamespace(args=[]))

        text = update.callback_query.edits[-1][0]
        self.assertIn("Mode: 🔴 REAL", text)
        self.assertIn("Saldo Indodax", text)
        self.assertIn("765,432", text)
        self.assertNotIn("DRY RUN", text)
        self.assertNotIn("Kas IDR", text)
        self.assertNotIn("50,000,000", text)

    async def test_posisi_real_mode_uses_indodax_trade_history_entry_not_stale_local_cache(self):
        scalper = self._scalper(
            real=True,
            indodax=_FakeIndodax(
                idr_balance=684,
                balances={"eden": "25"},
                trade_history={
                    "edenidr": [
                        {"type": "buy", "price": "1648", "amount": "10", "submit_time": "100"},
                        {"type": "buy", "price": "1704", "amount": "25", "submit_time": "200"},
                    ]
                },
            ),
        )
        scalper._get_price_from_api_only = lambda pair: {"edenidr": 1697}[pair]
        scalper.active_positions["edenidr"] = {
            "entry": 1648,
            "time": 1,
            "amount": 25,
            "capital": 41_200,
        }

        update = self._update()
        with patch("cache.redis_price_cache.price_cache.get_price_sync", return_value=None):
            await scalper.cmd_posisi(update, SimpleNamespace(args=[]))

        text = update.effective_message.replies[-1][0]
        self.assertIn("EDENIDR", text)
        self.assertIn("Entry `1,704`", text)
        self.assertNotIn("Entry `1,648`", text)
        self.assertEqual(scalper.active_positions["edenidr"]["entry"], 1704)
        self.assertEqual(scalper.active_positions["edenidr"]["source"], "indodax_trade_history")

    async def test_sell_callback_real_mode_syncs_holdings_before_confirmation(self):
        indodax = _FakeIndodax(
            idr_balance=684,
            balances={"eden": "25"},
            trade_history={
                "edenidr": [
                    {"type": "buy", "price": "1648", "amount": "10", "submit_time": "100"},
                    {"type": "buy", "price": "1704", "amount": "25", "submit_time": "200"},
                ]
            },
        )
        scalper = self._scalper(real=True, indodax=indodax)
        scalper._get_price_sync = lambda pair: {"edenidr": 1697}[pair]
        scalper._get_price_from_api_only = lambda pair: {"edenidr": 1697}[pair]
        scalper.active_positions["edenidr"] = {
            "entry": 1648,
            "time": 1,
            "amount": 25,
            "capital": 41_200,
        }

        query = _FakeCallbackQuery("s_sell:edenidr")
        await scalper._initiate_sell(query, "edenidr")

        text, kwargs = query.edits[-1]
        callbacks = [
            button.callback_data
            for row in kwargs["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("SELL EDENIDR", text)
        self.assertIn("Entry: `1,704`", text)
        self.assertNotIn("Entry: `1,648`", text)
        self.assertIn("s_confirm_sell:edenidr", callbacks[0])
        self.assertEqual(scalper.active_positions["edenidr"]["entry"], 1704)

    async def test_confirmed_real_sell_uses_indodax_synced_amount_not_stale_local_amount(self):
        indodax = _FakeIndodax(
            idr_balance=684,
            balances={"eden": "25"},
            trade_history={
                "edenidr": [
                    {"type": "buy", "price": "1704", "amount": "25", "submit_time": "200"},
                ]
            },
        )
        scalper = self._scalper(real=True, indodax=indodax)
        scalper._get_price_sync = lambda pair: {"edenidr": 1697}[pair]
        scalper._get_price_from_api_only = lambda pair: {"edenidr": 1697}[pair]
        scalper.active_positions["edenidr"] = {
            "entry": 1648,
            "time": 1,
            "amount": 10,
            "capital": 16_480,
        }

        query = _FakeCallbackQuery("s_confirm_sell:edenidr:1697")
        await scalper._execute_confirmed_sell(query, "edenidr", 1697)

        self.assertEqual(len(indodax.orders), 1)
        self.assertEqual(indodax.orders[0]["pair"], "edenidr")
        self.assertEqual(indodax.orders[0]["type"], "sell")
        self.assertEqual(indodax.orders[0]["amount"], 25)
        self.assertNotIn("edenidr", scalper.active_positions)
        self.assertIn("SELL EDENIDR", query.edits[-1][0])

    async def test_posisi_real_mode_builds_positions_from_indodax_holdings_not_local_cache(self):
        scalper = self._scalper(
            real=True,
            indodax=_FakeIndodax(
                idr_balance=765_432,
                balances={"l3": "100", "pippin": "0"},
            ),
        )
        scalper._get_price_from_api_only = lambda pair: {"l3idr": 210, "pippinidr": 805}[pair]
        scalper.active_positions["pippinidr"] = {
            "entry": 710,
            "time": 1,
            "amount": 100,
            "capital": 71_000,
        }

        update = self._update()
        with patch("cache.redis_price_cache.price_cache.get_price_sync", return_value=None):
            await scalper.cmd_posisi(update, SimpleNamespace(args=[]))

        text, kwargs = update.effective_message.replies[-1]
        callbacks = [
            button.callback_data
            for row in kwargs["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("L3IDR", text)
        self.assertIn("Open: 1", text)
        self.assertNotIn("PIPPINIDR", text)
        self.assertNotIn("Tidak ada posisi", text)
        self.assertIn("s_sell:l3idr", callbacks)

    async def test_refresh_posisi_real_mode_builds_positions_from_indodax_holdings_not_local_cache(self):
        scalper = self._scalper(
            real=True,
            indodax=_FakeIndodax(
                idr_balance=765_432,
                balances={"l3": "100", "pippin": "0"},
            ),
        )
        scalper._get_price_from_api_only = lambda pair: {"l3idr": 210, "pippinidr": 805}[pair]
        scalper.active_positions["pippinidr"] = {
            "entry": 710,
            "time": 1,
            "amount": 100,
            "capital": 71_000,
        }

        update = self._callback_update("s_refresh_posisi")
        with patch("cache.redis_price_cache.price_cache.get_price_sync", return_value=None):
            await scalper.refresh_posisi_callback(update, SimpleNamespace(args=[]))

        text, kwargs = update.callback_query.edits[-1]
        callbacks = [
            button.callback_data
            for row in kwargs["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("L3IDR", text)
        self.assertIn("Open: 1", text)
        self.assertNotIn("PIPPINIDR", text)
        self.assertNotIn("Tidak ada posisi", text)
        self.assertIn("s_sell:l3idr", callbacks)

    async def test_sync_accepts_indodax_open_orders_dict_by_pair_without_str_get_error(self):
        scalper = self._scalper(
            real=True,
            indodax=_FakeIndodax(
                idr_balance=765_432,
                open_orders={
                    "pippin_idr": [
                        {
                            "order": "12345",
                            "type": "buy",
                            "price": "710",
                            "amount_remain": "100",
                        }
                    ],
                    "ignored_idr": "unexpected-non-dict-entry",
                },
            ),
        )

        update = self._update()
        await scalper.cmd_sync(update, SimpleNamespace(args=[]))

        text = update.effective_message.edits[-1][0]
        self.assertNotIn("str' object has no attribute 'get", text)
        self.assertIn("SYNC SELESAI", text)
        self.assertIn("PIPPINIDR", text)
        self.assertIn("pippinidr", scalper.active_positions)
        self.assertEqual(scalper.active_positions["pippinidr"]["order_id"], "12345")

    async def test_posisi_real_mode_uses_indodax_order_history_amount_fields_not_stale_cache(self):
        scalper = self._scalper(
            real=True,
            indodax=_FakeIndodax(
                idr_balance=684,
                balances={"eden": "25"},
                trade_history={
                    "edenidr": [
                        {
                            "order_id": "ed-actual-buy",
                            "type": "buy",
                            "price": "1704",
                            "status": "filled",
                            "submit_time": "1716530000",
                            "finish_time": "1716530100",
                            "order_idr": "42600",
                            "remain_idr": "0",
                        }
                    ]
                },
            ),
        )
        scalper._get_price_from_api_only = lambda pair: 1665
        scalper.active_positions["edenidr"] = {
            "entry": 1648,
            "time": 1,
            "amount": 33.0,
            "capital": 54_384,
        }

        update = self._update()
        with patch("cache.redis_price_cache.price_cache.get_price_sync", return_value=None):
            await scalper.cmd_posisi(update, SimpleNamespace(args=[]))

        text = update.effective_message.replies[-1][0]
        self.assertIn("EDENIDR", text)
        self.assertIn("Entry `1,704`", text)
        self.assertNotIn("Entry `1,648`", text)
        self.assertEqual(scalper.active_positions["edenidr"]["entry"], 1704)
        self.assertEqual(scalper.active_positions["edenidr"]["amount"], 25)
        self.assertEqual(scalper.active_positions["edenidr"]["source"], "indodax_trade_history")

    async def test_real_position_verification_uses_indodax_balance_key(self):
        scalper = self._scalper(
            real=True,
            indodax=_FakeIndodax(idr_balance=684, balances={"eden": "29.20328061"}),
        )

        self.assertTrue(scalper._verify_position_exists("edenidr"))

    async def test_posisi_keeps_position_visible_when_live_price_unavailable(self):
        scalper = self._scalper()
        scalper._get_price_sync = lambda pair: None
        scalper._get_price_from_api_only = lambda pair: None
        scalper.active_positions["myxillaidr"] = {
            "entry": 4_700,
            "time": 1,
            "amount": 5303.19,
            "capital": 25_000_000,
        }

        update = self._update()
        await scalper.cmd_posisi(update, SimpleNamespace(args=[]))

        text, kwargs = update.effective_message.replies[-1]
        buttons = [
            button.text
            for row in kwargs["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("MYXILLAIDR", text)
        self.assertIn("Harga live belum tersedia", text)
        self.assertTrue(any("MYXILLAIDR" in button for button in buttons))
        self.assertTrue(any("Sell" in button for button in buttons))

    async def test_quick_tpsl_callback_sets_presets_from_entry(self):
        scalper = self._scalper()
        scalper.active_positions["l3idr"] = {
            "entry": 200,
            "time": 1,
            "amount": 100,
            "capital": 20_000,
        }

        update = self._callback_update("s_set_sltp:l3idr:2:1")
        await scalper.menu_callback(update, SimpleNamespace(args=[]))

        pos = scalper.active_positions["l3idr"]
        self.assertEqual(pos["tp"], 204)
        self.assertEqual(pos["sl"], 198)
        reply = update.callback_query.edits[-1][0]
        self.assertIn("TP/SL L3IDR", reply)
        self.assertIn("TP +2.00%", reply)
        self.assertIn("SL -1.00%", reply)
        self.assertIn("R/R", reply)
        self.assertIn("bot-side polling", reply)

    async def test_sltp_command_reply_shows_risk_reward_and_bot_side_warning(self):
        scalper = self._scalper()
        scalper.active_positions["l3idr"] = {
            "entry": 200,
            "time": 1,
            "amount": 100,
            "capital": 20_000,
        }

        update = self._update()
        await scalper.cmd_sltp(update, SimpleNamespace(args=["l3", "206", "196"]))

        reply = update.effective_message.replies[-1][0]
        self.assertEqual(scalper.active_positions["l3idr"]["tp"], 206)
        self.assertEqual(scalper.active_positions["l3idr"]["sl"], 196)
        self.assertIn("TP +3.00%", reply)
        self.assertIn("SL -2.00%", reply)
        self.assertIn("R/R: `1.50`", reply)
        self.assertIn("Risk", reply)
        self.assertIn("Reward", reply)
        self.assertIn("bot-side polling", reply)

    async def test_posisi_summary_shows_entry_based_tpsl_percent_and_rr(self):
        scalper = self._scalper()
        prices = {"otheridr": 110, "l3idr": 210}
        scalper._get_price_from_api_only = lambda pair: prices[pair]
        scalper.active_positions["otheridr"] = {
            "entry": 100,
            "time": 1,
            "amount": 50,
            "capital": 5_000,
            "tp": 110,
            "sl": 95,
        }
        scalper.active_positions["l3idr"] = {
            "entry": 200,
            "time": 1,
            "amount": 100,
            "capital": 20_000,
            "tp": 206,
            "sl": 196,
        }

        update = self._update()
        with patch("cache.redis_price_cache.price_cache.get_price_sync", return_value=None):
            await scalper.cmd_posisi(update, SimpleNamespace(args=[]))

        reply = update.effective_message.replies[-1][0]
        self.assertIn("OTHERIDR", reply)
        self.assertIn("TP +10.00%", reply)
        self.assertIn("SL -5.00%", reply)
        self.assertIn("R/R `2.00`", reply)
        self.assertIn("L3IDR", reply)
        self.assertIn("TP +3.00%", reply)
        self.assertIn("SL -2.00%", reply)
        self.assertIn("R/R `1.50`", reply)

    async def test_refresh_posisi_summary_uses_same_entry_based_tpsl_metrics(self):
        scalper = self._scalper()
        scalper._get_price_from_api_only = lambda pair: 210
        scalper.active_positions["l3idr"] = {
            "entry": 200,
            "time": 1,
            "amount": 100,
            "capital": 20_000,
            "tp": 206,
            "sl": 196,
        }

        update = self._callback_update("s_refresh_posisi")
        with patch("cache.redis_price_cache.price_cache.get_price_sync", return_value=None):
            await scalper.refresh_posisi_callback(update, SimpleNamespace(args=[]))

        reply = update.callback_query.edits[-1][0]
        self.assertIn("TP +3.00%", reply)
        self.assertIn("SL -2.00%", reply)
        self.assertIn("R/R `1.50`", reply)

    async def test_quick_tpsl_panel_offers_scalper_presets_with_rr_preview(self):
        scalper = self._scalper()
        scalper.active_positions["l3idr"] = {
            "entry": 200,
            "time": 1,
            "amount": 100,
            "capital": 20_000,
            "tp": 206,
            "sl": 196,
        }

        update = self._callback_update("s_sltp_hint:l3idr")
        await scalper.menu_callback(update, SimpleNamespace(args=[]))

        text, kwargs = update.callback_query.edits[-1]
        buttons = [
            button.text
            for row in kwargs["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("TP +3.00%", text)
        self.assertIn("SL -2.00%", text)
        self.assertIn("R/R", text)
        self.assertIn("bot-side polling", text)
        self.assertIn("TP +1% / SL -0.5%", buttons)
        self.assertIn("TP +2% / SL -1%", buttons)
        self.assertIn("TP +3% / SL -2%", buttons)
        self.assertIn("SL BE", buttons)

    async def test_confirmed_sell_callback_preserves_partial_amount(self):
        scalper = self._scalper()
        scalper.balance = 0
        scalper.active_positions["l3idr"] = {
            "entry": 100,
            "time": 1,
            "amount": 100,
            "capital": 10_000,
        }
        update = self._callback_update("s_confirm_sell:l3idr:120:25")

        await scalper.menu_callback(update, SimpleNamespace(args=[]))

        pos = scalper.active_positions["l3idr"]
        self.assertEqual(pos["amount"], 75)
        self.assertEqual(pos["capital"], 7_500)
        self.assertEqual(scalper.balance, 2_991)

    async def test_sltp_and_cancel_normalize_short_pair(self):
        scalper = self._scalper()
        scalper.active_positions["l3idr"] = {
            "entry": 200,
            "time": 1,
            "amount": 100,
            "capital": 20_000,
            "tp": 220,
            "sl": 190,
        }

        sltp_update = self._update()
        await scalper.cmd_sltp(sltp_update, SimpleNamespace(args=["l3", "230", "180"]))
        self.assertEqual(scalper.active_positions["l3idr"]["tp"], 230)
        self.assertEqual(scalper.active_positions["l3idr"]["sl"], 180)

        cancel_update = self._update()
        await scalper.cmd_cancel(cancel_update, SimpleNamespace(args=["l3", "all"]))
        self.assertNotIn("tp", scalper.active_positions["l3idr"])
        self.assertNotIn("sl", scalper.active_positions["l3idr"])

    async def test_quick_buy_buttons_preserve_micro_price_in_callback(self):
        scalper = self._scalper()
        markup = scalper._build_quick_buy_keyboard("pepeidr", 0.00001234)

        callbacks = [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data.startswith("s_confirm_buy:")
        ]
        self.assertEqual(len(callbacks), 3)
        prices = [float(callback.split(":")[2]) for callback in callbacks]
        self.assertTrue(all(price > 0 for price in prices))
        self.assertTrue(all(price == 0.00001234 for price in prices))

    async def test_quick_buy_recovers_zero_price_then_blocks_real_only_without_client(self):
        scalper = self._scalper(real=True)
        scalper.indodax = None
        scalper.pairs = ["pepeidr"]
        scalper._get_price_sync = lambda pair: 0.00001234
        update = self._callback_update("s_confirm_buy:PEPEIDR:0:500000:0:0")

        await scalper.menu_callback(update, SimpleNamespace(args=[]))

        self.assertEqual(scalper.balance, 50_000_000)
        self.assertNotIn("pepeidr", scalper.active_positions)
        reply = update.callback_query.edits[-1][0]
        self.assertIn("REAL BUY DIBATALKAN", reply)
        self.assertNotIn("Harga tidak valid", reply)
        self.assertNotIn("Price: `0`", reply)
        self.assertNotIn("/autotrade dryrun", reply)

    async def test_cancel_button_still_edits_when_callback_answer_already_failed(self):
        scalper = self._scalper()
        update = self._callback_update("s_cancel_action")

        async def fail_answer(*args, **kwargs):
            raise RuntimeError("callback already answered")

        update.callback_query.answer = fail_answer

        await scalper.menu_callback(update, SimpleNamespace(args=[]))

        self.assertEqual(update.callback_query.edits[-1][0], "✅ Dibatalkan.")

    async def test_real_mode_without_indodax_client_blocks_quick_buy_without_balance_change(self):
        scalper = self._scalper()
        scalper.dry_run = False
        scalper.is_real_trading = True
        scalper.indodax = None
        scalper.pairs = ["jellyjellyidr"]
        update = self._callback_update("s_confirm_buy:jellyjellyidr:805:50000:0:0")
        context = SimpleNamespace(args=[])

        await scalper.menu_callback(update, context)

        self.assertEqual(scalper.balance, 50_000_000)
        self.assertNotIn("jellyjellyidr", scalper.active_positions)
        self.assertIn("REAL BUY DIBATALKAN", update.callback_query.edits[-1][0])
        self.assertNotIn("NoneType", update.callback_query.edits[-1][0])

    def test_tp_sl_sell_blocks_when_scalper_real_only_and_indodax_client_is_none(self):
        scalper = self._scalper(real=True)
        scalper.indodax = None
        sent = []
        scalper._send_telegram_message = lambda *args, **kwargs: sent.append(args)
        scalper.active_positions["jellyjellyidr"] = {
            "entry": 800,
            "time": 0,
            "amount": 62.0,
            "capital": 50_000,
        }

        scalper._execute_real_sell("jellyjellyidr", 805, "TAKE PROFIT")

        self.assertIn("jellyjellyidr", scalper.active_positions)
        self.assertEqual(scalper.balance, 50_000_000)
        self.assertTrue(any("REAL SELL DIBATALKAN" in args[1] for args in sent))

    def test_real_tp_sl_sell_without_indodax_client_does_not_close_position(self):
        scalper = self._scalper()
        scalper.dry_run = False
        scalper.is_real_trading = True
        scalper.indodax = None
        scalper._send_telegram_message = lambda *args, **kwargs: None
        scalper.active_positions["jellyjellyidr"] = {
            "entry": 800,
            "time": 0,
            "amount": 62.0,
            "capital": 50_000,
        }

        scalper._execute_real_sell("jellyjellyidr", 805, "TAKE PROFIT")

        self.assertIn("jellyjellyidr", scalper.active_positions)
        self.assertEqual(scalper.balance, 50_000_000)

    async def test_reset_confirm_clears_positions_alerts_and_saved_state(self):
        scalper = self._scalper()
        scalper.active_positions["pippinidr"] = {
            "entry": 710,
            "time": 0,
            "amount": 100,
            "capital": 71_000,
        }
        scalper.alerted_positions.add("pippinidr")
        scalper.notified_drops["pippinidr"] = {3}
        scalper.balance = 49_929_000

        update = self._update()
        await scalper.cmd_reset(update, SimpleNamespace(args=["confirm"]))

        self.assertEqual(scalper.active_positions, {})
        self.assertEqual(scalper.alerted_positions, set())
        self.assertEqual(scalper.notified_drops, {})
        self.assertEqual(scalper.balance, 50_000_000)
        self.assertIn("RESET SELESAI", update.effective_message.replies[-1][0])

        saved = json.loads(self.positions_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["positions"], {})
        self.assertEqual(saved["notified_drops"], {})

    async def test_reset_confirm_refreshes_pairs_to_top_volume_and_persists(self):
        scalper = self._scalper(indodax=_FakeIndodax(tickers=[
            {"pair": "ethidr", "volume": 2_000_000_000, "last": 1},
            {"pair": "dogeidr", "volume": 999_999_999, "last": 1},
            {"pair": "btcidr", "volume": 5_000_000_000, "last": 1},
            {"pair": "pepeusdt", "volume": 9_000_000_000, "last": 1},
            {"pair": "tinyidr", "volume": 499_999_999, "last": 1},
        ]))
        scalper.pairs = ["hypeidr"]

        update = self._update()
        with patch.object(ScalperConfig, "save_pairs") as save_pairs:
            await scalper.cmd_reset(update, SimpleNamespace(args=["confirm"]))

        self.assertEqual(scalper.pairs, ["btcidr", "ethidr", "dogeidr"])
        save_pairs.assert_called_once_with(["btcidr", "ethidr", "dogeidr"])
        reply = update.effective_message.replies[-1][0]
        self.assertIn("Pair aktif", reply)
        self.assertIn("BTCIDR", reply)
        self.assertIn("ETHIDR", reply)
        self.assertIn("DOGEIDR", reply)
        self.assertNotIn("PEPEUSDT", reply)
        self.assertNotIn("TINYIDR", reply)

    async def test_sell_removes_position_even_when_state_manager_can_repopulate(self):
        scalper = self._scalper()
        scalper.state_manager = _FakeRedisStateManager()
        scalper._get_price_sync = lambda pair: 805
        scalper.active_positions["pippinidr"] = {
            "entry": 710,
            "time": 0,
            "amount": 100,
            "capital": 71_000,
        }
        scalper.state_manager.redis_positions["pippinidr"] = dict(scalper.active_positions["pippinidr"])

        update = self._update()
        await scalper.cmd_sell(update, SimpleNamespace(args=["PIPPINIDR"]))

        self.assertNotIn("pippinidr", scalper.active_positions)
        saved = json.loads(self.positions_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["positions"], {})

        posisi_update = self._update()
        await scalper.cmd_posisi(posisi_update, SimpleNamespace(args=[]))
        text, kwargs = posisi_update.effective_message.replies[-1]
        buttons = [
            button.text
            for row in kwargs["reply_markup"].inline_keyboard
            for button in row
        ]
        self.assertIn("Tidak ada posisi", text)
        self.assertFalse(any("SELL" in button for button in buttons))

    def test_monitor_snapshot_does_not_send_drop_alert_after_reset(self):
        scalper = self._scalper()
        scalper.active_positions["pippinidr"] = {
            "entry": 710,
            "time": 0,
            "amount": 100,
            "capital": 71_000,
        }
        sent = []
        scalper._send_telegram_message = lambda admin_id, msg: sent.append((admin_id, msg))

        def reset_while_fetching_price(pair):
            scalper._reset_position_state()
            return 446

        scalper._get_price_sync = reset_while_fetching_price

        scalper._check_tp_sl_real({"pippinidr": None})

        self.assertEqual(sent, [])
        self.assertEqual(scalper.active_positions, {})
        self.assertEqual(scalper.notified_drops, {})


if __name__ == "__main__":
    unittest.main()
