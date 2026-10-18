import unittest
from research.execution_offset_study import ExecutionCalibration,bounded_departure,OFFSETS


class CalibrationTests(unittest.TestCase):
    def test_delayed_labels_and_bucket_deduplication(self):
        c=ExecutionCalibration(600);calls=[]
        def score(arrival):
            calls.append(arrival);return 'SUCCESS','TEST',dict(post_poll=arrival+10)
        c.advance(1000,score);c.observe(1000,{0:1015},'ZERO',0)
        c.advance(1001,score);c.observe(1001,{0:1016},'ZERO',0)
        self.assertEqual(len(c.pending),1)
        c.advance(1804,score);self.assertFalse(calls)
        c.advance(1805,score);self.assertEqual(calls,[1615])
        self.assertEqual(list(c.history[('ZERO',0)]),[(1805,1)])

    def test_future_poll_blocks_training(self):
        c=ExecutionCalibration(600);c.advance(1000,lambda a:None);c.observe(1000,{0:1015},'ZERO',0)
        with self.assertRaises(ValueError):c.advance(1805,lambda a:('SUCCESS','TEST',dict(post_poll=1900)))
        self.assertFalse(c.history[('ZERO',0)])

    def test_only_executable_fresh_plans_enter_training(self):
        c=ExecutionCalibration(600);c.advance(1000,lambda a:None)
        c.observe(1000,{-300:1315,0:1150},'ZERO',60)
        self.assertFalse(c.pending) # outside next issue / source expires
        c.observe(1000,{0:1015},'ZERO',0);self.assertEqual(len(c.pending),1)

    def test_phase_specific_selection_and_conservative_gate(self):
        c=ExecutionCalibration(600);now=100000
        for o in OFFSETS:
            c.history[('ZERO',o)].extend((now-i*300,1 if o==-600 else 0) for i in range(12))
        choices={o:now+15 if o<=0 else now+o for o in OFFSETS}
        self.assertEqual(c.choose(now,choices,'ZERO',gated=True),(now+15,-600))
        self.assertEqual(c.choose(now,choices,'POSITIVE',gated=True),(None,None))
        self.assertEqual(c.choose(now,choices,'POSITIVE',gated=False),(now+15,0))

    def test_unknown_does_not_become_success_or_failure(self):
        c=ExecutionCalibration(600);c.advance(1000,lambda a:None);c.observe(1000,{0:1015},'ZERO',0)
        c.advance(1805,lambda a:('UNKNOWN','GAP',None))
        self.assertFalse(c.history[('ZERO',0)]);self.assertEqual(c.counts['matured_UNKNOWN'],1)

    def test_bounds_and_publication_floor(self):
        self.assertEqual(bounded_departure(1000,1010,-1200),1015)
        self.assertIsNone(bounded_departure(1000,1000+28800,300))
        self.assertIsNone(bounded_departure(1000,None,-300))
