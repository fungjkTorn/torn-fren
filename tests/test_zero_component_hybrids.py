import unittest

from deploy.scripts import v163_readonly_event_first_preview as model
from research.zero_component_hybrids import ComponentHybrid

T=1791000000


class HybridTests(unittest.TestCase):
    def train(self,mode):
        z=ComponentHybrid(lambda a,b:False,mode)
        z.add(model.OBS(T,0,'a'))
        for i in range(10):
            start=T+100+i*400
            for dt,q in ((0,300),(100,200),(200,100),(250,20),(300,0)):
                z.add(model.OBS(start+dt,q,'a'))
        return z,T+4100

    def test_hybrids_keep_empirical_buying_window_and_separate_rate_current(self):
        for mode in ComponentHybrid.MODES:
            z,start=self.train(mode)
            z.add(model.OBS(start,600,'a'));z.add(model.OBS(start+100,500,'a'))
            f=z.forecast('mex:Jaguar Plushie',asof=start+100)
            w=f['current_stock_window']
            self.assertEqual(w['predicted_stock_below_30_epoch'],start+250)
            self.assertEqual(w['predicted_true_depletion_epoch'],start+(300 if mode=='recent64' else 600))
            state=z._physical_state(start+100)
            self.assertEqual(state.get('future_stocked_durations',state['stocked_durations']),[300]*10)
            self.assertFalse(f['legacy_threshold_phase_clock_used'])

    def test_residual_stock_never_anchors_empty_wait(self):
        for mode in ComponentHybrid.MODES:
            z,start=self.train(mode)
            z.add(model.OBS(start,300,'a'));z.add(model.OBS(start+250,20,'a'))
            f=z.forecast('mex:Jaguar Plushie',asof=start+250)
            self.assertIsNone(f['current_stock_window'])
            self.assertIsNone(f['observed_zero_epoch'])


if __name__=='__main__':unittest.main()
