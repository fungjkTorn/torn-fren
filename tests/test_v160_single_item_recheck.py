"""User-triggered single-item model updates use read-only live collector as-of."""
import hashlib
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research.plushie_champions.common import TRAVEL_SECONDS
from research.v128_full24_earliest_shadow import _read_item,exact_roster
from research.v60_private_snapshot_probe import read_heartbeat
from research.v145_provider_continuous_phases import provider_continuous_phases
from test_v160_prospective_v151_shadow import T,collector_fixture

ROOT=Path(__file__).resolve().parents[1]
FILE=ROOT/"deploy/scripts/v160_single_item_recheck.py"
spec=importlib.util.spec_from_file_location("single_item_recheck",FILE)
worker=importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
ITEM="mex:Jaguar Plushie"


def model(key,periods,*,asof,scenarios,cycle_sampling):
    assert key==ITEM and asof==T and scenarios==48
    flight=TRAVEL_SECONDS[key.split(":",1)[0]]
    delay=0 if cycle_sampling=="independent" else 600
    return {
        "status":"PROVISIONAL_SCENARIO_SUPPORTED_DEPARTURE",
        "first_reachable":{
            "departure_epoch":asof+delay,
            "arrival_epoch":asof+delay+flight,
            "scenario_stock_fraction":0.72,
            "two_adjacent_5min_bins":True,
            "needs_reconfirmation":delay>300,
        },
    }


class SingleItemRecheckTests(unittest.TestCase):
    def test_exact_now_single_item_no_ledger_or_collector_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            collector=collector_fixture(root)
            ledger=root/"v160_v151_prospective24.db"
            roster=ROOT/"research/v38_roster.json"
            before=hashlib.sha256(collector.read_bytes()).hexdigest()
            modules=(TRAVEL_SECONDS,_read_item,read_heartbeat,
                     provider_continuous_phases,model)
            out=worker.recheck(ITEM,now_fn=lambda:T,mono_fn=lambda:10,
                               source=collector,roster=roster,modules=modules)
            self.assertEqual(out["status"],"CURRENT_ITEM_RECHECK_RESEARCH_ONLY")
            self.assertEqual(out["source_heartbeat_age_seconds"],15)
            self.assertEqual(out["source_last_quantity"],100)
            self.assertEqual(out["flight_seconds"],1020)
            self.assertEqual(out["models"]["independent"]["departure_epoch"],T)
            self.assertEqual(out["models"]["paired_complete"]["departure_epoch"],T+600)
            self.assertTrue(out["models"]["independent"]["sustained_five_minute_support"])
            self.assertFalse(out["private_ledger_written"])
            self.assertTrue(out["forecast_not_prospectively_recorded"])
            self.assertFalse(out["country_source_freshness_verified"])
            self.assertFalse(out["real_player_arrival_verified"])
            self.assertEqual(before,hashlib.sha256(collector.read_bytes()).hexdigest())
            self.assertFalse(ledger.exists())

    def test_on_demand_recheck_emits_all_restocks_not_only_first_eligible_flight(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            collector=collector_fixture(root)
            modules=(TRAVEL_SECONDS,_read_item,read_heartbeat,
                     provider_continuous_phases,model)
            calls=[]
            def events(key,history,*,asof):
                calls.append((key,asof))
                return {"item_key":key,"asof_epoch":asof,
                    "status":"EVENT_TIMELINE_FORECAST_AVAILABLE",
                    "restock_events":[
                        {"event_index":1,"predicted_restock_epoch":asof+600,
                         "expected_departure_epoch":None,
                         "reason":"MODELED_RESTOCK_NOT_REACHABLE_WITH_CURRENT_FLIGHT"},
                        {"event_index":2,"predicted_restock_epoch":asof+2400,
                         "expected_departure_epoch":asof+360,
                         "reason":"MODELED_REACHABLE_RECONFIRM"}],
                    "forecast_event_count":2,
                    "restock_accuracy_verified":False}
            report=worker.recheck(ITEM,source=collector,
                                  roster=ROOT/"research/v38_roster.json",
                                  modules=modules,now_fn=lambda:T,
                                  event_planner=events)
            self.assertEqual(calls,[(ITEM,T)])
            self.assertEqual(report["restock_timeline"]["forecast_event_count"],2)
            self.assertIsNone(report["restock_timeline"]["restock_events"][0]
                              ["expected_departure_epoch"])
            self.assertEqual(report["restock_timeline"]["restock_events"][1]
                             ["expected_departure_epoch"],T+360)
            self.assertFalse(report["forecast_not_prospectively_recorded"] is False)
            self.assertFalse((root/"v160_v151_prospective24.db").exists())

    def test_reject_unknown_item_and_stale_source_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=collector_fixture(Path(tmp))
            mods=(TRAVEL_SECONDS,_read_item,read_heartbeat,
                  provider_continuous_phases,model)
            base={"source":source,"roster":ROOT/"research/v38_roster.json",
                  "modules":mods}
            with self.assertRaisesRegex(ValueError,"unknown item"):
                worker.recheck("mex:Not a Real Item",now_fn=lambda:T,**base)
            with self.assertRaisesRegex(ValueError,"stale"):
                worker.recheck(ITEM,now_fn=lambda:T+200,**base)

    def test_staged_package_entrypoint_valid_and_geometry_matches_model(self):
        travel,*others=worker.pinned_modules(
            stage=ROOT/"research",work=ROOT)
        self.assertEqual(travel,TRAVEL_SECONDS)
        self.assertEqual(set(exact_roster()),
                         set(json.loads((ROOT/"research/v38_roster.json").read_text())["items"])
                         |worker.EXTRA)
        for item in exact_roster():
            self.assertIn(item.split(":",1)[0],travel)


if __name__=="__main__":
    unittest.main()
