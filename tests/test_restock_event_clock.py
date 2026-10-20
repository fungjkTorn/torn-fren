import unittest
import tempfile
from pathlib import Path

from research.restock_event_clock import IntervalClock,departure,model,item_benchmark,selected_target_error
from research.true_zero_cycles import ZeroCycles

T=1790985600


class EventClockTests(unittest.TestCase):
    def test_selected_later_event_is_not_matched_to_nearest_actual_drop(self):
        choice=dict(event_index=2,predicted_restock_epoch=1002)
        result=selected_target_error(choice,[1000,2000],500,lambda a,b:False)
        self.assertEqual(result['actual_restock'],2000)
        self.assertEqual(result['absolute_error_seconds'],998)
        self.assertEqual(selected_target_error(choice,[1000],500,lambda a,b:False)['status'],'PENDING')
        self.assertEqual(selected_target_error(choice,[1000,2000],500,lambda a,b:True)['status'],'UNKNOWN_CONTINUITY')

    def test_provider_switch_within_positive_phase_does_not_train_complete_cycle(self):
        rows=[model.OBS(T-30,0,'a'),model.OBS(T,200,'a'),model.OBS(T+100,180,'b'),
              model.OBS(T+200,0,'b'),model.OBS(T+1000,200,'b')]
        clock=IntervalClock(rows,lambda a,b:False,T+1000)
        self.assertEqual(clock.trials[0]['outcome'],'UNKNOWN')
        self.assertEqual(clock.trials[0]['invalidated_at'],T+100)

    def test_full_historical_path_is_readonly_and_keeps_both_metrics(self):
        from test_continuous_departure_replay import ContinuousTests
        with tempfile.TemporaryDirectory() as td:
            source=ContinuousTests().fixture(Path(td));before=source.read_bytes()
            r=item_benchmark(source,'mex:Jaguar Plushie',days=1)
            self.assertEqual(source.read_bytes(),before)
            self.assertIn('interval_ridge',r['restock_timing'])
            self.assertIn('interval_ridge_expected',r['departure'])
            self.assertIn('leave_now',r['chronological_slices']['later_validation'])
            self.assertFalse(r['production_promotion'])

    def fixture(self):
        rows=[model.OBS(T-30,0,'a')];epoch=T
        for i in range(140):
            rows.extend(model.OBS(epoch+d,n,'a') for d,n in ((0,200),(600,20),(900,0)))
            epoch+=(3600,5400,4500)[i%3]
        return rows,epoch

    def forecast(self,rows,issued,cutoff):
        clock=IntervalClock(rows,lambda a,b:False,cutoff)
        tracker=ZeroCycles(lambda a,b:False)
        for r in rows:
            if r.epoch<=issued:tracker.add(r)
        return clock.forecast('mex:Jaguar Plushie',tracker,issued,'ridge'),tracker

    def test_earliest_reachable_event_keeps_unreachable_next_drop(self):
        events=[dict(predicted_restock_epoch=t,predicted_stock_below_30_epoch=t+100) for t in (1200,2000)]
        forecast=dict(restock_events=events)
        chosen=departure(forecast,issued=1000,flight=500)
        self.assertEqual(chosen['event_index'],2)
        self.assertEqual(chosen['departure'],1500)
        self.assertEqual(chosen['landing'],2000)
        self.assertEqual(forecast['restock_events'],events)

    def test_plus10_is_after_actual_landing_not_subtracted_from_departure(self):
        forecast=dict(restock_events=[dict(predicted_restock_epoch=2000,predicted_stock_below_30_epoch=2010)])
        self.assertIsNone(departure(forecast,issued=1000,flight=500)['departure'])
        forecast['restock_events'][0]['predicted_stock_below_30_epoch']=2011
        self.assertEqual(departure(forecast,issued=1000,flight=500)['departure'],1500)

    def test_current_stock_and_uncertainty_window(self):
        f=dict(current_stock_window=dict(predicted_restock_epoch=1000,predicted_stock_below_30_epoch=1800,
            restock_late_epoch=1000,early_stock_end_epoch=1700))
        self.assertEqual(departure(f,issued=1000,flight=500)['event_index'],0)
        self.assertEqual(departure(f,issued=1000,flight=500,conservative=True)['departure'],1000)
        f['current_stock_window']['early_stock_end_epoch']=1500
        self.assertIsNone(departure(f,issued=1000,flight=500,conservative=True)['departure'])

    def test_future_mutation_does_not_change_issued_event_timeline(self):
        rows,cutoff=self.fixture();issued=rows[301].epoch+100
        original,tracker=self.forecast(rows,issued,cutoff)
        changed=[r if r.epoch<=issued else model.OBS(r.epoch,0,r.source) for r in rows]
        altered,_=self.forecast(changed,issued,cutoff)
        self.assertEqual(original,altered)
        self.assertEqual(original['status'],'EVENT_TIMELINE_FORECAST_AVAILABLE')
        self.assertLessEqual(original['latest_training_end'],issued)
        self.assertTrue(original['true_restock_events'])
        self.assertEqual(original['physical_depletion_quantity'],0)
        self.assertEqual(tracker.last.quantity,200)

    def test_residual_stock_below30_does_not_reset_restock_anchor(self):
        rows,cutoff=self.fixture()
        # Choose an actual restock (three observations per completed cycle).
        birth=rows[301].epoch
        before,_=self.forecast(rows,birth+100,cutoff)
        after,tracker=self.forecast(rows,birth+650,cutoff)
        self.assertEqual(tracker.last.quantity,20)
        self.assertEqual(before['anchor_restock_epoch'],after['anchor_restock_epoch'])
        self.assertIsNone(after['current_stock_window'])


if __name__=='__main__':unittest.main()
