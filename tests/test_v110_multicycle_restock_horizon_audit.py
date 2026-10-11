"""V110: restock-horizon errors assessed as distinct events, not updates."""
import unittest
from unittest.mock import patch

from research import v110_multicycle_restock_horizon_audit as m
from research.v107_explicit_restock_cycle_baseline import (
    StockObservation,next_windows
)
from research.v109_raw_restock_transition_event_audit import (
    transition_episodes
)

START=1700000000


def repeated(*,n=500,low=900,high=1800):
    t=START
    rows=[StockObservation(t,0,"yata")]
    for _ in range(n):
        t+=low
        rows.append(StockObservation(t,200,"yata"))
        t+=high
        rows.append(StockObservation(t,0,"yata"))
    return rows


class MulticycleTests(unittest.TestCase):
    def test_contiguous_phases_reconstruct_distinct_future_restock_windows(self):
        events,_=transition_episodes(repeated(n=5))
        windows=m.chained_future_restock_windows(events,1)
        self.assertEqual(len(windows),4)
        self.assertEqual(windows[0]["restock"],events[1]["actual_next_transition"])
        self.assertLess(windows[0]["restock"],windows[0]["depletion"])
        self.assertEqual(windows[1]["restock"],
                         windows[0]["depletion"]+900)

    def test_four_hop_model_synthetic_causal_perfect_cycle(self):
        obs=repeated()
        events,_=transition_episodes(obs)
        out=m.evaluate_multihop(obs,events,(),item_key="uni:Red Fox Plushie",
                                max_events=15)
        self.assertEqual(out["selected_distinct_depletion_events"],15)
        for hop in ("1","2","3","4"):
            s=out["by_predicted_restock_hop"][hop]
            self.assertEqual(s["scorable"],15)
            self.assertEqual(s["within_5m"],15)
            self.assertEqual(s["errors"]["median_abs_minutes"],0)
        self.assertEqual(out["first_reachable_window_hop_counts"],{3:15})
        self.assertEqual(out["flight_proxy_scorable"],15)
        self.assertEqual(out["flight_proxy_successes"],15)
        self.assertEqual(out["flight_proxy_misses"],0)

    def test_every_model_input_is_strictly_asof_no_future(self):
        obs=repeated()
        events,_=transition_episodes(obs)
        seen=[]
        def checked(key,prior,*,asof,collection_gaps):
            self.assertTrue(all(x.epoch<=asof for x in prior))
            self.assertEqual(prior[-1].epoch,asof)
            seen.append(asof)
            return next_windows(
                key,prior,asof=asof,collection_gaps=collection_gaps)
        m.evaluate_multihop(obs,events,(),item_key="uni:Nessie Plushie",
                            max_events=8,forecast=checked)
        self.assertEqual(len(seen),8)

    def test_censor_on_broken_provider_segment(self):
        obs=repeated(n=30)
        boundary=len(obs)//2
        obs=obs[:boundary]+[
            StockObservation(r.epoch,r.quantity,"prometheus")
            for r in obs[boundary:]]
        episodes,rej=transition_episodes(obs)
        self.assertGreater(rej["PROVIDER_OR_COLLECTION_GAP"],0)
        for i,anchor in enumerate(episodes):
            if anchor["phase"]!="DEPLETED":
                continue
            windows=m.chained_future_restock_windows(episodes,i)
            self.assertTrue(all(
                item["depletion"]<=episodes[-1]["actual_next_transition"]
                for item in windows))
            self.assertLessEqual(len(windows),4)

    def test_short_bounce_censoring_not_silent_hop_skip(self):
        obs=[
            StockObservation(START,0,"yata"),
            StockObservation(START+600,100,"yata"),
            StockObservation(START+1200,0,"yata"),
            StockObservation(START+1250,300,"yata"),
            StockObservation(START+2200,0,"yata"),
            StockObservation(START+2800,150,"yata"),
            StockObservation(START+4000,0,"yata"),
        ]
        events,rej=transition_episodes(obs)
        self.assertGreater(rej["SHORT_TRANSITION_BOUNCE"],0)
        first_depleted=next(i for i,e in enumerate(events)
                            if e["phase"]=="DEPLETED")
        actual=m.chained_future_restock_windows(events,first_depleted)
        self.assertEqual(actual,[])

    def test_past_event_not_scored_as_current_arrival(self):
        self.assertEqual(m.choose_anchor_events([],[],max_events=10),[])
        with self.assertRaises(ValueError):
            m.chained_future_restock_windows(
                [{"phase":"STOCKED"}],0)


if __name__=="__main__":
    unittest.main()
