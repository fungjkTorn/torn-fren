from collections import Counter
import unittest
from deploy.scripts import v163_readonly_event_first_preview as model
from research.depletion_timing_audit import observed_depletions,predicted_depletions,observed_availability_losses,predicted_availability_losses,observed_restocks,count_events


class DepletionTests(unittest.TestCase):
    def test_threshold_not_zero_and_provider_or_gap_crossings_rejected(self):
        rows=[model.OBS(100,80,'a'),model.OBS(120,20,'a'),model.OBS(140,80,'a'),
              model.OBS(160,0,'b'),model.OBS(180,80,'b'),model.OBS(200,0,'b')]
        self.assertEqual(observed_availability_losses(rows,lambda a,b: a<=190<=b),[120])
        self.assertEqual(observed_depletions(rows,lambda a,b: a<=190<=b),[])

    def test_current_and_future_windows_include_only_target_cohort(self):
        w=lambda t:{'predicted_stock_below_30_epoch':t}
        stream={'current_stock_window':w(120),'restock_events':[w(120),w(170),w(250)]}
        self.assertEqual(predicted_availability_losses(stream,start=100,end=200),[120,170])
        self.assertEqual(predicted_depletions(stream,start=100,end=200),[])
        self.assertEqual(predicted_availability_losses(stream,start=120,end=170),[170])

    def test_zero_clock_is_separate_from_low_stock_and_repeated_zero(self):
        rows=[model.OBS(t,q,'a') for t,q in [(100,100),(120,20),(180,1),(220,0),(240,0),(300,10),(350,100)]]
        self.assertEqual(observed_availability_losses(rows,lambda a,b:False),[120])
        self.assertEqual(observed_depletions(rows,lambda a,b:False),[220])
        self.assertEqual(observed_restocks(rows,lambda a,b:False),[300])
        stream={'true_depletion_events':[{'predicted_true_depletion_epoch':220}],
                'restock_events':[{'predicted_stock_below_30_epoch':120}]}
        self.assertEqual(predicted_depletions(stream,start=100,end=250),[220])

    def test_matching_is_one_to_one_with_recall_and_precision_denominators(self):
        c=Counter();count_events(c,[1000,1010,2000],[1005])
        self.assertEqual(c['matched_60s'],1)
        self.assertEqual(c['observed'],1);self.assertEqual(c['forecast'],3)


if __name__=='__main__':unittest.main()
