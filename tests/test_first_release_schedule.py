"""Operation-sequence regressions for all ten first-release incumbents."""
from __future__ import annotations

from copy import deepcopy
from functools import partial
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from services.first_release_schedule import (
    FIRST_RELEASE_MODELS, MIN_QUANTITY, build_first_release_decision,
    forecast_first_release_item, freeze_trip, native_timing_choice,
)
from services.travel_decision_contract_v166 import STATUS_STALE, STATUS_ABSTAIN

NOW = 1_790_000_000


def event(restock, length=1800):
    return {"predicted_restock_epoch": restock,
            "restock_early_epoch": restock - 60,
            "restock_late_epoch": restock + 60,
            "predicted_stock_below_30_epoch": restock + length}


def forecast(key, events, current=None):
    return {"item_key": key, "asof_epoch": NOW,
            "flight_seconds": 1200, "arrival_stock_threshold": MIN_QUANTITY,
            "status": "EVENT_TIMELINE_FORECAST_AVAILABLE",
            "restock_events": events, "current_stock_window": current}


class FirstReleaseSequenceTests(unittest.TestCase):
    def plan(self, key, events, scorer=None, flight=1200, **kw):
        return build_first_release_decision(
            forecast(key, events, **kw), now=NOW, flight_seconds=flight,
            poll_age_seconds=0, timing_choice=scorer)

    def test_exact_frozen_roster_and_real_configurations_exist(self):
        from services import plushie_flower_dynamic_planner_v18 as v18
        from services import plushie_flower_dynamic_planner_v19 as v19
        self.assertEqual(10, len(FIRST_RELEASE_MODELS))
        self.assertEqual(8, sum(g == "v18" for g, _ in FIRST_RELEASE_MODELS.values()))
        for key, (generation, config) in FIRST_RELEASE_MODELS.items():
            with self.subTest(item=key):
                engine = v18 if generation == "v18" else v19
                self.assertIn(config, {c.name for c in engine.configs()})

    def test_all_ten_try_unreachable_events_then_first_reachable_only(self):
        events = [event(NOW + 100, 200), event(NOW + 300, 200),
                  event(NOW + 2400), event(NOW + 10000)]
        for key in FIRST_RELEASE_MODELS:
            with self.subTest(item=key):
                calls = []
                def score(**request):
                    calls.append(request)
                    return {"departure": NOW + request["delays"][-1], "score": .01}
                result = self.plan(key, events, score)
                self.assertEqual(3, result["selected_restock_event_index"])
                self.assertEqual(1, len(calls))
                self.assertLess(result["estimated_arrival_epoch"], NOW + 4200)
                self.assertGreaterEqual(result["estimated_arrival_epoch"], NOW + 2400)
                self.assertEqual([False, False, True, True],
                    [e["flight_reachable"] for e in result["forecast_events"]])
                self.assertEqual(FIRST_RELEASE_MODELS[key],
                    (calls[0]["generation"], calls[0]["config"]))

    def test_low_confidence_or_missing_timing_support_cannot_skip_reachable_event(self):
        for key in FIRST_RELEASE_MODELS:
            for scorer in (lambda **kw: None,
                           lambda **kw: {"departure": NOW + kw["delays"][0], "score": 0}):
                with self.subTest(item=key, scorer=scorer):
                    r = self.plan(key, [event(NOW + 2400), event(NOW + 10000)], scorer)
                    self.assertEqual(1, r["selected_restock_event_index"])
                    self.assertEqual(NOW + 1200, r["estimated_departure_epoch"])

    def test_later_event_or_early_arrival_returned_by_scorer_is_rejected(self):
        for key in FIRST_RELEASE_MODELS:
            for departure in (NOW + 1190, NOW + 8800, NOW + 2400.5):
                with self.subTest(item=key, departure=departure):
                    r = self.plan(key, [event(NOW + 2400), event(NOW + 10000)],
                                  lambda **kw: {"departure": departure, "score": 1})
                    self.assertEqual("REJECTED_OUTSIDE_FIRST_EVENT", r["timing_refinement_status"])
                    self.assertEqual(NOW + 1200, r["estimated_departure_epoch"])
                    self.assertEqual(NOW + 2400, r["estimated_arrival_epoch"])

    def test_current_stock_that_survives_flight_is_first_opportunity(self):
        for key in FIRST_RELEASE_MODELS:
            r = self.plan(key, [event(NOW + 10000)],
                          current=event(NOW - 600, 4000))
            self.assertEqual(0, r["selected_restock_event_index"])
            self.assertEqual(NOW, r["estimated_departure_epoch"])

    def test_current_stock_that_will_expire_does_not_block_future_restock(self):
        for key in FIRST_RELEASE_MODELS:
            r = self.plan(key, [event(NOW + 10000)], current=event(NOW - 600, 900))
            self.assertEqual(1, r["selected_restock_event_index"])

    def test_actual_flight_duration_changes_reachability_and_countdown(self):
        events = [event(NOW + 1000, 400), event(NOW + 10000)]
        a = self.plan("mex:Dahlia", events, flight=600)
        b = self.plan("mex:Dahlia", events, flight=1800)
        self.assertEqual(1, a["selected_restock_event_index"])
        self.assertEqual(2, b["selected_restock_event_index"])
        self.assertEqual(NOW + 400, a["estimated_departure_epoch"])
        self.assertEqual(NOW + 8200, b["estimated_departure_epoch"])

    def test_multi_day_forecast_is_not_suppressed_by_old_eight_hour_cap(self):
        for key in FIRST_RELEASE_MODELS:
            r = self.plan(key, [event(NOW + 3 * 86400)])
            self.assertEqual(NOW + 3 * 86400 - 1200, r["estimated_departure_epoch"])

    def test_unreachable_event_list_reports_no_window_without_inventing_one(self):
        r = self.plan("mex:Dahlia", [event(NOW + 10, 20)])
        self.assertIsNone(r["estimated_departure_epoch"])
        self.assertEqual("NO_REACHABLE_PREDICTED_WINDOW", r["status"])
        self.assertEqual(1, len(r["forecast_events"]))

    def test_stale_data_does_not_invoke_timing_model(self):
        f = forecast("mex:Dahlia", [event(NOW + 2400)])
        def forbidden(**kw):
            self.fail("stale forecast invoked timing model")
        for when, age in ((NOW + 300, 0), (NOW, 181)):
            r = build_first_release_decision(f, now=when, flight_seconds=1200,
                                            poll_age_seconds=age, timing_choice=forbidden)
            self.assertEqual(STATUS_STALE, r["status"])
            self.assertIsNone(r["estimated_departure_epoch"])

    def test_old_ge30_forecast_is_not_relabelled_as_gt30(self):
        f = forecast("mex:Dahlia", [event(NOW + 2400)])
        f["arrival_stock_threshold"] = 30
        r = build_first_release_decision(f, now=NOW, flight_seconds=1200,
                                        poll_age_seconds=0)
        self.assertEqual(STATUS_ABSTAIN, r["status"])
        self.assertIsNone(r["estimated_departure_epoch"])

    def test_input_not_mutated_and_frozen_trip_cannot_be_postponed_by_refresh(self):
        f = forecast("mex:Dahlia", [event(NOW + 2400)])
        original = deepcopy(f)
        r = build_first_release_decision(f, now=NOW, flight_seconds=1200,
                                        poll_age_seconds=0)
        self.assertEqual(original, f)
        trip = freeze_trip(r, opportunity_id="physical-opportunity-1")
        later = dict(r, estimated_departure_epoch=NOW + 20000,
                     estimated_arrival_epoch=NOW + 21200)
        self.assertEqual(trip, freeze_trip(later, opportunity_id="physical-opportunity-1", existing=trip))
        with self.assertRaises(ValueError):
            freeze_trip(later, opportunity_id="another-opportunity", existing=trip)


class FirstReleaseNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = tempfile.TemporaryDirectory()
        cls.source = Path(cls.scratch.name) / "synthetic.sqlite"
        cls.now = NOW
        start = NOW - 80 * 3600 - 300
        with sqlite3.connect(cls.source) as db:
            # Exercise the actual VM exporter schema, including its deliberate
            # omission of collection_gaps.reason, rather than a collector clone.
            from deploy.research_runner.export_snapshot import DDL
            db.executescript(DDL)
            rows = []
            for key in FIRST_RELEASE_MODELS:
                country, item = key.split(":", 1)
                rows.append((start, country, item, 0, "yata"))
                for i in range(80):
                    t = start + i * 3600
                    rows.extend((t + dt, country, item, qty, "yata") for dt, qty in
                                [(600, 200), (1800, 60), (2400, 30), (3000, 0)])
                rows.append((NOW, country, item, 0, "yata"))
            db.executemany("INSERT INTO stock_history(timestamp,country,item_name,quantity,source) VALUES(?,?,?,?,?)", rows)
            db.executemany("INSERT INTO poll_heartbeats(timestamp,mode,success,source) VALUES(?,'poll-cycle',1,'yata')",
                           [(t,) for t in range(start, NOW + 1, 60)])

    def test_sanitized_gap_adapter_preserves_boundaries_and_readonly_source(self):
        from services import history_service
        from services.frozen_candidate_worker_v31 import _install_frozen_readonly_history
        for with_reason in (False, True):
            with self.subTest(with_reason=with_reason), tempfile.TemporaryDirectory() as td:
                source = Path(td) / "gaps.sqlite"
                with sqlite3.connect(source) as db:
                    db.execute("CREATE TABLE collection_gaps(start_timestamp INTEGER,end_timestamp INTEGER" +
                               (",reason TEXT)" if with_reason else ")"))
                    db.execute("INSERT INTO collection_gaps VALUES(" +
                               ("100,200,'original reason')" if with_reason else "100,200)"))
                    db.execute("INSERT INTO collection_gaps VALUES(" +
                               ("300,NULL,'open gap')" if with_reason else "300,NULL)"))
                before = source.read_bytes()
                saved = {name: getattr(history_service, name) for name in
                         ("DB_PATH", "_connect", "init_db", "_DB_READY")}
                try:
                    _install_frozen_readonly_history(history_service, source)
                    gaps = history_service.get_collection_gaps()
                    self.assertEqual([(100, 200), (300, None)],
                        [(g['start_timestamp'], g['end_timestamp']) for g in gaps])
                    if with_reason:
                        self.assertEqual('original reason', gaps[0]['reason'])
                    self.assertEqual(100, history_service._collection_gap_overlap(150, 160)['start_timestamp'])
                    self.assertEqual(2, len(history_service._collection_gaps_overlapping(150, 350)))
                    with history_service._connect() as db:
                        self.assertEqual(1, db.execute('PRAGMA query_only').fetchone()[0])
                        with self.assertRaises(sqlite3.OperationalError):
                            db.execute('DELETE FROM main.collection_gaps')
                finally:
                    for name, value in saved.items():
                        setattr(history_service, name, value)
                self.assertEqual(before, source.read_bytes())

    @classmethod
    def tearDownClass(cls):
        cls.scratch.cleanup()

    def test_real_native_configuration_for_every_item_with_no_source_writes(self):
        from services import history_service
        before = self.source.read_bytes()
        original_connect = history_service._connect
        refined = []
        # Actual V18/V19 load_item, cycle extraction, features, config and plan.
        # This is a small deterministic integration fixture, not accuracy evidence.
        for key in FIRST_RELEASE_MODELS:
            with self.subTest(item=key):
                f = forecast(key, [event(NOW + 10000), event(NOW + 20000)])
                r = build_first_release_decision(
                    f, now=NOW, flight_seconds=1200, poll_age_seconds=0,
                    timing_choice=partial(native_timing_choice, self.source))
                self.assertEqual(1, r["selected_restock_event_index"])
                self.assertEqual("REFINED_WITHIN_FIRST_EVENT", r["timing_refinement_status"])
                self.assertTrue(NOW + 10000 <= r["estimated_arrival_epoch"] < NOW + 11800)
                self.assertIs(original_connect, history_service._connect)
                refined.append(key)
        self.assertEqual(10, len(refined))
        self.assertEqual(before, self.source.read_bytes())

    def test_real_event_forecast_to_native_schedule_all_ten(self):
        from research.plushie_champions.common import TRAVEL_SECONDS
        for key in FIRST_RELEASE_MODELS:
            with self.subTest(item=key):
                r = forecast_first_release_item(self.source, key, now=NOW,
                    flight_seconds=TRAVEL_SECONDS[key.split(":", 1)[0]])
                d = r["decision"]
                reachable = [e for e in d["forecast_events"] if e["flight_reachable"]]
                self.assertTrue(reachable)
                self.assertEqual(reachable[0]["index"], d["selected_restock_event_index"])
                self.assertEqual(31, r["forecast"]["arrival_stock_threshold"])
                self.assertEqual(31, d["target_quantity"])
                self.assertFalse(r["collector_written"])
                self.assertFalse(r["production_deployed"])

    def test_native_adapter_restores_globals_after_error(self):
        from services import history_service
        from services import plushie_flower_dynamic_planner_v18 as engine
        before = history_service._connect
        with patch.object(engine, "load_item", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                native_timing_choice(self.source, item_key="mex:Dahlia", generation="v18",
                    config="dyn2", now=NOW, flight_seconds=1200,
                    min_quantity=31, delays=(0,))
        self.assertIs(before, history_service._connect)

    def test_exactly_30_is_not_a_stocked_phase_for_this_release(self):
        from deploy.scripts.v163_readonly_event_first_preview import OBS
        from research.v145_provider_continuous_phases import provider_continuous_phases
        rows = [OBS(NOW - 300, 0, "yata"), OBS(NOW - 200, 30, "yata"),
                OBS(NOW - 100, 31, "yata"), OBS(NOW, 30, "yata")]
        p = provider_continuous_phases(rows, asof=NOW, min_qty=31)
        self.assertEqual("LOW", p["phase"])
        self.assertEqual([(NOW - 100, NOW)], p["observed_bounded_stocked_windows"])


if __name__ == "__main__":
    unittest.main()
