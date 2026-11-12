"""V163 event-first model predicts EACH restock, then flight, without skipping them."""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
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
        # Exercise explicit legacy horizon behavior; the current default has
        # no calendar cap (covered by the first-release/horizon-free tests).
        events=m.predict_events("mex:Jaguar Plushie",p,asof=ASOF,
                                horizon=28800)["restock_events"]
        self.assertGreater(len(events),3)
        widths=[e["restock_window_width_seconds"] for e in events]
        self.assertEqual(widths,sorted(widths))
        self.assertGreater(widths[-1],widths[0])
        self.assertTrue(all(e["predicted_restock_epoch"]<=ASOF+28800 for e in events))

    def test_source_streamed_to_python_stdin_pins_research_on_foreign_cwd(self):
        # Reproduce the real VM failure: git show | python -, where the
        # checked-out worktree does not necessarily contain V128 and imports
        # have to resolve from the separately staged pinned research tree.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            work=root/"checkout"
            (work/"research").mkdir(parents=True)
            stage=root/"pinned"/"research"
            champions=stage/"plushie_champions"
            champions.mkdir(parents=True)
            modules={
                "plushie_champions/common.py":"TRAVEL_SECONDS={'mex':1020}\n",
                "v128_full24_earliest_shadow.py":
                    "_gap_index=None\n_read_item=None\nexact_roster=None\n",
                "v145_provider_continuous_phases.py":
                    "provider_continuous_phases=None\n",
                "v60_private_snapshot_probe.py":"read_heartbeat=None\n",
            }
            for name,content in modules.items():
                dest=stage/name
                dest.write_text(content,encoding="utf8")
            outside=root/"outside"
            outside.mkdir()
            env=os.environ.copy()
            env.update(TORNFREN_REPLAY_PINNED_RESEARCH=str(stage),
                       TORNFREN_REPLAY_WORK=str(work),PYTHONPATH="",
                       PYTHONDONTWRITEBYTECODE="1")
            run=subprocess.run([sys.executable,"-","--help"],
                input=FILE.read_text(encoding="utf8"),text=True,
                cwd=outside,env=env,capture_output=True,timeout=20)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIn("--historical-replay-days",run.stdout)
            # Removing one pinned dependency must FAIL, not silently import
            # a similarly named version from the mutable checkout.
            (stage/"v128_full24_earliest_shadow.py").unlink()
            fail=subprocess.run([sys.executable,"-","--help"],
                input=FILE.read_text(encoding="utf8"),text=True,
                cwd=outside,env=env,capture_output=True,timeout=20)
            self.assertNotEqual(fail.returncode,0)
            self.assertIn("v128_full24_earliest_shadow",fail.stderr)

    def test_nearby_overlapping_restock_events_use_optimal_not_greedy_matching(self):
        # Greedy chooses 11 (distance 1) for forecast 10, then cannot
        # match forecast 15. Optimal pairs 10->8, 15->11 (2 matches).
        matched=m.match_events([10,15],[8,11],tolerance=4)
        self.assertEqual(matched["matched"],2)
        self.assertEqual(matched["missed_actual"],0)
        self.assertEqual(matched["false_predicted"],0)
        self.assertEqual(matched["sum_absolute_timing_error_seconds"],6)
        reversed_order=m.match_events([15,10],[11,8],tolerance=4)
        self.assertEqual(reversed_order,matched)

    def test_event_matching_is_one_to_one_and_penalizes_missed_and_extra(self):
        result=m.match_events([100,150,300],[103,306,500],tolerance=10)
        self.assertEqual(result["matched"],2)
        self.assertEqual(result["missed_actual"],1)
        self.assertEqual(result["false_predicted"],1)
        self.assertEqual(result["sum_absolute_timing_error_seconds"],9)

    def test_incremental_phase_replay_exactly_matches_original_v145(self):
        from research.v145_provider_continuous_phases import provider_continuous_phases
        from research.v128_full24_earliest_shadow import _gap_index
        OBS=m.OBS
        records=[
            OBS(100,0,"yata"),OBS(200,100,"yata"),
            OBS(300,80,"prometheus"),OBS(410,0,"prometheus"),
            OBS(520,0,"yata"),OBS(580,100,"yata"),
            OBS(700,90,"prometheus"),OBS(800,0,"prometheus"),
            OBS(900,60,"yata"),OBS(1100,0,"yata"),
            OBS(1200,75,"yata"),OBS(1250,0,"yata"),
        ]
        gaps=[(850,880)]
        tracker=m._ReplayPhases(_gap_index(gaps,1300))
        for j,obs in enumerate(records):
            tracker.add(obs)
            reference=provider_continuous_phases(records[:j+1],
                asof=obs.epoch,gaps=[g for g in gaps if g[0]<=obs.epoch])
            observed=tracker.asof()
            for key in ("phase","phase_onset","last_observation",
                        "stocked_durations","depleted_durations"):
                self.assertEqual(observed[key],reference[key],
                                 f"incremental mismatch at {j}: {key}")
        cross,events,ambiguous=m._replay_restock_index(records,gaps,1300)
        truth,amb=m.confirmed_restocks(records,gaps,start=99,end=1300)
        self.assertEqual(events,truth)
        self.assertEqual(len(ambiguous),amb)
        self.assertTrue(callable(cross))

    def test_recent_window_changes_only_past_phase_durations(self):
        p=phase(kind="LOW",age=200,low=1200,high=600)
        p["depleted_durations"]=[1200]*32+[3600]*8
        p["stocked_durations"]=[600]*32+[900]*8
        old=m.predict_events("mex:Jaguar Plushie",p,asof=ASOF)
        short=m.predict_events("mex:Jaguar Plushie",p,asof=ASOF,
                               recent_cycles=8)
        self.assertNotEqual(old["restock_events"][0]["predicted_restock_epoch"],
                            short["restock_events"][0]["predicted_restock_epoch"])
        self.assertEqual(short["cycle_window"],8)
        self.assertEqual(m.predict_events(
            "mex:Jaguar Plushie",dict(p,phase_onset=ASOF+1),
            asof=ASOF)["cycle_window"],"all")
        with self.assertRaises(ValueError):
            m.predict_events("mex:Jaguar Plushie",p,asof=ASOF,
                             recent_cycles=0)

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
            comparison=m.replay_events(source=src,asof=ASOF,days=1,
                 tolerance=600,roster=exact_roster(),
                 limit_items=2,cycle_windows=(8,16,32))
            for field in ("actual_observed_restocks","predicted_events",
                          "matched_timing","restock_recall","restock_precision"):
                self.assertEqual(result[field],comparison[field])
            self.assertEqual(set(comparison["recent_cycle_challengers"]),
                             {"recent_8","recent_16","recent_32"})
            for name,challenge in comparison["recent_cycle_challengers"].items():
                self.assertEqual(challenge["observed_restocks"],
                                 comparison["actual_observed_restocks"])
                self.assertLessEqual(challenge["matched_timing"],
                                     challenge["observed_restocks"])
                self.assertLessEqual(challenge["matched_timing"],
                                     challenge["forecast_restocks"])
            self.assertIn("CAUSAL CYCLE-HISTORY TOURNAMENT",
                          m.format_replay(comparison))
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
