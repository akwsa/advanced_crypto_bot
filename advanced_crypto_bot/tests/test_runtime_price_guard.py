# Tujuan: Unit tests untuk price sanity guard di autotrade/runtime.py.
# Caller: pytest. Mencegah regresi Bug Critical #1 (BTC=100 IDR data palsu)
# dan Bug Critical #3 (asyncio cross-loop crash di _get_cached_signal).

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from autotrade.runtime import (
    _PAIR_PRICE_FLOOR_IDR,
    _get_cached_signal,
    _is_price_sane_for_pair,
)


class TestPriceFloorGuard(unittest.TestCase):
    """Bug Critical #1: BTC=100 IDR test fixture leaks ke production."""

    def test_btc_real_price_passes(self):
        # BTC ~1.5B IDR — well above floor.
        self.assertTrue(_is_price_sane_for_pair("btcidr", 1_500_000_000))

    def test_btc_at_100_idr_blocked(self):
        # Exact bug scenario from audit.
        self.assertFalse(_is_price_sane_for_pair("btcidr", 100))

    def test_btc_just_below_floor_blocked(self):
        floor = _PAIR_PRICE_FLOOR_IDR["btcidr"]
        self.assertFalse(_is_price_sane_for_pair("btcidr", floor - 1))

    def test_btc_at_floor_passes(self):
        floor = _PAIR_PRICE_FLOOR_IDR["btcidr"]
        self.assertTrue(_is_price_sane_for_pair("btcidr", floor))

    def test_eth_at_100_idr_blocked(self):
        self.assertFalse(_is_price_sane_for_pair("ethidr", 100))

    def test_pair_normalization_works(self):
        # Ensure underscores/slashes don't bypass the guard.
        self.assertFalse(_is_price_sane_for_pair("BTC/IDR", 100))
        self.assertFalse(_is_price_sane_for_pair("btc_idr", 100))
        self.assertFalse(_is_price_sane_for_pair("BTCIDR", 100))

    def test_unknown_pair_passes(self):
        # Small-cap pairs (no floor) should not be blocked — they may
        # legitimately trade at 1 IDR.
        self.assertTrue(_is_price_sane_for_pair("renidr", 1))
        self.assertTrue(_is_price_sane_for_pair("hifiidr", 100))

    def test_zero_or_negative_blocked(self):
        self.assertFalse(_is_price_sane_for_pair("renidr", 0))
        self.assertFalse(_is_price_sane_for_pair("renidr", -1))
        self.assertFalse(_is_price_sane_for_pair("btcidr", 0))

    def test_none_blocked(self):
        self.assertFalse(_is_price_sane_for_pair("btcidr", None))


class TestGetCachedSignalCrossLoop(unittest.TestCase):
    """Bug Critical #3: SignalQueue worker thread runs its own loop;
    awaiting a Task created in the main bot loop raises
    'Task attached to a different loop'. _get_cached_signal must detect
    this and create a fresh task in the current loop.
    """

    def _make_bot(self):
        return SimpleNamespace(
            _signal_result_cache={},
            _signal_inflight_tasks={},
        )

    def test_inflight_task_from_other_loop_is_replaced(self):
        bot = self._make_bot()
        pair = "btcidr"

        # Create a "stale" task that lives in loop_a.
        loop_a = asyncio.new_event_loop()

        async def long_running_signal(*_args, **_kwargs):
            await asyncio.sleep(10)
            return {"recommendation": "STALE"}

        async def install_stale_task():
            stale = asyncio.create_task(long_running_signal())
            bot._signal_inflight_tasks[pair] = stale
            return stale

        stale_task = loop_a.run_until_complete(install_stale_task())
        self.assertFalse(stale_task.done())

        # Now run _get_cached_signal in a DIFFERENT loop. Without the
        # cross-loop guard this would raise
        # "got Future <...> attached to a different loop".
        loop_b = asyncio.new_event_loop()
        try:
            fresh_mock = AsyncMock(return_value={"recommendation": "FRESH"})
            with patch("autotrade.runtime.generate_signal_for_pair", fresh_mock):
                result = loop_b.run_until_complete(_get_cached_signal(bot, pair))

            self.assertIsNotNone(result)
            self.assertEqual(result["recommendation"], "FRESH")
        finally:
            stale_task.cancel()
            try:
                loop_a.run_until_complete(asyncio.gather(stale_task, return_exceptions=True))
            except Exception:
                pass
            loop_a.close()
            loop_b.close()

    def test_inflight_task_same_loop_is_reused(self):
        bot = self._make_bot()
        pair = "ethidr"
        call_count = {"n": 0}

        async def slow_generator(*_args, **_kwargs):
            call_count["n"] += 1
            await asyncio.sleep(0.01)
            return {"recommendation": "BUY", "price": 50_000_000}

        async def scenario():
            # Two concurrent calls in the same loop should share one task.
            with patch(
                "autotrade.runtime.generate_signal_for_pair",
                side_effect=slow_generator,
            ):
                results = await asyncio.gather(
                    _get_cached_signal(bot, pair),
                    _get_cached_signal(bot, pair),
                )
            return results

        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(scenario())
        finally:
            loop.close()

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["recommendation"], "BUY")
        # Generator called only once — second call awaited the inflight task.
        self.assertEqual(call_count["n"], 1)


if __name__ == "__main__":
    unittest.main()
