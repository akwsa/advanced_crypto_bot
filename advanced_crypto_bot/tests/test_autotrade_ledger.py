import tempfile
import unittest
import threading

from autotrade.contracts import TradeIntent
from core.database import Database


class TestAutoTradeLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db")
        self.db = Database(self.tmp.name)
        self.intent = TradeIntent.from_signal({
            "signal_id": "signal-1", "pair": "btcidr", "signal_type": "BUY",
            "confidence": .8, "price": 100.0, "created_at": 1_800_000_000,
            "data": {"signal": {"recommendation": "BUY", "indicators": {"rsi": 40}}},
        })

    def tearDown(self):
        self.db.close()
        self.tmp.close()

    def test_migration_is_rerunnable(self):
        self.db._create_tables()
        self.db._create_tables()

    def test_fill_replay_is_idempotent_and_reconstructable(self):
        first = self.db.record_dryrun_fill(intent=self.intent, user_id=1,
            order_id="DRY-1", pair="btcidr", side="BUY", price=101,
            quantity=2, fee=0.2)
        replay = self.db.record_dryrun_fill(intent=self.intent, user_id=1,
            order_id="DRY-1", pair="btcidr", side="BUY", price=101,
            quantity=2, fee=0.2)
        self.assertTrue(first["inserted"])
        self.assertFalse(replay["inserted"])
        position = self.db.get_autotrade_position("btcidr", 1)
        self.assertEqual(position["quantity"], 2)
        self.assertEqual(position["cost_basis"], 202)
        self.assertEqual(position["avg_price"], 101)
        self.assertEqual(position["fees"], 0.2)

    def test_invalid_fill_rolls_back(self):
        with self.assertRaises(ValueError):
            self.db.record_dryrun_fill(intent=self.intent, user_id=1,
                order_id="DRY-BAD", pair="btcidr", side="BUY", price=0,
                quantity=2, fee=0)
        with self.db.get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM autotrade_orders").fetchone()[0]
        self.assertEqual(count, 0)

    def test_deferred_pending_promotes_once(self):
        self.db.record_dryrun_pending(intent=self.intent, user_id=7, order_id="DRY-P",
            pair="btcidr", side="BUY", limit_price=100, quantity=2)
        first = self.db.promote_dryrun_pending_fill(order_id="DRY-P", user_id=7,
            price=99, fee=.2)
        replay = self.db.promote_dryrun_pending_fill(order_id="DRY-P", user_id=7,
            price=99, fee=.2)
        self.assertTrue(first["inserted"])
        self.assertIsNone(replay)
        position = self.db.get_autotrade_position("btcidr", 7)
        self.assertEqual(position["quantity"], 2)
        self.assertEqual(position["cost_basis"], 198)

    def test_sell_close_and_rebuild_projection(self):
        self.db.record_dryrun_fill(intent=self.intent,user_id=9,order_id="B1",pair="btcidr",side="BUY",price=100,quantity=2,fee=.1)
        self.assertTrue(self.db.record_dryrun_sell(fill_key="S1",order_id="S1",pair="btcidr",user_id=9,price=110,quantity=1,fee=.1))
        self.assertFalse(self.db.record_dryrun_sell(fill_key="S1",order_id="S1",pair="btcidr",user_id=9,price=110,quantity=1,fee=.1))
        rebuilt=self.db.rebuild_autotrade_position("btcidr",9)
        self.assertEqual(rebuilt["quantity"],1)
        self.assertEqual(rebuilt["cost_basis"],100)
        self.db.record_dryrun_sell(fill_key="S2",order_id="S2",pair="btcidr",user_id=9,price=120,quantity=1,fee=.1)
        self.assertEqual(self.db.rebuild_autotrade_position("btcidr",9)["status"],"CLOSED")

    def test_atomic_fill_failure_rolls_back_both_ledgers(self):
        with self.assertRaises(RuntimeError):
            self.db.create_atomic_dryrun_fill(intent=self.intent,user_id=1,order_id="AF",pair="btcidr",price=100,quantity=1,fee=0,confidence=.8,notes="x",inject_failure=True)
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0],0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM autotrade_fills").fetchone()[0],0)

    def test_atomic_pending_and_promotion_failure_roll_back(self):
        with self.assertRaises(RuntimeError):
            self.db.create_atomic_dryrun_pending(intent=self.intent,user_id=1,order_id="AP0",pair="btcidr",limit_price=100,quantity=1,notes="{}",inject_failure=True)
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM pending_orders").fetchone()[0],0)
        self.db.create_atomic_dryrun_pending(intent=self.intent,user_id=1,order_id="AP",pair="btcidr",limit_price=100,quantity=1,notes="{}")
        row=self.db.get_pending_order_by_order_id("AP","btcidr")
        with self.assertRaises(RuntimeError):
            self.db.promote_atomic_dryrun_pending(pending_db_id=row['id'],order_id="AP",user_id=1,fill_price=99,fee=0,confidence=.8,notes="fill",inject_failure=True)
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0],0)
            self.assertEqual(conn.execute("SELECT status FROM pending_orders WHERE id=?",(row['id'],)).fetchone()[0],"PENDING")
            self.assertEqual(conn.execute("SELECT status FROM autotrade_orders WHERE order_id='AP'").fetchone()[0],"PENDING")

    def test_atomic_direct_replay_does_not_duplicate_legacy(self):
        args=dict(intent=self.intent,user_id=1,order_id="R1",pair="btcidr",price=100,quantity=1,fee=0,confidence=.8,notes="x")
        first=self.db.create_atomic_dryrun_fill(**args)
        second=self.db.create_atomic_dryrun_fill(**args)
        self.assertEqual(first,second)
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0],1)

    def test_rebuild_isolated_per_user(self):
        a=self.intent
        b=TradeIntent.from_signal({"signal_id":"other","pair":"btcidr","signal_type":"BUY","price":200,"created_at":1_800_000_001})
        self.db.record_dryrun_fill(intent=a,user_id=1,order_id="U1",pair="btcidr",side="BUY",price=100,quantity=1,fee=0)
        self.db.record_dryrun_fill(intent=b,user_id=2,order_id="U2",pair="btcidr",side="BUY",price=200,quantity=3,fee=0)
        self.assertEqual(self.db.rebuild_autotrade_position("btcidr",1)["quantity"],1)
        self.assertEqual(self.db.rebuild_autotrade_position("btcidr",2)["quantity"],3)

    def test_poison_rejection_is_durable(self):
        self.db.record_autotrade_rejection("bad1","POISON_ENVELOPE",{"bad":object()})
        self.db.record_autotrade_rejection("bad1","POISON_ENVELOPE",{})
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM autotrade_rejections").fetchone()[0],1)

    def test_atomic_sell_failure_rolls_back_legacy_and_normalized(self):
        tid=self.db.create_atomic_dryrun_fill(intent=self.intent,user_id=1,order_id="BS",pair="btcidr",price=100,quantity=2,fee=0,confidence=.8,notes="buy")
        with self.assertRaises(RuntimeError):
            self.db.close_atomic_dryrun_position(trade_id=tid,fill_key="SF",order_id="SF",pair="btcidr",user_id=1,sell_price=110,quantity=1,fee=0,reason="test",pnl=10,pnl_pct=10,inject_failure=True)
        self.assertEqual(self.db.get_trade(tid)['amount'],2)
        self.assertEqual(self.db.get_autotrade_position("btcidr",1)['quantity'],2)

    def test_concurrent_same_intent_replay_is_single_logical_fill(self):
        barrier=threading.Barrier(2); results=[]; errors=[]
        def run():
            db=Database(self.tmp.name)
            try:
                barrier.wait()
                results.append(db.create_atomic_dryrun_fill(intent=self.intent,user_id=1,order_id="CC",pair="btcidr",price=100,quantity=1,fee=0,confidence=.8,notes="x"))
            except Exception as exc: errors.append(exc)
            finally: db.close()
        threads=[threading.Thread(target=run) for _ in range(2)]
        [t.start() for t in threads]; [t.join() for t in threads]
        self.assertEqual(errors,[]); self.assertEqual(results[0],results[1])
        with self.db.get_connection() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0],1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM autotrade_orders").fetchone()[0],1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM autotrade_fills").fetchone()[0],1)

    def test_received_intent_can_create_pending(self):
        self.db.record_autotrade_intent(self.intent)
        pid=self.db.create_atomic_dryrun_pending(intent=self.intent,user_id=4,order_id="RP",pair="btcidr",limit_price=100,quantity=1,notes="{}")
        self.assertIsNotNone(pid)
        self.assertEqual(self.db.get_pending_order_by_order_id("RP","btcidr")['status'],"PENDING")

    def test_pending_lookup_isolated_by_user(self):
        self.db.add_pending_order("PU1","btcidr",1,"BUY",100,1)
        self.db.add_pending_order("PU2","btcidr",2,"BUY",100,1)
        self.assertEqual([r['order_id'] for r in self.db.get_pending_orders("btcidr",user_id=1)],["PU1"])
        self.assertEqual([r['order_id'] for r in self.db.get_pending_orders("btcidr",user_id=2)],["PU2"])
