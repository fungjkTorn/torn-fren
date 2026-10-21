import unittest
import numpy as np
from research.japan_xanax import exact_renewal as m
from research.japan_xanax.renewal_shadow import Cycle, History


def brute(cycles, horizon):
    """Independent path enumeration oracle, tiny horizon only."""
    weights=m.weights_for(cycles);result=np.zeros(horizon+1)
    def visit(zero,mass):
        for c,w in zip(cycles,weights):
            p=mass*w;start=zero+c.restock-c.zero;end=start+c.available-m.GRACE
            if start < end and start <= horizon:
                result[start:min(end,horizon+1)]+=p
            following=zero+c.end-c.zero
            if following <= horizon:visit(following,p)
    visit(0,1.)
    return result


class ExactRenewalTests(unittest.TestCase):
    def test_matches_exhaustive_paths_with_joint_cycle_durations(self):
        cycles=(Cycle(0,31,107,37,100),Cycle(107,160,246,22,200))
        actual=m.renewal_occupancy(cycles,500)
        np.testing.assert_allclose(actual,brute(cycles,500),atol=1e-12)
        self.assertGreaterEqual(actual.min(),0);self.assertLessEqual(actual.max(),1)
        self.assertFalse(actual.flags.writeable)

    def test_exact_boundary_and_noninteger_grid_offsets(self):
        c=Cycle(0,31,107,37,100)
        values=m.renewal_occupancy((c,),400)
        self.assertAlmostEqual(values[30],0)
        self.assertAlmostEqual(values[31],1)
        self.assertAlmostEqual(values[57],1)
        self.assertAlmostEqual(values[58],0)  # arrival+10 equals buy-end
        self.assertAlmostEqual(values[138],1)
        self.assertAlmostEqual(values[137],0)

    def history(self,high=False):
        h=History(lambda a,b:False)
        h.cycles=[Cycle(i*600,i*600+300,(i+1)*600,120,100) for i in range(16)]
        h.phase_start=10000;h.last=(10000,100 if high else 0,'a')
        return h

    def test_current_phase_conditioning_and_future_exclusion(self):
        for high in (False,True):
            h=self.history(high)
            values,status=m.curve(h,10000,0)
            self.assertEqual(status,'SHADOW_ESTIMATE')
            self.assertEqual(values['latest_training_cycle_end'],9600)
            for delay,s in zip(values['delays'],values['support']):
                offset=m.FLIGHT+delay+(300 if high else 0)
                expected=float(300 <= offset%600 < 410)
                self.assertAlmostEqual(s,expected,places=10)
            h.cycles.append(Cycle(10001,10200,10600,100,100))
            self.assertEqual(m.curve(h,10000,0)[0],values)

    def test_fails_closed_without_phase_freshness_or_survivors(self):
        h=self.history();self.assertIsNone(m.curve(h,10000,181)[0])
        h.phase_start=None
        self.assertEqual(m.curve(h,10000,0)[1],'UNKNOWN_CURRENT_PHASE')
        h.phase_start=9000
        self.assertEqual(m.curve(h,10000,0)[1],'INSUFFICIENT_PHASE_SURVIVORS')
        h.last=(10001,0,'a')
        with self.assertRaises(ValueError):m.curve(h,10000,0)

    def test_selector_is_earliest_supported_and_has_no_target_retention(self):
        values=dict(delays=[0,60,120],support=[.3,.6,.8])
        self.assertEqual(m.choose(values,10000,'60'),10060)
        self.assertEqual(m.choose(values,10000,'peak'),10120)
        self.assertIsNone(m.choose(None,10000,'peak'))

    def test_invalid_zero_cycles_rejected(self):
        for c in (Cycle(0,0,100,10,100),Cycle(0,20,100,100,100)):
            with self.assertRaises(ValueError):m.renewal_occupancy((c,),200)


if __name__=='__main__':unittest.main()
