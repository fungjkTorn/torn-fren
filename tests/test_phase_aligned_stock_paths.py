import bisect
import unittest

from research.phase_aligned_stock_paths import PhaseAlignedStockPaths
from research.true_zero_cycles import ZeroCycles,model

T=1791000000


class AlignedTests(unittest.TestCase):
    def rows(self,cutoff,change_after=None):
        rows=[]
        for start in range(T,cutoff+1,9000):
            for offset,q in ((0,200),(480,20),(600,0)):
                t=start+offset
                if t<=cutoff:rows.append(model.OBS(t,0 if change_after is not None and t>change_after else q,'a'))
        return rows

    def build(self,rows,cutoff,unknown=False,crosses=lambda a,b:False):
        times=[r.epoch for r in rows]
        def interval(a,b):
            self.assertLessEqual(b+190,cutoff)
            if unknown or crosses(a,b):return -1
            i=bisect.bisect_right(times,a)-1;j=bisect.bisect_right(times,b)-1
            segment=rows[i:j+1]
            phases={r.quantity>=30 for r in segment}
            return int(phases.pop()) if i>=0 and len(phases)==1 else -1
        return PhaseAlignedStockPaths(rows,crosses,cutoff=cutoff,flight_seconds=17940,interval_score=interval)

    def tracker(self,rows,issued,crosses=lambda a,b:False):
        z=ZeroCycles(crosses)
        for r in rows:
            if r.epoch<=issued:z.add(r)
        return z

    def test_narrow_windows_after_multiple_cycles_at_exact_phase_age(self):
        cutoff=T+6*86400;issued=T+45*9000+2603
        rows=self.rows(cutoff);z=self.tracker(rows,issued)
        paths=self.build(rows,cutoff);plans=paths.plans(issued,z,poll_age=0)
        for p in plans.values():
            self.assertIsNotNone(p['departure_epoch'])
            self.assertLessEqual(p['latest_training_path_end'],issued)
            self.assertEqual(p['physical_phase_age_seconds'],2003)
            self.assertLess((p['departure_epoch']+17940-T)%9000,480)
            self.assertIsNone(p['calibrated_success_probability'])
            self.assertFalse(p['event_timing_prediction_supported'])

    def test_residual_positive_is_not_a_zero_anchor(self):
        cutoff=T+6*86400;rows=self.rows(cutoff)
        issued=T+45*9000+500
        z=self.tracker(rows,issued);f=PhaseAlignedStockPaths.features(z,issued)
        self.assertEqual(f[0],1)
        self.assertEqual(f[1],T+45*9000)
        paths=self.build(rows,cutoff)
        self.assertNotIn(T+45*9000+480,paths.anchors)

    def test_future_truth_mutations_and_shorter_snapshot_preserve_plans(self):
        cutoff=T+6*86400;issued=T+45*9000+2603
        rows=self.rows(cutoff);z=self.tracker(rows,issued)
        expected=self.build(rows,cutoff).plans(issued,z,poll_age=0)
        changed=self.rows(cutoff,change_after=issued)
        self.assertEqual(self.build(changed,cutoff).plans(issued,z,poll_age=0),expected)
        self.assertEqual(self.build(self.rows(issued),issued).plans(issued,z,poll_age=0),expected)
        with self.assertRaises(ValueError):
            self.build(rows,cutoff).plans(issued,self.tracker(rows,issued+9000),poll_age=0)

    def test_unknown_stale_and_unmatured_history_abstain(self):
        cutoff=T+6*86400;rows=self.rows(cutoff);z=self.tracker(rows,cutoff)
        unknown=self.build(rows,cutoff,unknown=True)
        self.assertTrue(all(p['departure_epoch'] is None for p in unknown.plans(cutoff,z,poll_age=0).values()))
        paths=self.build(rows,cutoff)
        self.assertTrue(all(p['departure_epoch'] is None for p in paths.plans(cutoff,z,poll_age=181).values()))
        early=T+4*9000+2603
        self.assertTrue(all(p['departure_epoch'] is None for p in paths.plans(early,self.tracker(rows,early),poll_age=0).values()))

    def test_provider_crossing_does_not_create_physical_anchor(self):
        cutoff=T+6*86400;rows=self.rows(cutoff)
        crossing=T+45*9000+600
        changed=[model.OBS(r.epoch,r.quantity,'b' if r.epoch>=crossing else 'a') for r in rows]
        self.assertNotIn(crossing,self.build(changed,cutoff).anchors)


if __name__=='__main__':unittest.main()
