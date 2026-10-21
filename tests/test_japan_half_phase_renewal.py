import unittest
import numpy as np
from research.japan_xanax import half_phase_renewal as m
from research.japan_xanax.renewal_shadow import History
from research.japan_xanax.training_audit import HalfPhases


def enumerate_paths(low,high,half_life,horizon,positive=False):
    wl=m.weights(low,half_life);wh=m.weights(high,half_life);result=np.zeros(horizon+1)
    def high_start(t,mass):
        for phase,w in zip(high,wh):
            end=t+phase[2]-m.GRACE
            if t<end and t<=horizon:result[t:min(end,horizon+1)]+=mass*w
            following=t+phase[1]
            if following<=horizon:zero_start(following,mass*w)
    def zero_start(t,mass):
        for phase,w in zip(low,wl):
            following=t+phase[1]
            if following<=horizon:high_start(following,mass*w)
    (high_start if positive else zero_start)(0,1.)
    return result


class HalfRenewalTests(unittest.TestCase):
    def test_both_phase_kernels_match_independent_exhaustive_path_enumeration(self):
        low=((100,37),(200,73));high=((100,57,25),(200,91,40))
        zero,positive=m.occupancy(low,high,21600,400)
        np.testing.assert_allclose(zero,enumerate_paths(low,high,21600,400),atol=1e-12)
        np.testing.assert_allclose(positive,enumerate_paths(low,high,21600,400,True),atol=1e-12)
        self.assertFalse(zero.flags.writeable);self.assertFalse(positive.flags.writeable)

    def test_arrival_plus_ten_equality_is_not_accepted(self):
        zero,positive=m.occupancy(((100,37),),((200,57,25),),21600,400)
        self.assertAlmostEqual(positive[14],1);self.assertAlmostEqual(positive[15],0)
        self.assertAlmostEqual(zero[37],1);self.assertAlmostEqual(zero[51],1);self.assertAlmostEqual(zero[52],0)

    def histories(self,high=False):
        h=History(lambda a,b:False);p=HalfPhases(lambda a,b:False)
        h.phase_start=10000;h.last=(10000,100 if high else 0,'a')
        p.low=[dict(end=600*i+300,duration=300) for i in range(16)]
        p.high=[dict(end=600*i+600,duration=300,available=120) for i in range(16)]
        return h,p

    def test_current_phase_and_age_conditioning_match_known_periodic_path(self):
        for high in (False,True):
            h,p=self.histories(high)
            values,status=m.curve(h,p,10000,0,21600)
            self.assertEqual(status,'SHADOW_ESTIMATE')
            for d,s in zip(values['delays'],values['support']):
                offset=m.FLIGHT+d+(300 if high else 0)
                self.assertAlmostEqual(s,float(300<=offset%600<410),places=10)
            h.phase_start=9970
            values,status=m.curve(h,p,10000,0,21600)
            for d,s in zip(values['delays'],values['support']):
                offset=m.FLIGHT+d+30+(300 if high else 0)
                self.assertAlmostEqual(s,float(300<=offset%600<410),places=10)

    def test_future_completions_excluded_and_unknown_phase_is_not_synthesized(self):
        h,p=self.histories();before=m.curve(h,p,10000,0,21600)
        p.low.append(dict(end=11000,duration=9000));p.high.append(dict(end=11000,duration=9000,available=8000))
        self.assertEqual(before,m.curve(h,p,10000,0,21600))
        h.phase_start=None
        self.assertEqual(m.curve(h,p,10000,0,21600)[1],'UNKNOWN_CURRENT_PHASE')
        self.assertIsNone(m.curve(h,p,10000,181,21600)[0])

    def test_low_quantity_does_not_extend_current_buying_window(self):
        h,p=self.histories(True);h.last=(10000,29,'a')
        # Large flight horizon masks the current spell; use a long completed
        # high interval to expose the current quantity guard directly.
        p.high=[dict(end=600*i+600,duration=20000,available=18000) for i in range(16)]
        values,status=m.curve(h,p,10000,0,21600)
        self.assertEqual(status,'SHADOW_ESTIMATE')
        self.assertAlmostEqual(values['support'][0],0)


if __name__=='__main__':unittest.main()
