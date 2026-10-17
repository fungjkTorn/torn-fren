import bisect
import unittest

import numpy as np

from deploy.scripts import v163_readonly_event_first_preview as model
from research.direct_arrival_occupancy import DirectArrivalOccupancy as Direct
from research.true_zero_cycles import ZeroCycles

T=1790985600


class DirectTests(unittest.TestCase):
    def fixture(self,cutoff,change_after=None):
        return [model.OBS(t,0 if change_after is not None and t>change_after else q,'a')
                for start in range(T,cutoff+1,2400)
                for offset,q in ((0,0),(600,200),(1200,20),(1800,0))
                if (t:=start+offset)<=cutoff]

    def tracker(self,rows,issued):
        z=ZeroCycles(lambda a,b:False)
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
        return Direct(rows,list(range(T,cutoff+1,30)),lambda a,b:False,
            cutoff=cutoff,flight_seconds=100,score=score)

    def test_future_mutation_prefix_and_cold_start_independence(self):
        issued=T+5*86400;cutoff=issued+86400;rows=self.fixture(cutoff)
        z=self.tracker(rows,issued);p=self.build(rows,cutoff)
        expected=p.plans(issued,z,poll_age=0)
        self.assertIsNotNone(expected['direct70']['departure_epoch'])
        self.assertGreater(expected['direct70']['uncalibrated_arrival_score'],.7)
        self.assertLessEqual(p.training['latest_training_truth_maturity'],issued)
        self.assertEqual(self.build(self.fixture(cutoff,issued),cutoff).plans(issued,z,poll_age=0),expected)
        self.assertEqual(self.build(self.fixture(issued),issued).plans(issued,z,poll_age=0),expected)
        # Querying earlier replay windows cannot warm up or change later fits.
        q=self.build(rows,cutoff)
        q.plans(issued-86400,self.tracker(rows,issued-86400),poll_age=0)
        self.assertEqual(q.plans(issued,z,poll_age=0),expected)
        self.assertLess(p.training['oldest_training_origin'],issued-86400)

    def test_guards_unknowns_exact_zero_and_individual_label_maturity(self):
        issued=T+5*86400;rows=self.fixture(issued)
        z=self.tracker(rows,issued);p=self.build(rows,issued)
        self.assertTrue(all(x['departure_epoch'] is None for x in p.plans(issued,z,poll_age=181).values()))
        unknown=self.build(rows,issued,True)
        self.assertTrue(all(x['departure_epoch'] is None for x in unknown.plans(issued,z,poll_age=0).values()))
        p.plans(issued,z,poll_age=0)
        self.assertTrue(np.all(p.maturity[p.maturity<=p.fit_epoch]<=p.fit_epoch))
        # Recent origins with short mature leads are eligible without waiting
        # for their full eight-hour future path to finish.
        self.assertGreater(p.origin[p.maturity<=p.fit_epoch].max(),p.fit_epoch-28800)
        residual=issued+1200;z=self.tracker(self.fixture(residual),residual)
        self.assertEqual(z.last.quantity,20)
        self.assertEqual(Direct.state(z,residual)[0],1)
        with self.assertRaises(ValueError):p.plans(issued,z,poll_age=0)


if __name__=='__main__':unittest.main()
