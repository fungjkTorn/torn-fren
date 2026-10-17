"""V111 arrival evidence audit: strict proxy vs weak last-known only."""
import unittest

from research import v111_arrival_proxy_evidence_audit as m
from research.v107_explicit_restock_cycle_baseline import StockObservation

START=1700000000


def rows(*values):
    return [StockObservation(START+offset,qty,src)
            for offset,qty,src in values]


class ArrivalEvidenceTests(unittest.TestCase):
    def evidence(self,arr,*,observations=None,gaps=()):
        obs=observations if observations is not None else rows(
            (0,120,"yata"),(600,90,"yata"))
        return m.arrival_evidence(
            obs,[x.epoch for x in obs],gaps,START+arr)

    def test_two_sided_same_provider_high_state_is_strict_hit(self):
        e=self.evidence(300)
        self.assertTrue(e["strict_bracket_proxy"])
        self.assertTrue(e["last_known_proxy"])
        self.assertEqual(e["reason"],"SAME_SOURCE_BRACKETED_STATE")

    def test_two_sided_same_provider_low_state_is_strict_miss(self):
        obs=rows((0,5,"yata"),(600,0,"yata"))
        e=self.evidence(300,observations=obs)
        self.assertIs(e["strict_bracket_proxy"],False)

    def test_actual_threshold_crossing_straddles_arrival_is_not_scored(self):
        obs=rows((0,0,"yata"),(600,100,"yata"))
        e=self.evidence(300,observations=obs)
        self.assertIsNone(e["strict_bracket_proxy"])
        self.assertFalse(e["last_known_proxy"])
        self.assertTrue(e["transition_straddles_arrival"])

    def test_switching_providers_disallows_strict_claim(self):
        obs=rows((0,100,"yata"),(600,80,"prometheus"))
        e=self.evidence(300,observations=obs)
        self.assertIsNone(e["strict_bracket_proxy"])
        self.assertTrue(e["last_known_proxy"])
        self.assertTrue(e["source_switch_across_bracket"])

    def test_no_recent_next_observation_is_weak_only(self):
        obs=rows((0,100,"yata"),(2000,80,"yata"))
        e=self.evidence(300,observations=obs)
        self.assertIsNone(e["strict_bracket_proxy"])
        self.assertTrue(e["last_known_proxy"])
        self.assertEqual(e["reason"],"NO_NEARBY_AFTER_ARRIVAL")

    def test_stale_previous_row_not_used_as_proof(self):
        e=self.evidence(1000)
        self.assertIsNone(e["strict_bracket_proxy"])
        # Here prior row is at +600; still recent but no later observation.
        self.assertTrue(e["last_known_proxy"])
        obs=rows((0,200,"yata"),(4000,80,"yata"))
        e=m.arrival_evidence(obs,[x.epoch for x in obs],(),
                             START+1000)
        self.assertIsNone(e["last_known_proxy"])
        self.assertEqual(e["reason"],"NO_RECENT_BEFORE_ARRIVAL")

    def test_known_collector_gap_censors_last_known(self):
        e=self.evidence(300,gaps=[(START+200,START+400)])
        self.assertIsNone(e["strict_bracket_proxy"])
        self.assertIsNone(e["last_known_proxy"])
        self.assertEqual(e["reason"],"COLLECTION_GAP_BEFORE_ARRIVAL")

    def test_exact_at_row_is_observed_stock_not_future_imputation(self):
        e=self.evidence(0)
        self.assertTrue(e["strict_bracket_proxy"])
        self.assertEqual(e["reason"],"EXACT_STOCK_ROW_TIMESTAMP")

    def test_causal_model_uses_only_prior_raw_rows(self):
        obs=[StockObservation(START,0,"yata")]
        t=START
        for _ in range(400):
            t+=900
            obs.append(StockObservation(t,200,"yata"))
            t+=1800
            obs.append(StockObservation(t,0,"yata"))
        checked=[]
        def predictor(item,history,*,asof,collection_gaps):
            self.assertTrue(all(row.epoch<=asof for row in history))
            checked.append(asof)
            # Same valid schema as restock prediction but no secret future.
            return {"windows":[{
                "earliest_expected_departure":asof,
                "expected_stocked_start":asof+6360,
                "expected_drop_below_30":asof+7000
            }]}
        audit=m.audit_item(obs,(),item_key="uni:Nessie Plushie",
                          max_events=4,forecast=predictor)
        self.assertEqual(audit["selected_distinct_depletion_anchors"],4)
        self.assertEqual(audit["forecasted_departures"],4)
        self.assertEqual(len(checked),4)
        self.assertFalse(audit["strict_player_success_verified"])
        self.assertFalse(audit["country_provider_asof_verified"])


if __name__=="__main__":
    unittest.main()
