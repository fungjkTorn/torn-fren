"""V126 keeps unknown phase starts unknown while providing sensitivity only."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from research import v126_unknown_onset_sensitivity as m
from research.v107_explicit_restock_cycle_baseline import StockObservation

T0=1700000000
ITEM="uni:Nessie Plushie"


def source_switch_series():
    t=T0
    arr=[StockObservation(t,0,"yata")]
    for _ in range(20):
        t+=7200;arr.append(StockObservation(t,200,"yata"))
        t+=3600;arr.append(StockObservation(t,0,"yata"))
    t+=7200;arr.append(StockObservation(t,75,"yata"))
    t+=200;arr.append(StockObservation(t,70,"prometheus"))
    return arr,t


def file_digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class UnknownOnsetTests(unittest.TestCase):
    def test_switch_does_not_forge_last_high_onset(self):
        seq,t=source_switch_series()
        r=m.hypothetical_unknown_onset_curve(
            seq,ITEM,asof=t+131,scenarios=64)
        self.assertEqual(r["status"],"UNCERTAIN_ORIGIN_EXPLORATORY_CURVE")
        self.assertIsNone(r["observed_phase_onset"])
        self.assertFalse(r["phase_start_imputed"])
        self.assertEqual(r["historical_phase"],"HIGH")
        self.assertEqual(
            r["bounds"]["known_uninterrupted_observed_age_lower_bound_seconds"],
            131)
        self.assertEqual(r["bounds"]["observed_item_change_rows_in_segment"],1)
        self.assertEqual(len(r["scores"]),97)
        self.assertTrue(all(0<=v<=1 for v in r["scores"]))
        self.assertFalse(r["scores_are_calibrated_probabilities"]
                         if "scores_are_calibrated_probabilities" in r else False)
        self.assertFalse(r["source_country_freshness_verified"])

    def test_real_observed_threshold_is_not_replaced_or_reinterpreted(self):
        seq,t=source_switch_series()
        seq.append(StockObservation(t+200,0,"prometheus"))
        seq.append(StockObservation(t+500,60,"prometheus"))
        r=m.hypothetical_unknown_onset_curve(
            seq,ITEM,asof=t+600,scenarios=16)
        self.assertEqual(r["status"],"NOT_AN_UNKNOWN_ONSET")
        self.assertEqual(r["observed_phase_onset"],t+500)

    def test_known_collection_gap_resets_lower_bound(self):
        seq,t=source_switch_series()
        seq.append(StockObservation(t+300,65,"prometheus"))
        gaps=[(t+100,t+200)]
        b=m.source_segment_duration(seq,gaps,asof=t+400)
        self.assertEqual(b["first_uninterrupted_observation_epoch"],t+300)
        self.assertEqual(b["known_uninterrupted_observed_age_lower_bound_seconds"],100)

    def test_no_future_stock_used(self):
        seq,t=source_switch_series()
        with self.assertRaisesRegex(ValueError,"invalid hypothetical"):
            m.hypothetical_unknown_onset_curve(
                seq,ITEM,asof=t-1)
        with self.assertRaises(ValueError):
            m.hypothetical_unknown_onset_curve(
                seq,"jap:Xanax",asof=t+131)

    def test_preview_never_mutates_source_or_adds_sidecar(self):
        seq,t=source_switch_series()
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/"collector.db"
            side=Path(tmp)/"prospective.db"
            with sqlite3.connect(src) as db:
                db.execute("""CREATE TABLE stock_history(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER,quantity INTEGER,source TEXT,
                    country TEXT,item_name TEXT)""")
                db.execute("""CREATE TABLE poll_heartbeats(
                    timestamp INTEGER,source TEXT,mode TEXT,success INTEGER)""")
                db.execute("""CREATE TABLE collection_gaps(
                    start_timestamp INTEGER,end_timestamp INTEGER)""")
                for _,name in m.TARGETS.values():
                    db.executemany("""INSERT INTO stock_history (
                        timestamp,quantity,source,country,item_name)
                        VALUES (?,?,?,'uni',?)""",[
                        (o.epoch,o.quantity,o.source,name) for o in seq
                    ])
                db.execute("""INSERT INTO poll_heartbeats(
                    timestamp,source,mode,success
                ) VALUES (?,'yata','poll-cycle',1)""",(t+131,))
                db.commit()
            before=file_digest(src)
            result=m.read_only_preview(
                source=src,sidecar=side,now=t+131,enforce=False)
            self.assertEqual(result["status"],
                "V126_UNKNOWN_ORIGIN_READ_ONLY_SENSITIVITY_PREVIEW")
            self.assertEqual(file_digest(src),before)
            self.assertFalse(side.exists())
            self.assertEqual(result["written_databases"],0)
            for key,rec in result["unknown_phase_diagnostics"].items():
                self.assertEqual(rec["status"],
                    "UNCERTAIN_ORIGIN_EXPLORATORY_CURVE")
                self.assertFalse(rec["is_actionable_departure"])
                self.assertFalse(rec["replaces_v125_recommendation"])
                self.assertIsNone(result["original_v125"][
                    "as_issued_model_recommendations"][key]["earliest_departure"])

    def test_stale_global_heartbeat_has_no_model_preview(self):
        seq,t=source_switch_series()
        with tempfile.TemporaryDirectory() as tmp:
            dbpath=Path(tmp)/"stock.db"
            with sqlite3.connect(dbpath) as db:
                db.execute("""CREATE TABLE poll_heartbeats(
                    timestamp INTEGER,source TEXT,mode TEXT,success INTEGER)""")
                db.execute("""CREATE TABLE stock_history(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER,quantity INTEGER,source TEXT,
                    country TEXT,item_name TEXT)""")
                db.execute("""CREATE TABLE collection_gaps(
                    start_timestamp INTEGER,end_timestamp INTEGER)""")
                db.execute("""INSERT INTO poll_heartbeats(
                    timestamp,source,mode,success)
                    VALUES (?,'yata','poll-cycle',1)""",(t,))
                db.commit()
            result=m.read_only_preview(
                source=dbpath,sidecar=Path(tmp)/"side.db",
                now=t+1000,enforce=False)
            self.assertEqual(result["status"],"V126_STALE_GLOBAL_HEARTBEAT")
            self.assertFalse(result["unknown_phase_diagnostics"])


if __name__=="__main__":
    unittest.main()
