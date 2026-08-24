from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from workers.price_poller import PricePoller


class _PositionDatabase:
    def get_all_open_autotrade_positions(self):
        return [
            {'pair': 'ace_idr'},
            {'pair': 'bico/idr'},
            {'pair': 'humanityidr'},
        ]


@pytest.mark.asyncio
async def test_poller_always_marks_canonical_open_positions():
    bot = SimpleNamespace(subscribers={}, db=_PositionDatabase())
    poller = PricePoller(bot)
    poller.invalid_pairs = {'aceidr'}
    poller._poll_single_pair = AsyncMock()

    with patch('workers.price_poller.Config.WATCH_PAIRS', []), patch(
        'workers.price_poller.asyncio.sleep', new=AsyncMock()
    ):
        await poller._poll_all_pairs()

    polled = {call.args[0] for call in poller._poll_single_pair.await_args_list}
    assert polled == {'aceidr', 'bicoidr', 'humanityidr'}
