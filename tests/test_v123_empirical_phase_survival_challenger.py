"""V123 empirical multi-cycle score regression, no lookahead, matched proxy."""
import bisect
import unittest
from unittest.mock import MagicMock

from research import v123_empirical_phase_survival_challenger as m
from research.v107_explicit_restock_cycle_baseline import StockObservation

T0=1700000000
ITEM="uni:Nessie Plushie"


def synthetic(*,cycles=200,low=7200,high=3600):
    t=T0
    obs=[StockObservation(t,0,"yata")]
    for _ in range(cycles):
        t+=low
        obs.append(StockObservation(t,200,"yata"))
        t+=high
        obs.append(StockObservation(t,0,"yata"))
    return obs


class PhaseSurvivalTests(unittest.TestCase):
    def test_depleted_conditional_probability_curve_from_completed_cycles(self):
        rows=synthetic(cycles=20)
        issue=rows[-1].epoch
        curve=m.empirical_survival_curve(
            rows,ITEM,asof=issue,scenarios=64)
        self.assertEqual(curve["status"],"EMPIRICAL_STOCK_SURVIVAL_CURVE")
        self.assertEqual(curve["immediate_arrival_score"],0.0)
        self.assertEqual(curve["scores"][3],1.0)
        self.assertEqual(curve["scores"][4],1.0)
        selected=m.choose_departure(curve,asof=issue)
        self.assertEqual(selected["status"],"DELAYED_ABOVE_IMMEDIATE_SCORE")
        self.assertEqual(selected["departure"],issue+900)
        self.assertEqual(selected["score"],1.0)
        self.assertFalse(curve["availability_scores_not_calibrated"] is False)

    def test_past_only_history_rejects_future_data(self):
        rows=synthetic(cycles=20)
        with self.assertRaisesRegex(ValueError,"future observation"):
            m.empirical_survival_curve(
                rows,ITEM,asof=rows[-2].epoch)
        # Prefix gives an earlier issue and cannot reach its later outcome.
        last_low=rows[-3].epoch
        prefix=[r for r in rows if r.epoch<=last_low]
        c=m.empirical_survival_curve(
            prefix,ITEM,asof=last_low,scenarios=64)
        self.assertEqual(c["status"],"EMPIRICAL_STOCK_SURVIVAL_CURVE")

    def test_insufficient_completed_cycles_abstains(self):
        rows=synthetic(cycles=3)
        c=m.empirical_survival_curve(
            rows,ITEM,asof=rows[-1].epoch,scenarios=32)
        self.assertEqual(c["status"],"INSUFFICIENT_COMPLETED_CYCLES")
        self.assertIsNone(m.choose_departure(
            c,asof=rows[-1].epoch)["departure"])

    def test_predeclared_score_gate_requires_contiguous_and_lift(self):
        curve={
            "status":"EMPIRICAL_STOCK_SURVIVAL_CURVE",
            "scores":[.2,.7,.1,.8,.8],
            "delay_seconds":[0,300,600,900,1200],
        }
        p=m.choose_departure(curve,asof=T0)
        self.assertEqual(p["departure"],T0+900)
        self.assertEqual(p["status"],"DELAYED_ABOVE_IMMEDIATE_SCORE")
        same=dict(curve,scores=[.8,.8,.8,.8,.8])
        self.assertEqual(m.choose_departure(
            same,asof=T0)["status"],"DEPART_NOW_SUPPORTED")
        no=dict(curve,scores=[.1,.59,.59,.4,.2])
        self.assertIsNone(m.choose_departure(no,asof=T0)["departure"])
        with self.assertRaises(ValueError):
            m.choose_departure(curve,asof=T0,required_lift=-.1)

    def test_whole_event_cohort_causality_and_proxy_difference(self):
        rows=synthetic()
        epochs=[o.epoch for o in rows]
        def observed(conn,country,item,arrival,asof):
            i=bisect.bisect_right(epochs,arrival)-1
            stocked=rows[i].quantity>=30
            return ("POLL_STATE_PROXY_SUCCESS" if stocked
                    else "POLL_STATE_PROXY_MISS",stocked,{})
        result=m.audit_item(
            rows,[],None,item_key=ITEM,
            asof=rows[-1].epoch+40000,
            max_anchors=16,scorer=observed)
        self.assertEqual(result["matured_depletion_anchors_evaluated"],16)
        self.assertEqual(result["model_departed"],16)
        self.assertEqual(result["model_no_departure"],0)
        self.assertEqual(result["model_only_hit"],16)
        self.assertEqual(result["immediate_only_hit"],0)
        self.assertEqual(result["mean_model_wait_minutes"],15.0)
        self.assertTrue(result["causal_prior_completed_phase_model_only"])
        self.assertFalse(result["provider_country_update_age_verified"])

    def test_counterfactual_identity_and_unknown_outcome_bounds(self):
        records=[
            {"issue":T0,"model_departure":T0,
             "model_hit":None,"immediate_hit":None},
            {"issue":T0+3600,"model_departure":T0+3900,
             "model_hit":True,"immediate_hit":False},
            {"issue":T0+7200,"model_departure":None,
             "model_hit":None,"immediate_hit":True},
        ]
        summary=m._pair(records)
        self.assertEqual(summary["depletion_starts"],3)
        self.assertEqual(summary["model_no_departure"],1)
        self.assertEqual(summary["unknown_pair"],1)
        self.assertEqual(summary["model_only_hit"],1)
        with self.assertRaisesRegex(AssertionError,"identical flight"):
            m._pair([dict(records[0],model_hit=True)])

    def test_country_and_sampler_validation(self):
        with self.assertRaises(ValueError):
            m.empirical_survival_curve(
                synthetic(cycles=2),"jap:Xanax",
                asof=synthetic(cycles=2)[-1].epoch)
        with self.assertRaises(ValueError):
            m.empirical_survival_curve(
                synthetic(cycles=2),ITEM,
                asof=synthetic(cycles=2)[-1].epoch,
                scenarios=0)


if __name__=="__main__":
    unittest.main()
