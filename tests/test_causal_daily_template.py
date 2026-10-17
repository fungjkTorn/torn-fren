import unittest
from research.causal_daily_template import DailyTemplate
from deploy.scripts.v163_readonly_event_first_preview import OBS


class TemplateTests(unittest.TestCase):
    def test_features_and_historical_targets_never_read_future_stock(self):
        t=1791910800
        rows=[OBS(t-3*86400+i*600,200 if i%2 else 0,"yata") for i in range(433)]
        model=DailyTemplate(rows,lambda a,b:False)
        real=model.state; queries=[]
        def traced(clock,issued):
            self.assertLessEqual(clock,issued);queries.append(clock)
            return real(clock,issued)
        model.state=traced
        before=model.plan(t-43200,1020)
        events=model.event_forecast(t-43200,'mex:Jaguar Plushie',1020)
        changed=DailyTemplate([r if r.epoch<=t-43200 else OBS(r.epoch,0,r.source) for r in rows],lambda a,b:False)
        self.assertEqual(before,changed.plan(t-43200,1020))
        self.assertEqual(events,changed.event_forecast(t-43200,'mex:Jaguar Plushie',1020))
        self.assertTrue(events['restock_events'])
        for event in events['restock_events']:
            self.assertLessEqual(event['historical_template_depletion_epoch'],t-43200)
            self.assertGreater(event['predicted_restock_epoch'],t-43200)
        self.assertTrue(queries)
        with self.assertRaises(ValueError):
            real(t+1,t)

    def test_absent_history_abstains(self):
        result=DailyTemplate([],lambda a,b:False).plan(1791910800,1020)
        self.assertIsNone(result["earliest"])
        self.assertIsNone(result["center"])
        self.assertIsNone(result["first_center"])

    def test_benign_provider_change_preserves_bounded_stock_phase(self):
        rows=[OBS(100,0,'a'),OBS(200,100,'a'),OBS(300,90,'b'),OBS(500,0,'b')]
        self.assertEqual(DailyTemplate(rows,lambda a,b:False).windows,[(200,500)])

    def test_provider_switch_at_threshold_or_known_gap_is_not_invented_cycle(self):
        rows=[OBS(100,0,'a'),OBS(200,100,'b'),OBS(500,0,'b')]
        self.assertEqual(DailyTemplate(rows,lambda a,b:False).windows,[])
        rows=[OBS(100,0,'a'),OBS(200,100,'a'),OBS(300,90,'a'),OBS(500,0,'a')]
        self.assertEqual(DailyTemplate(rows,lambda a,b:a<=350<=b).windows,[])


if __name__=="__main__":unittest.main()
