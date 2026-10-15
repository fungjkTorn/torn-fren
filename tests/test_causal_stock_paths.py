import unittest

from deploy.scripts import v163_readonly_event_first_preview as model
from research.true_zero_cycles import ZeroCycles
from research.causal_stock_paths import CausalStockPaths

T=1791000000


class PathTests(unittest.TestCase):
    def fixture(self,cutoff,*,change_after=None):
        rows=[]
        for start in range(T,cutoff+1,1800):
            for offset,q in ((0,0),(600,200),(1200,20),(1500,0)):
                t=start+offset
                if t<=cutoff:
                    rows.append(model.OBS(t,0 if change_after is not None and t>change_after else q,'a'))
        return rows

    def build(self,rows,cutoff,unknown=False):
        import bisect
        times=[o.epoch for o in rows]
        def score(arrival):
            self.assertLessEqual(arrival+190,cutoff)
            if unknown:return 'UNKNOWN','fixture',None
            i=bisect.bisect_right(times,arrival+10)-1
            return ('SUCCESS' if i>=0 and rows[i].quantity>=30 else 'FAILURE'),'fixture',None
        return CausalStockPaths(rows,list(range(T,cutoff+1,30)),lambda a,b:False,
                               cutoff=cutoff,flight_seconds=100,score=score)

    def tracker(self,rows,issued):
        z=ZeroCycles(lambda a,b:False)
        for r in rows:
            if r.epoch<=issued:z.add(r)
        return z

    def test_complete_paths_mature_before_issue_and_zero_not_below30(self):
        cutoff=T+5*86400;issued=T+4*86400
        rows=self.fixture(cutoff);planner=self.build(rows,cutoff)
        plans=planner.plans(issued,self.tracker(rows,issued),poll_age=0)
        for p in plans.values():
            self.assertIsNotNone(p['departure_epoch'])
            self.assertLessEqual(p['latest_training_path_end'],issued)
            self.assertIsNone(p['calibrated_success_probability'])
            self.assertFalse(p['event_timing_prediction_supported'])
        residual=issued+1200
        tracker=self.tracker(rows,residual)
        self.assertEqual(planner.features(tracker,residual)[0],1)
        self.assertIsNone(tracker.forecast('mex:Jaguar Plushie',asof=residual)['observed_zero_epoch'])

    def test_future_mutation_and_shorter_cutoff_do_not_change_earlier_plan(self):
        cutoff=T+5*86400;issued=T+4*86400
        rows=self.fixture(cutoff);z=self.tracker(rows,issued)
        expected=self.build(rows,cutoff).plans(issued,z,poll_age=0)
        altered=self.fixture(cutoff,change_after=issued)
        self.assertEqual(self.build(altered,cutoff).plans(issued,z,poll_age=0),expected)
        prefix=self.fixture(issued)
        self.assertEqual(self.build(prefix,issued).plans(issued,z,poll_age=0),expected)
        future=self.tracker(rows,issued+600)
        with self.assertRaises(ValueError):self.build(rows,cutoff).plans(issued,future,poll_age=0)

    def test_unknown_paths_and_stale_queries_never_invent_support(self):
        cutoff=T+5*86400;rows=self.fixture(cutoff);z=self.tracker(rows,cutoff)
        planner=self.build(rows,cutoff,unknown=True)
        self.assertTrue(all(p['departure_epoch'] is None for p in planner.plans(cutoff,z,poll_age=0).values()))
        self.assertTrue(all(p['departure_epoch'] is None for p in planner.plans(cutoff,z,poll_age=181).values()))


if __name__=='__main__':unittest.main()
