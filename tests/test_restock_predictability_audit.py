import tempfile
import unittest
from pathlib import Path

from research.restock_predictability_audit import (
    audit,cycles_from_rows,evaluate,clock_fit,model)

T=1790985600


class PredictabilityTests(unittest.TestCase):
    def fixture(self,n=160,change_after=None):
        rows=[model.OBS(T-30,0,'a')];epoch=T
        for i in range(n):
            for offset,quantity in ((0,200),(600,20),(900,0)):
                t=epoch+offset
                rows.append(model.OBS(t,0 if change_after is not None and t>change_after else quantity,'a'))
            epoch+=(3600,5400,4500)[i%3]
        return rows,epoch

    def test_regression_recovers_causal_serial_signal_without_below30_depletion(self):
        rows,cutoff=self.fixture()
        trials,restocks=cycles_from_rows(rows,lambda a,b:False,cutoff)
        self.assertEqual(trials[0]['stock_seconds'],900)
        self.assertEqual(trials[0]['empty_seconds'],2700)
        self.assertEqual(trials[-1]['outcome'],'PENDING')
        trace=[];r=evaluate('jap:Xanax',rows,list(range(T,cutoff+1,30)),[],cutoff=cutoff,trace=trace)
        c=r['cycle_regression']
        self.assertGreater(c['models']['ridge']['n'],30)
        self.assertLess(c['models']['ridge']['mae_seconds'],c['models']['median']['mae_seconds']*.5)
        self.assertTrue(c['signal_for_departure_experiment'])
        for row in trace:
            if row['prediction'] is not None:self.assertLessEqual(row['prediction']['latest_training_end'],row['start'])

    def test_future_mutations_do_not_change_earlier_predictions(self):
        rows,cutoff=self.fixture();split=T+4*86400;before=[];after=[]
        polls=list(range(T,cutoff+1,30))
        evaluate('jap:Xanax',rows,polls,[],cutoff=cutoff,trace=before)
        changed,_=self.fixture(change_after=split)
        evaluate('jap:Xanax',changed,polls,[],cutoff=cutoff,trace=after)
        self.assertEqual([r for r in before if r['start']<=split],[r for r in after if r['start']<=split])

    def test_provider_phase_conflict_and_gap_do_not_fabricate_cycles(self):
        rows=[model.OBS(T-30,0,'a'),model.OBS(T,200,'a'),
              model.OBS(T+600,20,'b'),model.OBS(T+900,0,'b'),model.OBS(T+3600,200,'b')]
        clean,_=cycles_from_rows(rows,lambda a,b:False,T+3600)
        self.assertEqual(clean[0]['outcome'],'CLOSED')
        conflict=rows[:2]+[model.OBS(T+600,0,'b')]+rows[3:]
        bad,_=cycles_from_rows(conflict,lambda a,b:False,T+3600)
        self.assertEqual(bad[0]['outcome'],'UNKNOWN')
        bad,_=cycles_from_rows(rows,lambda a,b:a<=T+100<=b,T+3600)
        self.assertEqual(bad[0]['outcome'],'UNKNOWN')

    def test_clock_control_rejects_a_sampling_cadence_artifact(self):
        events=[T+300+i*900 for i in range(100)];asof=events[-1]+60
        complete=list(range(T,asof+1,30))
        fit=clock_fit(events,complete,asof,900)
        self.assertTrue(fit['admitted'])
        sparse=[t for t in complete if min((t-T-300)%900,900-(t-T-300)%900)<=60]
        self.assertFalse(clock_fit(events,sparse,asof,900)['admitted'])
        future=events+[asof+900+i for i in range(100)]
        self.assertEqual(clock_fit(future,complete+[asof+900],asof,900),fit)

    def test_sanitized_source_remains_readonly_and_pending_counts_visible(self):
        from test_continuous_departure_replay import ContinuousTests
        with tempfile.TemporaryDirectory() as td:
            db=ContinuousTests().fixture(Path(td));before=db.read_bytes()
            r=audit(db,days=1,item_keys=['jap:Xanax'])
            self.assertEqual(db.read_bytes(),before)
            self.assertEqual(r['physical_depletion_quantity'],0)
            self.assertIn('PENDING',r['items']['jap:Xanax']['cycle_regression'])
            self.assertFalse(r['production_promotion'])


if __name__=='__main__':unittest.main()
