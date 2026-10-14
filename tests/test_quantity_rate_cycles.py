import copy
import unittest

from deploy.scripts import v163_readonly_event_first_preview as model
from research.quantity_rate_cycles import QuantityRateCycles
from research.departure_reconfirmation import compare

T=1791000000
KEY='mex:Jaguar Plushie'


class QuantityRateTests(unittest.TestCase):
    def trained(self):
        z=QuantityRateCycles(lambda a,b:False)
        z.add(model.OBS(T,0,'a'))
        for i in range(70):
            start=T+100+i*400
            for dt,q in ((0,300),(100,200),(200,100),(280,20),(300,0)):
                z.add(model.OBS(start+dt,q,'a'))
        return z,T+100+70*400

    def test_completed_rates_bounded_and_current_quantity_controls_zero(self):
        z,start=self.trained()
        self.assertEqual(len(z.rates),64)
        self.assertEqual(set(z.rates),{1.})
        z.add(model.OBS(start,600,'a'))
        z.add(model.OBS(start+100,500,'a'))
        f=z.forecast(KEY,asof=start+100)
        self.assertEqual(f['current_stock_window']['predicted_true_depletion_epoch'],start+600)
        self.assertEqual(f['current_stock_window']['predicted_stock_below_30_epoch'],start+571)
        # Current batch is unfinished: no training sample from its future zero.
        self.assertEqual(set(z.rates),{1.})
        self.assertEqual(f['true_restock_events'][0]['predicted_restock_epoch'],start+700)
        # Future batch lifetime uses completed rates/typical batch, not current residual.
        e=f['true_restock_events'][0]
        self.assertEqual(e['predicted_true_depletion_epoch']-e['predicted_restock_epoch'],300)

    def test_recent_drops_adjust_rate_but_below30_never_starts_zero_clock(self):
        z,start=self.trained()
        for dt,q in ((0,600),(60,480),(120,360),(180,240),(240,20)):
            z.add(model.OBS(start+dt,q,'a'))
        f=z.forecast(KEY,asof=start+240)
        self.assertIsNone(f['observed_zero_epoch'])
        self.assertIsNone(f['current_stock_window'])
        self.assertLess(f['true_depletion_events'][0]['predicted_true_depletion_epoch'],start+260)
        z.add(model.OBS(start+260,0,'a'))
        self.assertEqual(z.forecast(KEY,asof=start+260)['observed_zero_epoch'],start+260)

    def test_future_data_cannot_rewrite_frozen_forecast(self):
        z,start=self.trained();z.add(model.OBS(start,600,'a'))
        frozen=copy.deepcopy(z.forecast(KEY,asof=start))
        other=copy.deepcopy(z)
        other.add(model.OBS(start+100,0,'a'))
        self.assertEqual(z.forecast(KEY,asof=start),frozen)
        with self.assertRaises(ValueError):other.forecast(KEY,asof=start)

    def test_topups_provider_changes_and_gaps_exclude_rate_training(self):
        for mode in ('topup','provider','gap'):
            z=QuantityRateCycles(lambda a,b:mode=='gap' and a<T+150<=b)
            for dt,q,src in ((0,0,'a'),(100,300,'a'),(200,400 if mode=='topup' else 100,'b' if mode=='provider' else 'a'),(300,0,'b' if mode=='provider' else 'a')):
                z.add(model.OBS(T+dt,q,src))
            self.assertEqual(len(z.rates),0,mode)

    def test_replanning_comparison_keeps_unknown_and_abstention_pairs(self):
        base=[(1000,1000,0)];challenger=[(1000,None,0)]
        r=compare(base,challenger,cutoff=40000,flight_seconds=100,
                  score=lambda t:('UNKNOWN','fixture',None))
        self.assertEqual(r['UNKNOWN__ABSTAIN'],1)
        self.assertEqual(r.get('matched_resolved',0),0)
        with self.assertRaises(ValueError):
            compare(base,[(1300,None,0)],cutoff=40000,flight_seconds=100,
                    score=lambda t:('SUCCESS','fixture',None))


if __name__=='__main__':unittest.main()
