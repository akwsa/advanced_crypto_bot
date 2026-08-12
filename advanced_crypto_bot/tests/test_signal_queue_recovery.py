import json
import unittest
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


class TestQueueRecovery(unittest.TestCase):
    def setUp(self):
        self.q=SignalQueue.__new__(SignalQueue); self.q._connected=True
        self.q._redis=FakeRedis(); self.q.queue_name='q'; self.q.inflight_name='i'

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
