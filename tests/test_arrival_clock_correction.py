import unittest

from research.arrival_clock_correction import ArrivalClockCorrection
from services.travel_window_policy import project_policy

T=(1791000000//3600)*3600


def forecast(issued,onset=None):
    start=issued+8940+1800
    return dict(item_key='jap:Xanax',asof_epoch=issued,flight_seconds=8940,
        status='EVENT_TIMELINE_FORECAST_AVAILABLE',current_stock_window=None,
        physical_phase_onset_epoch=(issued//7200)*7200 if onset is None else onset,
        depletion_stock_quantity=0,restock_timer_anchor='FIRST_OBSERVED_ZERO_AFTER_POSITIVE_STOCK',
        restock_events=[dict(predicted_restock_epoch=start,restock_early_epoch=start-200,
            restock_late_epoch=start+200,predicted_stock_below_30_epoch=start+600)])


class ClockTests(unittest.TestCase):
    def test_all_offsets_mature_before_truth_and_only_past_error_changes_clock(self):
        learner=ArrivalClockCorrection('rate');now=T
        def score(arrival):
            self.assertLessEqual(arrival+190,now)
            return ('SUCCESS' if (arrival-(T+10880+300))%3600==0 else 'FAILURE'),'fixture',None
        for now in range(T,T+36*3600+1,300):
            plans=learner.plans(now,forecast(now),poll_age=0,score=score)
            if now<T+4*3600:
                self.assertEqual(plans['recent']['offset_seconds'],0)
        self.assertEqual(plans['recent']['offset_seconds'],300)
        self.assertLessEqual(plans['recent']['training']['latest_training_maturity'],now)
        self.assertEqual(plans['recent']['departure_epoch'],now+2240)
        self.assertIsNone(plans['recent']['calibrated_success_probability'])
        self.assertFalse(plans['recent']['event_timing_prediction_supported'])

    def test_no_supported_error_preserves_baseline_and_unknown_is_not_failure(self):
        learner=ArrivalClockCorrection('rate')
        baseline=project_policy(forecast(T),now=T,poll_age_seconds=0,kind='current_quarter')
        plans=learner.plans(T,forecast(T),poll_age=0,score=lambda a:('UNKNOWN','fixture',None))
        self.assertTrue(all(p['departure_epoch']==baseline['estimated_departure_epoch'] for p in plans.values()))
        for i in range(32):
            learner.history[1].append(dict(issued=T+i,ready=T+i,values=[-1]*31))
        self.assertEqual(learner.fit(1,'recent')['offset_seconds'],0)

    def test_stable_mode_rejects_a_gain_confined_to_one_half(self):
        learner=ArrivalClockCorrection('rate')
        for i in range(64):
            values=[0]*31
            values[20 if i<32 else 10]=1  # +300 then -300; baseline is0.
            learner.history[1].append(dict(issued=T+i,ready=T+i,values=values))
        self.assertEqual(learner.fit(1,'recent')['offset_seconds'],-300)
        self.assertEqual(learner.fit(1,'stable')['offset_seconds'],0)

    def test_deduplicated_phase_and_stale_inputs_never_enroll_extra_trials(self):
        learner=ArrivalClockCorrection('rate')
        for hour in range(6):
            learner.plans(T+hour*3600,forecast(T+hour*3600,onset=T-300),poll_age=0,
                          score=lambda a:('FAILURE','fixture',None))
        self.assertEqual(learner.counts['enrolled_trials'],1)
        plans=learner.plans(T+6*3600,forecast(T+6*3600),poll_age=181,
                            score=lambda a:('FAILURE','fixture',None))
        self.assertTrue(all(p['departure_epoch'] is None for p in plans.values()))
        self.assertEqual(learner.counts['enrolled_trials'],1)

    def test_unknown_reference_blocks_apparent_gain_and_pending_truth_is_rejected(self):
        learner=ArrivalClockCorrection('rate')
        for i in range(32):
            values=[1]*31;values[15]=-1
            learner.history[1].append(dict(issued=T+i,ready=T+i,values=values))
        self.assertEqual(learner.fit(1,'recent')['offset_seconds'],0)
        learner.pending=[dict(issued=T,arrival=T+1000,bucket=1,ready=T+2090)]
        with self.assertRaises(ValueError):
            learner._resolve(T+2090,lambda a:('PENDING','bad fixture',None))

    def test_observed_current_window_is_kept_separate_from_future_error(self):
        learner=ArrivalClockCorrection('rate')
        for i in range(32):
            values=[0]*31;values[20]=1
            learner.history[1].append(dict(issued=T-10000+i,ready=T-9000+i,values=values))
        f=forecast(T);f['current_stock_window']={'predicted_stock_below_30_epoch':T+10000}
        plans=learner.plans(T,f,poll_age=0,score=lambda a:('FAILURE','fixture',None))
        self.assertTrue(all(p['departure_epoch']==T and p['offset_seconds']==0 for p in plans.values()))
        with self.assertRaises(ValueError):learner.plans(T,f,poll_age=0,score=lambda a:None)


if __name__=='__main__':unittest.main()
