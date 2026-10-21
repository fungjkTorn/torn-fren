"""V124: source remains read-only, sidecar strictly isolated and opt-in."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research import v124_prospective_survival_shadow as m
from research.v107_explicit_restock_cycle_baseline import StockObservation

T0=1700000000


def build_stock(dbfile):
    with sqlite3.connect(dbfile) as db:
        db.execute("""CREATE TABLE stock_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER,quantity INTEGER,
            source TEXT,country TEXT,item_name TEXT)""")
        db.execute("""CREATE TABLE poll_heartbeats(
            id INTEGER PRIMARY KEY,
            timestamp INTEGER,source TEXT,mode TEXT,success INTEGER)""")
        db.execute("""CREATE TABLE collection_gaps(
            start_timestamp INTEGER,end_timestamp INTEGER)""")
        t=T0
        for country,item in m.TARGETS.values():
            t=T0
            db.execute("""INSERT INTO stock_history(
                timestamp,quantity,source,country,item_name)
                VALUES (?,?,?,?,?)""",
                (t,0,"yata",country,item))
            for _ in range(21):
                t+=7200
                db.execute("""INSERT INTO stock_history(
                    timestamp,quantity,source,country,item_name)
                    VALUES (?,?,?,?,?)""",
                    (t,300,"yata",country,item))
                t+=3600
                db.execute("""INSERT INTO stock_history(
                    timestamp,quantity,source,country,item_name)
                    VALUES (?,?,?,?,?)""",
                    (t,0,"yata",country,item))
        db.execute("""INSERT INTO poll_heartbeats(
            timestamp,source,mode,success) VALUES (?,'yata','poll-cycle',1)""",
            (t+100,))
        db.commit()
    return t+100


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ProspectiveShadowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source=Path(self.temp.name)/"stock.db"
        self.sidecar=Path(self.temp.name)/"v124_private.db"
        self.issue=build_stock(self.source)

    def run_once(self,*,record=False,issued=None):
        return m.observe(source=self.source,sidecar=self.sidecar,
                         issued=self.issue if issued is None else issued,
                         enforce_canonical=False,record=record)

    def test_default_preview_does_not_write_collector_or_sidecar(self):
        before=sha256(self.source)
        result=self.run_once()
        self.assertEqual(result["status"],"V124_PREVIEW_NO_WRITES")
        self.assertFalse(self.sidecar.exists())
        self.assertEqual(sha256(self.source),before)
        self.assertFalse(result["provider_country_freshness_verified"])
        self.assertEqual(len(result["items"]),2)
        for rec in result["items"].values():
            self.assertEqual(rec["status"],"ISSUED_MODEL_FORECAST")
            self.assertFalse(rec["source_country_age_verified"])
            self.assertTrue(rec["model_evidence_only_persisted_by_issued_at"])
            self.assertEqual(rec["issued_at"],self.issue)
            self.assertEqual(rec["baseline_departure"],self.issue)
            if rec["recommended_departure"] is not None:
                self.assertGreaterEqual(rec["recommended_departure"],self.issue)
                self.assertLessEqual(rec["recommended_departure"]-self.issue,
                                     28800)

    def test_record_creates_private_only_idempotent_issued_snapshot(self):
        before=sha256(self.source)
        first=self.run_once(record=True)
        self.assertEqual(first["status"],"V124_SHADOW_RECORDED")
        self.assertTrue(self.sidecar.exists())
        self.assertEqual(sha256(self.source),before)
        with sqlite3.connect(self.sidecar) as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM v124_forecasts").fetchone()[0],2)
            self.assertEqual(db.execute(
                "SELECT count(*) FROM v124_issue_attempts").fetchone()[0],2)
            for (payload,) in db.execute(
                "SELECT payload_json FROM v124_forecasts"):
                value=json.loads(payload)
                self.assertEqual(value["issued_at"],self.issue)
                self.assertEqual(value["policy_id"],m.POLICY_ID)
        second=self.run_once(record=True)
        self.assertEqual(second["status"],"V124_SHADOW_RECORDED")
        with sqlite3.connect(self.sidecar) as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM v124_forecasts").fetchone()[0],2)
            self.assertEqual(db.execute(
                "SELECT count(*) FROM v124_issue_attempts").fetchone()[0],2)

    def test_second_tick_same_depletion_logs_attempt_not_second_model(self):
        self.run_once(record=True)
        with sqlite3.connect(self.source) as db:
            db.execute("""INSERT INTO poll_heartbeats(
                timestamp,source,mode,success)
                VALUES (?,'yata','poll-cycle',1)""",(self.issue+300,))
            db.commit()
        self.run_once(record=True,issued=self.issue+300)
        with sqlite3.connect(self.sidecar) as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM v124_forecasts").fetchone()[0],2)
            self.assertEqual(db.execute(
                "SELECT count(*) FROM v124_issue_attempts").fetchone()[0],4)

    def test_global_stale_heartbeat_prevents_model_forecast(self):
        result=self.run_once(issued=self.issue+1800)
        self.assertEqual(result["global_heartbeat_age_seconds"],1800)
        for rec in result["items"].values():
            self.assertEqual(rec["status"],
                             "GLOBAL_COLLECTOR_HEARTBEAT_STALE")
        self.assertFalse(self.sidecar.exists())

    def test_old_depletion_not_issued_even_if_global_poll_recent(self):
        with sqlite3.connect(self.source) as db:
            db.execute("""INSERT INTO poll_heartbeats(
                timestamp,source,mode,success)
                VALUES (?,'yata','poll-cycle',1)""",(self.issue+1200,))
            db.commit()
        result=self.run_once(issued=self.issue+1200)
        for rec in result["items"].values():
            self.assertEqual(rec["status"],"DEPLETION_TOO_OLD")
        self.assertFalse(self.sidecar.exists())

    def test_interpolation_and_no_horizon_extrapolation(self):
        aligned=m.parse_and_align({
            "status":"EMPIRICAL_STOCK_SURVIVAL_CURVE",
            "delay_seconds":[0,300,600,900],
            "scores":[0,.2,.8,.4],
        },issued=T0+150,model_asof=T0)
        self.assertEqual(aligned["delay_seconds"],[0,300,600])
        self.assertEqual(aligned["immediate_arrival_score"],.1)
        self.assertEqual(aligned["scores"][1],.5)
        self.assertEqual(aligned["scores"][2],.6)
        self.assertFalse(aligned["scores_recalibrated"])
        with self.assertRaises(ValueError):
            m.parse_and_align({
                "status":"EMPIRICAL_STOCK_SURVIVAL_CURVE",
                "delay_seconds":[0,300],"scores":[0,1]
            },issued=T0+601,model_asof=T0)

    def test_canonical_path_lockdown_rejects_alternate_sidecar(self):
        with self.assertRaises(ValueError):
            m.preflight(source=self.source,sidecar=self.sidecar,
                        enforce_canonical=True)
        with self.assertRaises(ValueError):
            m.preflight(source=self.source,sidecar=self.source,
                        enforce_canonical=False)

    def test_never_uses_future_rows_as_model_training(self):
        series=[StockObservation(T0,0,"yata"),
                StockObservation(T0+300,100,"yata")]
        out=m.proposal("uni:Nessie Plushie",series,[],
                       issued=T0+200)
        self.assertEqual(out["status"],"FUTURE_STOCK_ROW_REJECTED")


if __name__=="__main__":
    unittest.main()
