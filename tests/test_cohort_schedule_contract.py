"""Both the Monkey minute scorer and next-six current-stock policy survive sync."""
import inspect
import unittest
from unittest.mock import patch
from services import first_release_live as publisher
from services import first_release_schedule as schedule


class CohortPolicyTests(unittest.TestCase):
    def setUp(self):
        self.key = 'arg:Monkey Plushie'
        self.roster = {self.key: ('v20','traj3')}

    def _decision(self, *, index=1):
        return {
            'estimated_departure_epoch': 1000,
            'selected_restock_event_index': index,
            'forecast_events': [{'index':1,'estimated_departure_start_epoch':1000,
                                 'estimated_latest_departure_epoch':1300}],
            'current_stock_candidate': {'estimated_departure_start_epoch':1000,
                                        'estimated_latest_departure_epoch':1300},
        }

    def test_monkey_minute_refinement_preserved(self):
        with patch.object(schedule, 'build_item_travel_decision', side_effect=lambda *a,**k:self._decision()):
            base = dict(item_key=self.key)
            choice=lambda **kwargs: {'departure':1013,'minute_refined':True,'score':.42}
            accepted = schedule.build_first_release_decision(base,now=900,flight_seconds=6660,
                poll_age_seconds=10,timing_choice=choice,model_roster=self.roster,allow_minute_refinement=True)
            rejected = schedule.build_first_release_decision(base,now=900,flight_seconds=6660,
                poll_age_seconds=10,timing_choice=choice,model_roster=self.roster,allow_minute_refinement=False)
        self.assertEqual(accepted['estimated_departure_epoch'],1013)
        self.assertEqual(accepted['timing_refinement_status'],'ONE_MINUTE_STOCK_SCORE')
        self.assertEqual(rejected['estimated_departure_epoch'],1000)
        self.assertEqual(rejected['timing_refinement_status'],'REJECTED_OUTSIDE_FIRST_EVENT')

    def test_next_six_current_stock_does_not_wait_for_timing_scorer(self):
        with patch.object(schedule, 'build_item_travel_decision', return_value=self._decision(index=0)):
            def forbidden_choice(**kw): raise AssertionError('timing scorer must not run')
            result=schedule.build_first_release_decision(dict(item_key=self.key),now=900,
                flight_seconds=6660,poll_age_seconds=10,timing_choice=forbidden_choice,
                model_roster=self.roster,current_stock_leave_now=True)
        self.assertEqual(result['estimated_departure_epoch'],1000)
        self.assertEqual(result['timing_refinement_status'],'CURRENT_STOCK_REACHABLE_LEAVE_NOW')

    def test_next_six_publisher_and_monkey_timing_flags_both_exist(self):
        sig=inspect.signature(publisher.publish).parameters
        self.assertIn('next_six_cohort',sig)
        item=inspect.signature(schedule.forecast_first_release_item).parameters
        self.assertIn('refine_minute',item)
        self.assertIn('current_stock_leave_now',item)
        self.assertIn('forecast_transform',item)


if __name__=='__main__':
    unittest.main()
