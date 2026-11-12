import unittest
import numpy as np
from research import continuous_departure_replay as replay
from research.causal_stock_paths import CausalStockPaths
from research.inventory_feature_paths import InventoryFeaturePaths as M
from research.quantity_rate_cycles import QuantityRateCycles
import test_restock_predictability_audit as fixtures

T=fixtures.T


class InventoryFeatureTests(unittest.TestCase):
    def build(self,rows,cutoff,unknown=False):
        e=replay.ArrivalEvidence(rows,list(range(T-30,cutoff+1,30)),[],cutoff)
        base=CausalStockPaths(rows,list(range(T-30,cutoff+1,30)),lambda a,b:False,
            cutoff=cutoff,flight_seconds=100,score=(lambda t:('UNKNOWN','x',None)) if unknown else e.score)
        return M(base,rows,lambda a,b:False)

    def tracker(self,rows,issued):
        z=QuantityRateCycles(lambda a,b:False)
        for r in rows:
            if r.epoch<=issued:z.add(r)
        return z

    def test_all_six_ablations_only_use_fully_mature_paths_and_no_event_claims(self):
        rows,cutoff=fixtures.PredictabilityTests().fixture();issued=T+6*86400
        p=self.build(rows,cutoff).plans(issued,self.tracker(rows,issued),poll_age=0)
        self.assertEqual(set(p),set(M.MODES));self.assertEqual(len(p),6)
        self.assertTrue(any(r['departure_epoch'] is not None for r in p.values()))
        for r in p.values():
            self.assertLessEqual(r['latest_training_path_end'],issued)
            self.assertLessEqual(r['scale_training_latest_origin']+28800+100+190,issued)
            self.assertGreaterEqual(r['selected_paths'],24)
            self.assertIsNone(r['calibrated_success_probability']);self.assertFalse(r['event_timing_prediction_supported'])
            self.assertEqual(r['depletion_stock_quantity'],0)
        self.assertNotIn(2,p['phase70']['feature_indices'])
        self.assertNotIn(10,p['quantity70']['feature_indices']);self.assertIn(10,p['flow70']['feature_indices'])

    def test_whole_future_mutation_prefix_and_base_matrix_immutability(self):
        rows,cutoff=fixtures.PredictabilityTests().fixture();issued=T+6*86400;z=self.tracker(rows,issued)
        m=self.build(rows,cutoff);before=m.base.outcomes.copy();expected=m.plans(issued,z,poll_age=0)
        np.testing.assert_array_equal(before,m.base.outcomes)
        changed,_=fixtures.PredictabilityTests().fixture(change_after=issued)
        self.assertEqual(self.build(changed,cutoff).plans(issued,z,poll_age=0),expected)
        self.assertEqual(self.build([r for r in rows if r.epoch<=issued],issued).plans(issued,z,poll_age=0),expected)
        with self.assertRaises(ValueError):m.plans(issued,self.tracker(rows,issued+3600),poll_age=0)

    def test_decline_signal_resets_on_provider_change_topup_and_old_update(self):
        z=QuantityRateCycles(lambda a,b:False)
        for i in range(5):
            for offset,q in ((0,0),(60,1000),(300,700),(600,300),(900,0)):
                z.add(replay.model.OBS(T+i*1800+offset,q,'yata'))
        b=T+5*1800
        for offset,q in ((0,1000),(60,850),(120,700),(180,550)):
            z.add(replay.model.OBS(b+offset,q,'yata'))
        self.assertEqual(M.features(z,b+180)[11],1)
        self.assertEqual(M.features(z,b+400)[11],0)
        z.add(replay.model.OBS(b+210,520,'other'));self.assertEqual(M.features(z,b+210)[11],0)
        z.add(replay.model.OBS(b+240,900,'other'));self.assertEqual(M.features(z,b+240)[11],0)
        z.add(replay.model.OBS(b+300,20,'other'));f=M.features(z,b+300)
        self.assertEqual(f[0],1);self.assertEqual(f[13],0) # unavailable20 is physically positive

    def test_unknown_future_stock_and_expired_polls_abstain(self):
        rows,cutoff=fixtures.PredictabilityTests().fixture();issued=T+6*86400;z=self.tracker(rows,issued)
        for m,age in ((self.build(rows,cutoff,True),0),(self.build(rows,cutoff),181)):
            self.assertTrue(all(r['departure_epoch'] is None for r in m.plans(issued,z,poll_age=age).values()))


if __name__=='__main__':unittest.main()
