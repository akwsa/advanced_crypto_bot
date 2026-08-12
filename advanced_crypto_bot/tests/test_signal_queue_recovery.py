import json
import unittest
from datetime import datetime, timezone
from signals.signal_queue import SignalQueue


class FakeRedis:
    def __init__(self): self.z={}; self.h={}; self.decisions={}; self.l=[]
    def eval(self,script,n,*args):
        if 'ZADD' in script:
            raw=args[-1]; self.z[raw]=float(args[-2]); self.h.pop(raw,None); return 1
        if 'HGET' in script:
            key,raw,terminal=args[-3:]; old=self.decisions.get(key)
            if old is None or terminal=='1': self.decisions[key]=raw; self.l.append(raw); return 1
            return 0
        if not self.z:return None
        raw=min(self.z,key=self.z.get); self.z.pop(raw); self.h[raw]=str(args[-1]); return raw
    def hkeys(self,k): return list(self.h)
    def hgetall(self,k): return dict(self.h)
    def hdel(self,k,raw): self.h.pop(raw,None)
    def zadd(self,k,mapping): self.z.update(mapping)
    def lpush(self,*a): pass
    def ltrim(self,*a): pass
    def incr(self,*a): pass
    def expire(self,*a): pass


class TestQueueRecovery(unittest.TestCase):
    def setUp(self):
        self.q=SignalQueue.__new__(SignalQueue); self.q._connected=True
        self.q._redis=FakeRedis(); self.q.queue_name='q'; self.q.inflight_name='i'; self.q.stats_prefix='stats:'

    def test_crash_before_ack_recovers_then_ack_removes(self):
        raw=json.dumps({'signal_id':'s1','pair':'btcidr','signal_type':'BUY','priority':10})
        self.q._redis.z[raw]=-10
        claimed=self.q.pop_signal()
        self.assertEqual(claimed['signal_id'],'s1')
        self.assertEqual(len(self.q._redis.h),1)
        self.assertEqual(self.q.recover_inflight(0),1)
        claimed=self.q.pop_signal(); self.q.ack(claimed)
        self.assertEqual(self.q._redis.h,{})

    def test_retryable_requeues_then_terminal_acks(self):
        raw=json.dumps({'signal_id':'s2','pair':'btcidr','signal_type':'BUY','priority':10})
        self.q._redis.z[raw]=-10
        claimed=self.q.pop_signal()
        self.assertEqual(self.q.settle(claimed,{'status':'ERROR_RETRYABLE','idempotency_key':'k'}),'REQUEUED')
        self.assertTrue(self.q._redis.z); self.assertFalse(self.q._redis.h)
        claimed=self.q.pop_signal()
        self.assertEqual(self.q.settle(claimed,{'status':'FILLED','idempotency_key':'k'}),'ACKED')
        self.assertFalse(self.q._redis.h)
        self.assertEqual(len(self.q._redis.decisions),1)

    def test_push_serializes_production_datetime_without_dropping_payload(self):
        observed_at = datetime(2026, 8, 12, 8, 51, 25, tzinfo=timezone.utc)
        signal_id = self.q.push_signal(
            "btcidr", "BUY", 0.75, 1_000_000,
            data={"signal": {"recommendation": "BUY", "observed_at": observed_at}},
            priority=5,
        )
        self.assertIsNotNone(signal_id)
        self.assertEqual(len(self.q._redis.z), 1)
        envelope = json.loads(next(iter(self.q._redis.z)))
        self.assertEqual(envelope["data"]["signal"]["observed_at"], str(observed_at))
