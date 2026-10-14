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
        changed=DailyTemplate([r if r.epoch<=t-43200 else OBS(r.epoch,0,r.source) for r in rows],lambda a,b:False)
        self.assertEqual(before,changed.plan(t-43200,1020))
        self.assertTrue(queries)
        with self.assertRaises(ValueError):
            real(t+1,t)

    def test_absent_history_abstains(self):
        result=DailyTemplate([],lambda a,b:False).plan(1791910800,1020)
        self.assertIsNone(result["earliest"])
        self.assertIsNone(result["center"])


if __name__=="__main__":unittest.main()
