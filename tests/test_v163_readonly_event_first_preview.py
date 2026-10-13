"""V163 event-first model predicts EACH restock, then flight, without skipping them."""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
FILE=ROOT/"deploy/scripts/v163_readonly_event_first_preview.py"
spec=importlib.util.spec_from_file_location("v163_events",FILE)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

ASOF=1791911000


def phase(*,kind="LOW",age=200,low=1200,high=600):
    return {
        "phase":kind,
        "phase_onset":ASOF-age,
        "last_observation":SimpleNamespace(
            epoch=ASOF-15,quantity=0 if kind=="LOW" else 350,source="yata"),
        "stocked_durations":[high]*20,
        "depleted_durations":[low]*20,
    }


class EventTimelineTests(unittest.TestCase):
    def test_all_restock_events_in_horizon_even_when_first_unreachable(self):
        low=phase(low=3600,high=300)
        actual=m.predict_events("jap:Xanax",low,asof=ASOF)
        self.assertEqual(actual["status"],"EVENT_TIMELINE_FORECAST_AVAILABLE")
        events=actual["restock_events"]
        self.assertGreaterEqual(len(events),6)
        self.assertEqual(actual["forecast_event_count"],len(events))
        self.assertEqual(events[0]["predicted_restock_epoch"],ASOF+3400)
        self.assertEqual(events[1]["predicted_restock_epoch"],ASOF+7300)
        self.assertIsNone(events[0]["expected_departure_epoch"])
        self.assertIsNone(events[1]["expected_departure_epoch"])
        self.assertEqual(events[2]["predicted_restock_epoch"],ASOF+11200)
        self.assertEqual(events[2]["expected_departure_epoch"],ASOF+11200-8940-10)
        self.assertEqual(events[2]["expected_arrival_epoch"],ASOF+11200)
        self.assertTrue(events[2]["expected_departure_reachable"])
        self.assertGreater(actual["unreachable_restock_events"],0)

    def test_near_plushie_restock_depart_now_and_next_cycle(self):
        low=phase(low=1200,high=600)
        result=m.predict_events("mex:Jaguar Plushie",low,asof=ASOF)
        self.assertGreaterEqual(result["forecast_event_count"],10)
        events=result["restock_events"]
        self.assertEqual(events[0]["predicted_restock_epoch"],ASOF+1000)
        self.assertEqual(events[0]["expected_departure_epoch"],ASOF)
        self.assertEqual(events[0]["expected_arrival_epoch"],ASOF+1030)
        self.assertEqual(events[1]["predicted_restock_epoch"],ASOF+2800)
        self.assertLess(events[0]["predicted_restock_epoch"],
                        events[1]["predicted_restock_epoch"])
        self.assertTrue(result["not_a_success_probability"])
        self.assertFalse(result["restock_accuracy_verified"])

    def test_high_current_stock_also_has_subsequent_restock_events(self):
        already_stocked=m.predict_events(
            "mex:Jaguar Plushie",
            phase(kind="HIGH",age=50,high=3600,low=500),asof=ASOF)
        self.assertIsNotNone(already_stocked["current_stock_window"])
        self.assertEqual(already_stocked["current_stock_window"]["expected_departure_epoch"],ASOF)
        self.assertGreater(len(already_stocked["restock_events"]),1)
        self.assertGreater(already_stocked["restock_events"][0]["predicted_restock_epoch"],ASOF+3000)

    def test_overdue_phase_preserves_uncertainty_without_inventing_schedule(self):
        history=phase(age=1500,low=1200,high=600)
        report=m.predict_events("mex:Jaguar Plushie",history,asof=ASOF)
        self.assertEqual(report["status"],"CURRENT_PHASE_OVERRAN_HISTORICAL_SURVIVORS")
        self.assertEqual(report["restock_events"],[])

    def test_lookahead_rejected_by_readonly_collector_asof(self):
        from test_v160_prospective_v151_shadow import collector_fixture
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=collector_fixture(root,issued=ASOF)
            with sqlite3.connect(source) as con:
                con.execute(
                    """INSERT INTO stock_history(timestamp,quantity,source,country,item_name)
                       VALUES(?,?,?,?,?)""",
                    (ASOF+500,500,"yata","mex","Jaguar Plushie"))
            before=source.read_bytes()
            a=m.forecast_all(source=source,asof=ASOF)
            self.assertEqual(a["roster"],24)
            self.assertEqual(a["source_heartbeat_age_seconds"],15)
            self.assertFalse(a["collector_written"])
            self.assertFalse(a["private_ledgers_written"])
            self.assertEqual(source.read_bytes(),before)
            self.assertEqual(a["validated_restock_timing_success"],None)
            self.assertNotIn(str(ASOF+500),json.dumps(a))

    def test_event_bounds_widen_over_multiple_future_replenishments(self):
        p=phase(age=200)
        p["stocked_durations"]=[300,400,600,900]*5
        p["depleted_durations"]=[900,1000,1200,1800]*5
        events=m.predict_events("mex:Jaguar Plushie",p,asof=ASOF)["restock_events"]
        self.assertGreater(len(events),3)
        widths=[e["restock_window_width_seconds"] for e in events]
        self.assertEqual(widths,sorted(widths))
        self.assertGreater(widths[-1],widths[0])
        self.assertTrue(all(e["predicted_restock_epoch"]<=ASOF+28800 for e in events))

    def test_event_matching_is_one_to_one_and_penalizes_missed_and_extra(self):
        result=m.match_events([100,150,300],[103,306,500],tolerance=10)
        self.assertEqual(result["matched"],2)
        self.assertEqual(result["missed_actual"],1)
        self.assertEqual(result["false_predicted"],1)
        self.assertEqual(result["sum_absolute_timing_error_seconds"],9)

    def test_historical_four_hour_replay_denominator_includes_all_clean_restocks(self):
        from test_v160_prospective_v151_shadow import collector_fixture
        from research.v128_full24_earliest_shadow import exact_roster
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            src=collector_fixture(root,issued=ASOF)
            start=(ASOF-90000)//1200*1200
            with sqlite3.connect(src) as db:
                for key in exact_roster():
                    country,item=key.split(":",1)
                    db.executemany(
                        """INSERT INTO stock_history(timestamp,quantity,source,country,item_name)
                           VALUES(?,?,?,?,?)""",
                        [(start+i*1200+offset,qty,"yata",country,item)
                         for i in range(72)
                         for offset,qty in ((0,0),(600,200),(900,0))])
            before=src.read_bytes()
            result=m.replay_events(
                source=src,asof=ASOF,days=1,tolerance=600,
                roster=exact_roster(),limit_items=2)
            self.assertEqual(result["items_evaluated"],2)
            self.assertGreater(result["actual_observed_restocks"],4)
            self.assertTrue(result["not_live_forward_validation"])
            self.assertTrue(result["not_five_minute_replanning"])
            self.assertFalse(result["collector_written"])
            self.assertFalse(result["lookahead_used_in_prediction"])
            self.assertLessEqual(result["matched_within_15s"],
                                 result["matched_within_60s"])
            self.assertLessEqual(result["matched_within_60s"],
                                 result["matched_timing"])
            self.assertLessEqual(result["matched_timing"],
                                 result["actual_observed_restocks"])
            self.assertLessEqual(result["matched_timing"],result["predicted_events"])
            self.assertIn("OBSERVED",m.format_replay(result).upper())
            self.assertEqual(src.read_bytes(),before)

    def test_cross_provider_threshold_not_claimed_as_clean_restock_truth(self):
        OBS=m.OBS
        rows=[OBS(100,0,"yata"),OBS(200,300,"prometheus"),
              OBS(300,0,"prometheus"),OBS(400,100,"prometheus")]
        events,amb=m.confirmed_restocks(rows,[],start=100,end=500)
        self.assertEqual(events,[400])
        self.assertEqual(amb,1)

    def test_invalid_inputs_and_future_evidence_fail_closed(self):
        with self.assertRaises(ValueError):
            m.predict_events("jap:Xanax",phase(),asof=ASOF,horizon=10)
        with self.assertRaises(ValueError):
            m.predict_events("mars:Xanax",phase(),asof=ASOF)
        missing=phase()
        missing["phase_onset"]=ASOF+1
        self.assertEqual(m.predict_events("jap:Xanax",missing,asof=ASOF)["status"],
                         "CURRENT_PHASE_UNKNOWN")

if __name__=="__main__":
    unittest.main()
