import unittest
from deploy.scripts import v163_readonly_event_first_preview as model
from research.true_zero_cycles import ZeroCycles
from services.travel_window_policy import project_policy

T=1791000000


class ZeroClockTests(unittest.TestCase):
    def tracker(self):
        tracker=ZeroCycles(lambda a,b:False)
        # Available for100s, residual stock for100s, physically empty100s.
        tracker.add(model.OBS(T,0,'a'))
        for i in range(10):
            for offset,q in ((100,200),(200,20),(250,1),(300,0)):
                tracker.add(model.OBS(T+i*300+offset,q,'a'))
        return tracker

    def test_below30_does_not_start_timer_and_true_zero_does(self):
        z=self.tracker();s=T+3000
        z.add(model.OBS(s+100,200,'a'))
        z.add(model.OBS(s+200,20,'a'))
        f=z.forecast('mex:Jaguar Plushie',asof=s+220)
        self.assertIsNone(f['observed_zero_epoch'])
        self.assertEqual(f['current_phase'],'HIGH')
        self.assertIsNone(f['current_stock_window'])
        self.assertEqual(f['restock_events'][0]['predicted_restock_epoch'],s+400)
        z.add(model.OBS(s+250,1,'a'))
        tiny=z.forecast('mex:Jaguar Plushie',asof=s+270)
        self.assertIsNone(tiny['observed_zero_epoch'])
        self.assertIsNone(tiny['current_stock_window'])
        z.add(model.OBS(s+300,0,'a'))
        f=z.forecast('mex:Jaguar Plushie',asof=s+320)
        self.assertEqual(f['observed_zero_epoch'],s+300)
        self.assertEqual(f['observed_zero_onset_bracket'],{'after_epoch':s+250,'by_epoch':s+300})
        self.assertEqual(f['restock_events'][0]['predicted_restock_epoch'],s+400)

    def test_zero_and_availability_end_are_distinct_clocks(self):
        z=self.tracker();s=T+3000
        z.add(model.OBS(s+100,200,'a'))
        f=z.forecast('mex:Jaguar Plushie',asof=s+120)
        self.assertEqual(f['current_stock_window']['predicted_stock_below_30_epoch'],s+200)
        self.assertEqual(f['current_stock_window']['predicted_true_depletion_epoch'],s+300)
        e=f['restock_events'][0]
        self.assertEqual(e['predicted_stock_below_30_epoch'],s+500)
        self.assertEqual(e['predicted_true_depletion_epoch'],s+600)
        self.assertFalse(f['legacy_threshold_phase_clock_used'])
        decision=project_policy(f,now=s+120,poll_age_seconds=0)
        self.assertEqual(decision['depletion_stock_quantity'],0)
        self.assertEqual(decision['forecast_events'][0]['predicted_true_depletion_epoch'],s+600)
        with self.assertRaises(ValueError):z.forecast('mex:Jaguar Plushie',asof=s)

    def test_provider_crossing_or_gap_cannot_invent_zero_anchor(self):
        z=ZeroCycles(lambda a,b:a<=T+150<=b)
        z.add(model.OBS(T,100,'a'));z.add(model.OBS(T+100,20,'a'))
        z.add(model.OBS(T+200,0,'a'))
        self.assertIsNone(z.forecast('mex:Jaguar Plushie',asof=T+220)['observed_zero_epoch'])
        z=ZeroCycles(lambda a,b:False)
        z.add(model.OBS(T,100,'a'));z.add(model.OBS(T+100,0,'b'))
        self.assertIsNone(z.forecast('mex:Jaguar Plushie',asof=T+120)['observed_zero_epoch'])


if __name__=='__main__':unittest.main()
