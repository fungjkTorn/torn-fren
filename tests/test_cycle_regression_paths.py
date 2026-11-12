import unittest

from research.continuous_departure_replay import ArrivalEvidence
from research.cycle_regression_paths import CycleRegressionPaths
from research.true_zero_cycles import ZeroCycles
import test_restock_predictability_audit as fixtures

T=fixtures.T


class CyclePathTests(unittest.TestCase):
    def build(self,rows,cutoff,unknown=False):
        e=ArrivalEvidence(rows,list(range(T-30,cutoff+1,30)),[],cutoff)
        return CycleRegressionPaths(rows,lambda a,b:False,cutoff=cutoff,
            flight_seconds=100,interval_score=(lambda a,b:-1) if unknown else e.interval_score)

    def tracker(self,rows,issued):
        z=ZeroCycles(lambda a,b:False)
        for r in rows:
            if r.epoch<=issued:z.add(r)
        return z

    def test_prequential_fits_complete_paths_and_current_state_match(self):
        rows,cutoff=fixtures.PredictabilityTests().fixture();issued=T+6*86400
        planner=self.build(rows,cutoff);plans=planner.plans(issued,self.tracker(rows,issued),poll_age=0)
        self.assertIsNotNone(plans['ridge70']['departure_epoch'])
        for p in plans.values():
            if p.get('selected_paths') is None:continue
            self.assertLessEqual(p['clock_fit_latest_training_end'],p['current_cycle_start_epoch'])
            self.assertLessEqual(p['latest_training_path_end'],issued)
            self.assertTrue(p['current_physical_and_buying_phase_matched'])
            self.assertEqual(p['depletion_stock_quantity'],0)
            self.assertIsNone(p['calibrated_success_probability'])
            self.assertFalse(p['event_timing_prediction_supported'])

    def test_future_mutation_and_shorter_snapshot_preserve_earlier_plan(self):
        rows,cutoff=fixtures.PredictabilityTests().fixture();issued=T+6*86400;z=self.tracker(rows,issued)
        expected=self.build(rows,cutoff).plans(issued,z,poll_age=0)
        changed,_=fixtures.PredictabilityTests().fixture(change_after=issued)
        self.assertEqual(self.build(changed,cutoff).plans(issued,z,poll_age=0),expected)
        prefix=[r for r in rows if r.epoch<=issued]
        self.assertEqual(self.build(prefix,issued).plans(issued,z,poll_age=0),expected)
        with self.assertRaises(ValueError):
            self.build(rows,cutoff).plans(issued,self.tracker(rows,issued+3600),poll_age=0)

    def test_unknown_paths_and_expired_polls_cannot_create_departures(self):
        rows,cutoff=fixtures.PredictabilityTests().fixture();issued=T+6*86400;z=self.tracker(rows,issued)
        for planner,age in ((self.build(rows,cutoff,True),0),(self.build(rows,cutoff),181)):
            self.assertTrue(all(p['departure_epoch'] is None for p in planner.plans(issued,z,poll_age=age).values()))


if __name__=='__main__':unittest.main()
