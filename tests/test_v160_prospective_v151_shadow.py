"""V160 prospective 24-item issue snapshot; only private opt-in ledger writes."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.v128_full24_earliest_shadow import exact_roster
from research.plushie_champions.common import TRAVEL_SECONDS
from research.v160_prospective_v151_shadow import (
    capture_once,POLICY,_source,write_private_sidecar,
)

T=1791800400


def collector_fixture(directory,issued=T):
    source=directory/"stock.db"
    with sqlite3.connect(source) as conn:
        conn.executescript("""
        CREATE TABLE stock_history(
            id INTEGER PRIMARY KEY,
            timestamp INTEGER,quantity INTEGER,source TEXT,
            country TEXT,item_name TEXT);
        CREATE TABLE collection_gaps(
            start_timestamp INTEGER,end_timestamp INTEGER);
        CREATE TABLE poll_heartbeats(
            id INTEGER PRIMARY KEY,timestamp INTEGER,
            mode TEXT,success INTEGER);
        """)
        conn.execute("INSERT INTO poll_heartbeats(timestamp,mode,success) VALUES(?,?,?)",
                     (issued-15,"poll-cycle",1))
        for key in exact_roster():
            country,item=key.split(":",1)
            conn.executemany(
                "INSERT INTO stock_history(timestamp,quantity,source,country,item_name)"
                " VALUES(?,?,?,?,?)",
                [(issued-1000,0,"yata",country,item),
                 (issued-900,100,"yata",country,item),
                 (issued-300,0,"yata",country,item),
                 (issued-10,100,"yata",country,item)])
    return source


def model(key,periods,*,asof,scenarios,cycle_sampling,
          departure_step_seconds=300):
    assert asof==T and 8<=scenarios<=96
    offset=600 if cycle_sampling=="paired_complete" else 0
    flight=TRAVEL_SECONDS[key.split(":",1)[0]]
    return {
        "status":"PROVISIONAL_SCENARIO_SUPPORTED_DEPARTURE",
        "first_reachable":{
            "departure_epoch":T+offset,
            "arrival_epoch":T+offset+flight,
            "wait_seconds":offset,
            "scenario_stock_fraction":.75,
        },
    }


class PrivateProspectiveShadowTests(unittest.TestCase):
    def test_preview_does_not_write_any_file_and_captures_24_issued_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=collector_fixture(root)
            dst=root/"v160_v151_prospective24.db"
            with patch("research.v160_prospective_v151_shadow.stable_earliest_departure",
                       side_effect=model):
                result=capture_once(
                    source=source,destination=dst,
                    canonical=False,issued_epoch=T,record=False,
                    now_fn=lambda:T,mono_fn=lambda:10,scenarios=8)
            self.assertFalse(dst.exists())
            self.assertEqual(result["roster_count"],24)
            self.assertEqual(len(result["predictions"]),24)
            self.assertEqual(result["source_heartbeat_age_seconds"],15)
            self.assertTrue(result["research_only"])
            self.assertFalse(result["private_sidecar_written"])
            self.assertFalse(result["incumbent_forecasts_verified"])
            self.assertEqual(result["policy_id"],POLICY)
            for key,rec in result["predictions"].items():
                self.assertEqual(rec["phase"],"HIGH")
                self.assertEqual(rec["phase_onset"],T-10)
                self.assertFalse(rec["incumbent_forecast_evaluated"])
                self.assertFalse(rec["published_to_website"])
                for variant,d in rec["models"].items():
                    self.assertEqual(d["arrival_epoch"]-d["departure_epoch"],
                                     TRAVEL_SECONDS[key.split(":",1)[0]])
                    self.assertEqual(d["wait_seconds"],600 if variant=="paired_complete" else 0)

    def test_record_writes_only_private_sidecar_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=collector_fixture(root)
            dst=root/"v160_v151_prospective24.db"
            with patch("research.v160_prospective_v151_shadow.stable_earliest_departure",
                       side_effect=model):
                result=capture_once(
                    source=source,destination=dst,canonical=False,
                    issued_epoch=T,record=True,now_fn=lambda:T,
                    mono_fn=lambda:10,scenarios=8)
                with self.assertRaisesRegex(ValueError,"duplicate issue epoch"):
                    capture_once(source=source,destination=dst,canonical=False,
                                 issued_epoch=T,record=True,now_fn=lambda:T,
                                 mono_fn=lambda:10,scenarios=8)
            self.assertTrue(dst.exists())
            with sqlite3.connect(dst) as conn:
                ticks=conn.execute("SELECT COUNT(*) FROM v160_ticks").fetchone()[0]
                records=conn.execute("SELECT COUNT(*) FROM v160_issued").fetchone()[0]
                raw=conn.execute("SELECT payload_json FROM v160_issued LIMIT 1").fetchone()[0]
            self.assertEqual((ticks,records),(1,24))
            self.assertEqual(json.loads(raw)["issued_epoch"],T)
            self.assertEqual(source.stat().st_size>0,True)
            self.assertTrue(result["private_sidecar_written"])

    def test_stale_collector_has_24_explicit_abstentions_not_fabricated_flights(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            src=collector_fixture(root)
            with sqlite3.connect(src) as conn:
                conn.execute("UPDATE poll_heartbeats SET timestamp=?",(T-500,))
            out=capture_once(
                source=src,destination=root/"v160_v151_prospective24.db",
                canonical=False,issued_epoch=T,now_fn=lambda:T,
                mono_fn=lambda:10)
            self.assertEqual(out["roster_count"],24)
            self.assertEqual(
                {rec["decision_status"] for rec in out["predictions"].values()},
                {"ABSTAIN_STALE_HEARTBEAT_OR_GAPS"})
            self.assertTrue(all(
                m["departure_epoch"] is None
                for x in out["predictions"].values()
                for m in x["models"].values()))

    def test_stale_run_over_90_seconds_fail_closes_all_24(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            src=collector_fixture(root)
            with patch("research.v160_prospective_v151_shadow.stable_earliest_departure",
                       side_effect=model):
                out=capture_once(
                    source=src,destination=root/"v160_v151_prospective24.db",
                    canonical=False,issued_epoch=T,
                    now_fn=iter([T,T+120]).__next__,
                    mono_fn=lambda:10,scenarios=8)
            self.assertTrue(all(
                x["decision_status"]=="ABSTAIN_OVERDUE_CAPTURE"
                for x in out["predictions"].values()))
            self.assertFalse((root/"v160_v151_prospective24.db").exists())

    def test_source_identity_and_private_file_name_reject_unsafe_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            src=collector_fixture(root)
            with self.assertRaises(ValueError):
                _source(src,src,canonical=False)
            with self.assertRaises(ValueError):
                _source(src,root/"v160_v151_prospective24.db",canonical=True)
            with self.assertRaises(ValueError):
                write_private_sidecar(root/"stock.db",{"predictions":{}})
            with self.assertRaises(ValueError):
                capture_once(source=src,destination=src,
                             canonical=False,issued_epoch=T,now_fn=lambda:T)
            with self.assertRaises(ValueError):
                capture_once(source=src,
                    destination=root/"v160_v151_prospective24.db",
                    canonical=False,issued_epoch=T-100,
                    now_fn=lambda:T)


if __name__=="__main__":
    unittest.main()
