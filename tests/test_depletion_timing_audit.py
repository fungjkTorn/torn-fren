from collections import Counter
import unittest
from deploy.scripts import v163_readonly_event_first_preview as model
from research.depletion_timing_audit import observed_depletions,predicted_depletions,count_events


class DepletionTests(unittest.TestCase):
    def test_threshold_not_zero_and_provider_or_gap_crossings_rejected(self):
        rows=[model.OBS(100,80,'a'),model.OBS(120,20,'a'),model.OBS(140,80,'a'),
              model.OBS(160,0,'b'),model.OBS(180,80,'b'),model.OBS(200,0,'b')]
        self.assertEqual(observed_depletions(rows,lambda a,b: a<=190<=b),[120])

    def test_current_and_future_windows_include_only_target_cohort(self):
        w=lambda t:{'predicted_stock_below_30_epoch':t}
        stream={'current_stock_window':w(120),'restock_events':[w(120),w(170),w(250)]}
        self.assertEqual(predicted_depletions(stream,start=100,end=200),[120,170])
        self.assertEqual(predicted_depletions(stream,start=120,end=170),[170])

    def test_matching_is_one_to_one_with_recall_and_precision_denominators(self):
        c=Counter();count_events(c,[1000,1010,2000],[1005])
        self.assertEqual(c['matched_60s'],1)
        self.assertEqual(c['observed'],1);self.assertEqual(c['forecast'],3)


if __name__=='__main__':unittest.main()
