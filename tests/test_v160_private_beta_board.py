"""Standalone V160 private live beta must only use honest, read-only issuance."""
import hashlib
import importlib.util
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"deploy/scripts/v160_private_beta_board.py"
spec=importlib.util.spec_from_file_location("v160_beta_board",SCRIPT)
board=importlib.util.module_from_spec(spec)
spec.loader.exec_module(board)
ISSUED=1791910560


def fixture(root):
    ledger=root/"v160_v151_prospective24.db"
    roster=root/"roster.json"
    names={}
    from research.v128_full24_earliest_shadow import exact_roster
    names={k:{"category":"plushie"} for k in exact_roster()}
    roster.write_text(json.dumps({"items":names}),encoding="utf-8")
    with closing(sqlite3.connect(ledger)) as db:
        db.executescript("""
            CREATE TABLE v160_ticks(issued_epoch INTEGER PRIMARY KEY,
                captured_epoch INTEGER,source_heartbeat_epoch INTEGER,
                roster_count INTEGER,policy_id TEXT);
            CREATE TABLE v160_issued(item_key TEXT,issued_epoch INTEGER,
                policy_id TEXT,payload_json TEXT,
                PRIMARY KEY(item_key,issued_epoch,policy_id));
        """)
        db.execute("INSERT INTO v160_ticks VALUES(?,?,?,?,?)",
                   (ISSUED,ISSUED+6,ISSUED-4,24,board.POLICY))
        for item_key in names:
            country=item_key.split(":",1)[0]
            payload={
                "item_key":item_key,"issued_epoch":ISSUED,
                "policy_id":board.POLICY,
                "research_only":True,
                "published_to_website":False,
                "source_last_qty":38,
                "models":{
                    "independent":{
                        "departure_epoch":ISSUED+600,
                        "arrival_epoch":ISSUED+600+board.FLIGHTS[country],
                        "wait_seconds":600,"status":"RESEARCH_WATCH_RECONFIRM",
                        "scenario_fraction":0.67},
                    "paired_complete":{
                        "departure_epoch":ISSUED+900,
                        "arrival_epoch":ISSUED+900+board.FLIGHTS[country],
                        "wait_seconds":900,"status":"RESEARCH_WATCH_RECONFIRM",
                        "scenario_fraction":0.8},
                }
            }
            db.execute("INSERT INTO v160_issued VALUES(?,?,?,?)",
                       (item_key,ISSUED,board.POLICY,json.dumps(payload)))
        db.commit()
    return ledger,roster


class PrivateBetaBoardTests(unittest.TestCase):
    def test_24_live_candidates_exact_flight_and_no_db_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger,roster=fixture(Path(tmp))
            before=hashlib.sha256(ledger.read_bytes()).hexdigest()
            output=board.snapshot(ledger,roster,now=ISSUED+45)
            self.assertTrue(output["healthy"])
            self.assertEqual(output["recorded_items"],24)
            self.assertEqual(len(output["items"]),24)
            self.assertEqual(output["source_heartbeat_age_seconds"],4)
            self.assertFalse(output["actual_player_flights_verified"])
            self.assertFalse(output["country_provider_freshness_verified"])
            self.assertTrue(output["research_only"])
            self.assertEqual(output["min_arrival_stock"],30)
            for row in output["items"]:
                self.assertTrue(row["available"])
                self.assertEqual(row["source_quantity"],38)
                self.assertEqual(row["models"]["independent"]["departure"],ISSUED+600)
                self.assertEqual(row["models"]["paired_complete"]["departure"],ISSUED+900)
                self.assertEqual(
                    row["models"]["paired_complete"]["arrival"]-
                    row["models"]["paired_complete"]["departure"],
                    row["flight_seconds"])
            self.assertEqual(hashlib.sha256(ledger.read_bytes()).hexdigest(),before)

    def test_stale_tick_hides_all_departure_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger,roster=fixture(Path(tmp))
            output=board.snapshot(ledger,roster,now=ISSUED+661)
            self.assertFalse(output["healthy"])
            self.assertTrue(all(not row["available"] for row in output["items"]))
            self.assertTrue(all(v["departure"] is None and v["arrival"] is None
                for row in output["items"] for v in row["models"].values()))

    def test_past_departures_not_offered_even_when_batch_fresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger,roster=fixture(Path(tmp))
            output=board.snapshot(ledger,roster,now=ISSUED+920)
            self.assertFalse(output["healthy"])
            self.assertTrue(all(row["models"]["independent"]["departure"] is None
                for row in output["items"]))

    def test_no_partial_or_foreign_roster_batch_can_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger,roster=fixture(Path(tmp))
            with closing(sqlite3.connect(ledger)) as db:
                db.execute("DELETE FROM v160_issued WHERE item_key=("
                           "SELECT item_key FROM v160_issued LIMIT 1)")
                db.commit()
            with self.assertRaisesRegex(ValueError,"incomplete"):
                board.snapshot(ledger,roster,now=ISSUED+5)

    def test_tampered_flight_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger,roster=fixture(Path(tmp))
            with closing(sqlite3.connect(ledger)) as db:
                key,payload=db.execute("SELECT item_key,payload_json FROM v160_issued LIMIT 1").fetchone()
                value=json.loads(payload)
                value["models"]["independent"]["arrival_epoch"]+=300
                db.execute("UPDATE v160_issued SET payload_json=? WHERE item_key=?",
                           (json.dumps(value),key))
                db.commit()
            with self.assertRaisesRegex(ValueError,"flight geometry"):
                board.snapshot(ledger,roster,now=ISSUED+5)

    def test_unconfigured_ledger_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with self.assertRaisesRegex(ValueError,"ledger missing"):
                board.snapshot(root/"never_created.db",root/"nothing.json")
            self.assertEqual(list(root.iterdir()),[])

    def test_loopback_http_returns_html_and_public_safe_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger,roster=fixture(Path(tmp))
            with ThreadingHTTPServer(("127.0.0.1",0),
                 board.handler_factory(ledger,roster)) as server:
                thread=threading.Thread(target=server.serve_forever,daemon=True)
                thread.start()
                base="http://127.0.0.1:"+str(server.server_port)
                try:
                    with urlopen(base+"/",timeout=3) as response:
                        page=response.read().decode()
                        self.assertEqual(response.status,200)
                        self.assertIn("Live research beta",page)
                        self.assertIn("Research-only",page)
                    with self.assertRaises(HTTPError) as exc:
                        urlopen(base+"/api/live",timeout=3)
                    self.assertEqual(exc.exception.code,503)
                    data=json.loads(exc.exception.read())
                    self.assertEqual(data["recorded_items"],24)
                    self.assertFalse(data["healthy"])
                    self.assertNotIn("payload_json",json.dumps(data))
                    self.assertNotIn("api_key",json.dumps(data))
                    # Also assert a genuinely fresh issue gets HTTP 200
                    # and presents the forecast candidates, without writes.
                    with patch.object(board.time,"time",return_value=ISSUED+45):
                        with urlopen(base+"/api/live",timeout=3) as good:
                            self.assertEqual(good.status,200)
                            ready=json.load(good)
                            self.assertTrue(ready["healthy"])
                            self.assertEqual(sum(r["available"]
                                for r in ready["items"]),24)
                finally:
                    server.shutdown()
                    thread.join(timeout=3)

    def test_shared_flight_geometry_matches_research_contract(self):
        from research.plushie_champions.common import TRAVEL_SECONDS
        self.assertEqual(board.FLIGHTS,TRAVEL_SECONDS)
        self.assertEqual(board.MIN_STOCK,30)


if __name__=="__main__":
    unittest.main()
