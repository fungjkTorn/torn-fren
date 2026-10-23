import unittest
from types import SimpleNamespace

from research.v167_all24_live_policy_replay import (
    ROUTES, MAX_EVENTS, lifecycle_telemetry, project_events, first_reachable
)


class V167PolicyTests(unittest.TestCase):
    def test_exact_24_routes_and_japan_included(self):
        self.assertEqual(25,len(ROUTES))
        self.assertEqual("champion",ROUTES["jap:Xanax"]["primary"])
        self.assertEqual("japan_quantity_rate",ROUTES["jap:Xanax"]["champion_kind"])
        self.assertEqual("v19_sou_dyn1",ROUTES["sou:Xanax"]["champion_kind"])

    def test_event_projection_has_no_time_horizon(self):
        # Multi-day depleted cycles should still project; no 8h/30d cutoff.
        phases={
            "phase":"LOW",
            "phase_onset":1_000_000,
            "last_observation":SimpleNamespace(epoch=1_000_000,quantity=0),
            "stocked_durations":[3600,4200,3900,4500],
            "depleted_durations":[3*86400,4*86400,5*86400,4*86400],
        }
        events=project_events("uni:Nessie Plushie",phases,1_000_000,max_events=4)
        self.assertEqual(4,len(events))
        self.assertGreater(events[-1]["predicted_restock_epoch"]-1_000_000,8*3600)
        self.assertGreater(events[-1]["predicted_restock_epoch"]-1_000_000,7*86400)

    def test_first_reachable_can_skip_events(self):
        events=[
            {"event_index":1,"reachable":False},
            {"event_index":2,"reachable":False},
            {"event_index":3,"reachable":True},
        ]
        self.assertEqual(3,first_reachable(events)["event_index"])

    def test_v2_lifecycle_fields(self):
        rows=[
            (1000,0,"p"),(1600,50,"p"),(2200,20,"p"),
            (3000,0,"p"),(4000,60,"p"),(5200,10,"p"),
            (6500,0,"p"),(8000,70,"p"),(9800,5,"p"),
        ]
        t=lifecycle_telemetry(rows,[],10_000)
        for key in (
            "last_restock_epoch","last_depletion_epoch",
            "avg_stocked_lifetime_seconds","median_stocked_lifetime_seconds",
            "avg_zero_to_restock_seconds","median_zero_to_restock_seconds",
            "avg_restock_interval_seconds","median_restock_interval_seconds",
            "avg_batch_size","median_batch_size",
            "valid_cycles","excluded_cycles",
            "current_phase","current_phase_age_seconds",
        ):
            self.assertIn(key,t)
        self.assertEqual(3,t["valid_cycles"])


if __name__=="__main__":
    unittest.main()
