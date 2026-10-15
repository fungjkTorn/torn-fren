import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.flight_lead_uncertainty import audit,evaluate_item,point_available,model
from research.country_freshness_probe import probe,normalize

T=1790985600


class LeadTests(unittest.TestCase):
    def rows(self,end,change_after=None):
        return [model.OBS(t,0 if change_after is not None and t>change_after else qty,'a')
            for origin in range(T,end+1,2400) for offset,qty in ((0,0),(600,200),(1200,20),(1800,0))
            if (t:=origin+offset)<=end]

    def test_fixed_clock_forecasts_do_not_change_with_future_truth(self):
        issued=T+3*86400;end=issued+28800
        rows=self.rows(end);polls=list(range(T,end+1,30));left=[];right=[]
        kw=dict(cutoff=end,start=issued-86400,end=issued)
        a=evaluate_item('jap:Xanax',rows,polls,[],trace=left,**kw)
        evaluate_item('jap:Xanax',self.rows(end,issued-43200),polls,[],trace=right,**kw)
        self.assertEqual([r for r in left if r['issued']<=issued-43200],
                         [r for r in right if r['issued']<=issued-43200])
        self.assertEqual(a['models']['rate']['8940']['issues'],24)
        self.assertIsNotNone(a['models']['rate']['8940']['next_event_absolute_error_p90'])
        self.assertGreater(a['models']['rate']['8940']['cycle_count_known'],0)
        # 20 is physically positive; it never becomes a physical restock.
        self.assertEqual(a['completed_buying_window_median'],600)

    def test_unknown_poll_evidence_never_becomes_arrival_failure(self):
        issued=T+3*86400;end=issued+28800
        a=evaluate_item('jap:Xanax',self.rows(end),[],[],cutoff=end,start=issued-86400,end=issued)
        for family in a['models'].values():
            for row in family.values():
                self.assertEqual(row['unhealthy_issue'],24)
                self.assertEqual(row['occupancy_scored'],0)

    def test_readonly_export_without_country_table_reports_missing_measurement(self):
        from test_continuous_departure_replay import ContinuousTests
        with tempfile.TemporaryDirectory() as td:
            db=ContinuousTests().fixture(Path(td));before=db.read_bytes()
            r=audit(db,days=1,item_keys=['jap:Xanax'])
            self.assertEqual(before,db.read_bytes())
            self.assertFalse(r['country_clock_evidence_available'])
            self.assertEqual(len(r['items']),1)


class ProbeTests(unittest.TestCase):
    def test_bounded_normalized_probe_retains_unchanged_regressed_and_missing_clocks(self):
        updates=iter((990,990,980,980))
        def fetch(provider):
            return {'timestamp':995,'stocks':{'jap':{'update':next(updates),'stocks':[{}]}}}
        sleeps=[]
        r=probe(rounds=2,interval=60,fetch=fetch,clock=lambda:1000,sleep=sleeps.append)
        self.assertEqual(len(r['samples']),4)
        self.assertEqual(sleeps,[60])
        self.assertEqual(r['summary']['yata']['countries']['jap']['observed_clock_regressions'],1)
        self.assertEqual(r['samples'][0]['countries']['mex']['status'],'COUNTRY_MISSING')
        self.assertFalse(r['actual_game_freshness_verified'])
        with self.assertRaises(ValueError):probe(rounds=100,fetch=fetch)

    def test_fetch_failures_are_explicit_and_do_not_persist_error_secrets(self):
        def fetch(provider):raise RuntimeError('PRIVATE_TOKEN_DO_NOT_KEEP')
        r=probe(rounds=1,fetch=fetch)
        self.assertEqual(r['summary']['yata']['failed_fetches'],1)
        self.assertNotIn('PRIVATE_TOKEN',str(r))


if __name__=='__main__':unittest.main()
