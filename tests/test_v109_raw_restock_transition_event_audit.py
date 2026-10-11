"""V109: event timing on raw source observations, never hindsight-cleaned."""
import unittest
from unittest.mock import patch

from research import v109_raw_restock_transition_event_audit as m
from research.v107_explicit_restock_cycle_baseline import (
    StockObservation,next_windows
)

START=1_700_000_000
LOW=7200
HIGH=7200


def repeating(n=80):
    t=START
    rows=[StockObservation(t,0,"yata")]
    for k in range(n):
        t+=LOW
        rows.append(StockObservation(t,250,"yata"))
        t+=HIGH
        rows.append(StockObservation(t,0,"yata"))
    return rows


class TransitionLevelTests(unittest.TestCase):
    def test_completed_events_are_distinct_provider_continuous_phases(self):
        obs=repeating(8)
        event,rejected=m.transition_episodes(obs)
        self.assertEqual(len(event),15)
        self.assertEqual(rejected["SHORT_TRANSITION_BOUNCE"],0)
        self.assertEqual(event[0]["phase"],"STOCKED")
        self.assertEqual(event[0]["phase_duration_seconds"],HIGH)
        self.assertEqual(event[1]["phase"],"DEPLETED")
        self.assertEqual(event[1]["phase_duration_seconds"],LOW)

    def test_constant_cycle_forecast_next_transition_is_exact(self):
        obs=repeating(80)
        episodes,_=m.transition_episodes(obs)
        info=m.evaluate_events(obs,episodes,item_key="uni:Nessie Plushie",
                               max_episodes=25)
        self.assertGreater(info["distinct_observed_phase_events_sampled"],0)
        for phase in ("STOCKED","DEPLETED"):
            stat=info["phase_predictions"][phase]
            self.assertGreater(stat["forecasts_issued"],0)
            self.assertEqual(stat["within_5m"],stat["forecasts_issued"])
            self.assertEqual(stat["median_absolute_error_minutes"],0)

    def test_future_rows_never_enter_model_input_during_prediction(self):
        obs=repeating(80)
        episodes,_=m.transition_episodes(obs)
        actual_model=next_windows
        visited=[]
        def checked(item_key,past,*,asof,collection_gaps):
            self.assertTrue(past)
            self.assertLessEqual(max(r.epoch for r in past),asof)
            visited.append(asof)
            return actual_model(item_key,past,asof=asof,
                                collection_gaps=collection_gaps)
        with patch.object(m,"next_windows",side_effect=checked):
            out=m.evaluate_events(obs,episodes,item_key="uni:Nessie Plushie",
                                  max_episodes=10)
        self.assertTrue(visited)
        self.assertTrue(out["future_stock_used_in_prediction"] is False)

    def test_cross_provider_or_gap_is_not_one_completed_phase(self):
        obs=repeating(12)
        split=len(obs)//2
        mixed=obs[:split]+[
            StockObservation(r.epoch,r.quantity,"prometheus")
            for r in obs[split:]]
        episodes,rej=m.transition_episodes(mixed)
        self.assertGreater(rej["PROVIDER_OR_COLLECTION_GAP"],0)
        a=obs[7].epoch-100
        b=obs[8].epoch+100
        episodes2,rej2=m.transition_episodes(obs,gaps=[(a,b)])
        self.assertGreater(rej2["PROVIDER_OR_COLLECTION_GAP"],0)
        self.assertLess(len(episodes2),len(obs)-2)

    def test_short_bounce_rejected_explicitly(self):
        obs=[
            StockObservation(START,0,"yata"),
            StockObservation(START+200,100,"yata"),
            StockObservation(START+300,0,"yata"),
            StockObservation(START+1200,100,"yata")
        ]
        events,rejected=m.transition_episodes(obs)
        self.assertEqual(rejected["SHORT_TRANSITION_BOUNCE"],1)
        self.assertEqual(len(events),1)

    def test_restocks_scored_even_when_flight_cannot_reach_first_window(self):
        prediction={
            "status":"ABSTAIN_NO_FLIGHT_CAN_REACH_PREDICTED_WINDOW",
            "windows":[{
                "expected_stocked_start":START+600,
                "expected_drop_below_30":START+900,
            }],
        }
        self.assertEqual(
            m.actual_forecast_boundary(prediction,"DEPLETED"),START+600)
        self.assertEqual(
            m.actual_forecast_boundary(prediction,"STOCKED"),START+900)

    def test_empty_history_has_no_claimed_skill(self):
        out=m.evaluate_events([],[],item_key="uni:Nessie Plushie")
        self.assertEqual(out["state"],"NO_OBSERVATIONS")

    def test_scoring_first_transition_tracks_correct_boundary(self):
        obs=repeating(10)
        q=obs[-2].epoch  # newly replenished above 30
        p=next_windows("uni:Nessie Plushie",obs,asof=q)
        self.assertEqual(
            m.actual_forecast_boundary(p,"STOCKED"),
            q+HIGH)
        q2=obs[-1].epoch
        p2=next_windows("uni:Nessie Plushie",obs,asof=q2)
        self.assertEqual(
            m.actual_forecast_boundary(p2,"DEPLETED"),
            q2+LOW)


if __name__=="__main__":
    unittest.main()
