import json
import os
import sqlite3
import subprocess
import tempfile
import time
import unittest

from autotrade.contracts import TradeIntent
from core.database import Database, build_autotrade_funnel_report


class TestAutotradeFunnel(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tempdir.name, 'funnel.db')
        self.db = Database(self.db_path)

    def tearDown(self):
        self.db.close()
        self.tempdir.cleanup()

    def _intent(self, key, pair='btcidr', user_id=42):
        # Keep the row comfortably inside CLI windows despite second-level
        # SQLite timestamp truncation at the reporting boundary.
        now = time.time() - 60
        return TradeIntent(
            pair=pair,
            recommendation='BUY',
            confidence=0.7,
            price=100.0,
            signal={'pair': pair, 'recommendation': 'BUY', 'price': 100.0},
            created_at=now,
            correlation_id=f'corr-{key}',
            idempotency_key=key,
            user_id=user_id,
        )

    def test_report_breakdowns_conversion_filtering_and_no_mutation(self):
        first = self._intent('first')
        second = self._intent('second', pair='ethidr')
        ignored = self._intent('ignored', user_id=99)
        for intent in (first, second, ignored):
            self.db.record_autotrade_intent(intent)
        self.db.decide_autotrade_intent('first', 'NO_ENTRY', 'ENTRY_QUALITY', 'score low')
        self.db.decide_autotrade_intent('second', 'FILLED', 'DRYRUN_FILL', 'filled')
        self.db.decide_autotrade_intent('ignored', 'NO_ENTRY', 'V4_FILTER', 'bad outcome')
        with self.db.get_connection() as conn:
            before = conn.execute('SELECT COUNT(*) FROM autotrade_intents').fetchone()[0]

        report = self.db.get_autotrade_funnel_report(user_id=42)

        self.assertEqual(report['totals']['actionable_total'], 2)
        self.assertEqual(report['totals']['executed_total'], 1)
        self.assertEqual(report['totals']['terminal_total'], 2)
        self.assertEqual(report['totals']['conversion_rate'], 0.5)
        self.assertEqual(sum(report['by_status'].values()), 2)
        self.assertEqual(sum(report['by_reason'].values()), 2)
        self.assertEqual(sum(report['by_pair'].values()), 2)
        self.assertEqual(report['integrity']['generic_rate'], 0.0)
        self.assertEqual(report['integrity']['excluded_unattributed_total'], 0)
        with self.db.get_connection() as conn:
            after = conn.execute('SELECT COUNT(*) FROM autotrade_intents').fetchone()[0]
        self.assertEqual(after, before)

    def test_empty_range_is_healthy_and_deterministic(self):
        with self.db.get_connection() as conn:
            report = build_autotrade_funnel_report(
                conn, start_at='2099-01-01 00:00:00', end_at='2099-01-02 00:00:00'
            )
        self.assertEqual(report['totals']['actionable_total'], 0)
        self.assertEqual(report['totals']['conversion_rate'], 0.0)
        self.assertEqual(report['totals']['terminal_coverage_rate'], 1.0)
        self.assertEqual(report['by_reason'], {})

    def test_intent_replay_preserves_terminal_decision(self):
        intent = self._intent('same')
        self.db.record_autotrade_intent(intent)
        terminal = self.db.decide_autotrade_intent('same', 'NO_ENTRY', 'LIQUIDITY', 'spread')
        replay = self.db.record_autotrade_intent(intent)
        self.assertEqual(replay['id'], terminal['id'])
        self.assertEqual(replay['status'], 'NO_ENTRY')
        self.assertEqual(replay['reason_code'], 'LIQUIDITY')

    def test_cli_prints_report_and_fails_generic_integrity_gate(self):
        intent = self._intent('generic')
        self.db.record_autotrade_intent(intent)
        self.db.decide_autotrade_intent('generic', 'NO_ENTRY', 'NO_ORDER_CREATED', 'legacy fallback')
        self.db.close_thread_connection()
        result = subprocess.run(
            [
                os.path.join(os.getcwd(), 'venv', 'bin', 'python'),
                'scripts/report_autotrade_funnel.py', '--db', self.db_path,
                '--hours', '1', '--user-id', '42', '--json',
            ],
            cwd=os.getcwd(), capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload['integrity']['passed'])
        self.assertEqual(payload['integrity']['generic_rate'], 1.0)

    def test_generic_codes_are_normalized_and_unattributed_history_is_visible(self):
        attributed = self._intent('generic-normalized')
        self.db.record_autotrade_intent(attributed)
        self.db.decide_autotrade_intent('generic-normalized', 'NO_ENTRY', ' other ', 'legacy')
        with self.db.get_connection() as conn:
            conn.execute('''INSERT INTO autotrade_intents
                (idempotency_key, correlation_id, version, pair, recommendation,
                 signal_json, status, reason_code, created_at)
                VALUES ('legacy-null', 'legacy-null', 1, 'btc_idr', 'BUY', '{}',
                        'NO_ENTRY', 'ENTRY_QUALITY', CURRENT_TIMESTAMP)''')
        report = self.db.get_autotrade_funnel_report(user_id=42)
        self.assertEqual(report['integrity']['generic_total'], 1)
        self.assertEqual(report['integrity']['generic_rate'], 1.0)
        self.assertEqual(report['integrity']['excluded_unattributed_total'], 1)

    def test_cli_rejects_non_finite_hours(self):
        result = subprocess.run(
            [
                os.path.join(os.getcwd(), 'venv', 'bin', 'python'),
                'scripts/report_autotrade_funnel.py', '--db', self.db_path,
                '--hours', 'nan', '--json',
            ],
            cwd=os.getcwd(), capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('must be finite', result.stderr)


if __name__ == '__main__':
    unittest.main()
