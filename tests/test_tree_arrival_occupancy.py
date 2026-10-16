import bisect
import unittest
import numpy as np
from research.tree_arrival_occupancy import TreeArrivalOccupancy as M,HistogramLogitTrees
from research.quantity_rate_cycles import QuantityRateCycles
from research.true_zero_cycles import model
import test_direct_arrival_occupancy as fixture

T=fixture.T


class TreeTests(unittest.TestCase):
    def tracker(self,rows,issued):
        z=QuantityRateCycles(lambda a,b:False)
        for r in rows:
            if r.epoch<=issued:z.add(r)
        return z

    def build(self,rows,cutoff,unknown=False):
        times=[r.epoch for r in rows]
        def score(arrival):
            self.assertLessEqual(arrival+190,cutoff)
            if unknown:return 'UNKNOWN','fixture',None
            j=bisect.bisect_right(times,arrival+10)-1
            return ('SUCCESS' if j>=0 and rows[j].quantity>=30 else 'FAILURE'),'fixture',None
        return M(rows,list(range(T,cutoff+1,30)),lambda a,b:False,cutoff=cutoff,flight_seconds=100,score=score)

    def test_small_fixed_trees_learn_nonlinear_regions_deterministically(self):
        a,b=np.meshgrid(np.linspace(0,1,24),np.linspace(0,1,24))
        x=np.column_stack((a.ravel(),b.ravel()));y=((x[:,0]<.25)|((x[:,0]>.75)&(x[:,1]>.5))).astype(float)
        p=HistogramLogitTrees().fit(x,y,np.ones(len(y))).predict(x)
        self.assertGreater(np.mean((p>=.5)==y),.95)
        np.testing.assert_array_equal(p,HistogramLogitTrees().fit(x,y,np.ones(len(y))).predict(x))
        self.assertTrue(np.all((p>0)&(p<1)))

    def test_future_mutation_prefix_canonical_refit_and_label_maturity(self):
        issued=T+5*86400;cutoff=issued+86400;rows=fixture.DirectTests().fixture(cutoff);z=self.tracker(rows,issued)
        m=self.build(rows,cutoff);expected=m.plans(issued,z,poll_age=0)
        self.assertTrue(any(r['departure_epoch'] is not None for r in expected.values()))
        for family in m.fits:
            self.assertLessEqual(m.training[family]['latest_training_truth_maturity'],m.fit_epoch)
            self.assertLess(m.training[family]['oldest_training_origin'],issued-86400)
        self.assertEqual(self.build(fixture.DirectTests().fixture(cutoff,issued),cutoff).plans(issued,z,poll_age=0),expected)
        self.assertEqual(self.build(fixture.DirectTests().fixture(issued),issued).plans(issued,z,poll_age=0),expected)
        q=self.build(rows,cutoff);q.plans(issued-86400,self.tracker(rows,issued-86400),poll_age=0)
        self.assertEqual(q.plans(issued,z,poll_age=0),expected)
        poisoned=self.build(rows,cutoff);poisoned.x[poisoned.maturity>issued]+=1000
        self.assertEqual(poisoned.plans(issued,z,poll_age=0),expected)

    def test_no_unknown_labels_stale_polls_or_false_depletion(self):
        issued=T+5*86400;rows=fixture.DirectTests().fixture(issued);z=self.tracker(rows,issued)
        for m,age in ((self.build(rows,issued),181),(self.build(rows,issued,True),0)):
            self.assertTrue(all(r['departure_epoch'] is None for r in m.plans(issued,z,poll_age=age).values()))
        residual=issued+1200;rows=fixture.DirectTests().fixture(residual);z=self.tracker(rows,residual)
        self.assertEqual(z.last.quantity,20);self.assertEqual(M.state(z,residual)[0][0],1)
        m=self.build(rows,residual)
        with self.assertRaises(ValueError):m.plans(issued,z,poll_age=0)
        for p in m.plans(residual,z,poll_age=0).values():
            if 'model_name' not in p:continue
            self.assertEqual(p['depletion_stock_quantity'],0);self.assertFalse(p['event_timing_prediction_supported'])
            self.assertIsNone(p['calibrated_success_probability'])


if __name__=='__main__':unittest.main()
