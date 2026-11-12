import unittest
from research.japan_xanax.renewal_shadow import History,Cycle


class CommonRandomTests(unittest.TestCase):
    def history(self):
        t=1792200000;h=History(lambda a,b:False)
        for i in range(40):
            zero=t-40*5000+i*5000;restock=zero+1200+(i%9)*120
            h.cycles.append(Cycle(zero,restock,restock+600+(i%3)*60,300+(i%4)*60,100))
        h.last=(t-500,0,'a');h.phase_start=t-500
        return h,t

    def test_unchanged_phase_has_consistent_overlapping_absolute_support(self):
        h,t=self.history();a={};b={}
        h.plans(t,poll_age=0,diagnostics=a,stable_scenarios=True)
        h.plans(t+60,poll_age=0,diagnostics=b,stable_scenarios=True)
        self.assertEqual(set(a),set(b))
        for family in a:self.assertEqual(a[family]['support'][1:],b[family]['support'][:-1])

    def test_default_unchanged_deterministic_and_current_evidence_still_required(self):
        h,t=self.history()
        self.assertEqual(h.plans(t,poll_age=0),h.plans(t,poll_age=0,stable_scenarios=False))
        a=h.plans(t,poll_age=0,stable_scenarios=True)
        self.assertEqual(a,h.plans(t,poll_age=0,stable_scenarios=True))
        self.assertTrue(all(p['departure'] is None for p in h.plans(t,poll_age=181,stable_scenarios=True).values()))
        h.phase_start=None
        self.assertIsNone(h.plans(t,poll_age=0,stable_scenarios=True)['sequence_blocks_peak']['departure'])


if __name__=='__main__':unittest.main()
