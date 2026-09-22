import time
import unittest


class _FakeRedis:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def setex(self, key, ttl, value):
        if self.fail:
            raise RuntimeError("redis down")
        self.calls.append((key, ttl, value))


class _FakeStateManager:
    def __init__(self, redis_client=None, available=True):
        self._redis = redis_client
        self._available = available

    def is_available(self):
        return self._available


class TestDashboardHeartbeat(unittest.TestCase):
    def test_publish_bot_heartbeat_writes_expected_redis_key(self):
        from bot_parts.dashboard_heartbeat import (
            DASHBOARD_BOT_HEARTBEAT_KEY,
            DASHBOARD_BOT_HEARTBEAT_TTL_SECONDS,
            publish_bot_heartbeat,
        )

        fake_redis = _FakeRedis()
        ok = publish_bot_heartbeat(fake_redis, now=1_779_341_800)

        self.assertTrue(ok)
        self.assertEqual(
            fake_redis.calls,
            [
                (
                    DASHBOARD_BOT_HEARTBEAT_KEY,
                    DASHBOARD_BOT_HEARTBEAT_TTL_SECONDS,
                    "1779341800",
                )
            ],
        )

    def test_publish_bot_heartbeat_is_best_effort_when_redis_fails(self):
        from bot_parts.dashboard_heartbeat import publish_bot_heartbeat

        ok = publish_bot_heartbeat(_FakeRedis(fail=True), now=1_779_341_800)

        self.assertFalse(ok)

    def test_publish_bot_heartbeat_via_state_manager_checks_availability(self):
        from bot_parts.dashboard_heartbeat import publish_bot_heartbeat_via_state_manager

        redis_client = _FakeRedis()
        unavailable = _FakeStateManager(redis_client=redis_client, available=False)
        ok = publish_bot_heartbeat_via_state_manager(unavailable, now=1_779_341_800)

        self.assertFalse(ok)
        self.assertEqual(redis_client.calls, [])

    def test_start_bot_heartbeat_thread_publishes_until_stop_event(self):
        from threading import Event

        from bot_parts.dashboard_heartbeat import start_bot_heartbeat_thread

        redis_client = _FakeRedis()
        state_manager = _FakeStateManager(redis_client=redis_client, available=True)
        stop_event = Event()

        thread = start_bot_heartbeat_thread(
            state_manager,
            stop_event=stop_event,
            interval_seconds=0.01,
            now_func=lambda: 1_779_341_800,
        )
        time.sleep(0.03)
        stop_event.set()
        thread.join(timeout=1)

        self.assertFalse(thread.is_alive())
        self.assertGreaterEqual(len(redis_client.calls), 1)
        self.assertTrue(all(call[0] == "dashboard:bot:heartbeat" for call in redis_client.calls))
