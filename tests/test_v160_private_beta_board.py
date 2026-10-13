"""Standalone V160 private live beta must only use honest, read-only issuance."""
import hashlib
import importlib.util
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
import sys
import threading
import unittest
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen,Request

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"deploy/scripts/v160_private_beta_board.py"
spec=importlib.util.spec_from_file_location("v160_beta_board",SCRIPT)
board=importlib.util.module_from_spec(spec)
spec.loader.exec_module(board)
ISSUED=1791910560


def fixture(root):
    ledger=root/"v160_v151_prospective24.db"
    roster=root/"roster.json"
    from research.v128_full24_earliest_shadow import exact_roster
    # Use actual pinned 22-key JSON. Prior synthetic 24-key fixture
    # masked a real VM install failure (24 = 22 base + 2 V42 Xanax).
    shutil.copyfile(ROOT/"research/v38_roster.json",roster)
    pinned=json.loads(roster.read_text(encoding="utf-8"))["items"]
    assert len(pinned)==22
    names=exact_roster(roster)
    assert len(names)==24
    assert set(names)==set(pinned)|board.EXTRA_XANAX_KEYS
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
    def test_browser_script_parses_with_node_when_available(self):
        import shutil
        if shutil.which("node") is None:
            self.skipTest("Node JS parser unavailable in local environment")
        scripts=re.findall(r"<script>(.*?)</script>",board.HTML,re.S)
        self.assertEqual(len(scripts),1)
        result=subprocess.run(["node","--check"],input=scripts[0],
                              capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("Where should I fly?",board.HTML)
        self.assertIn("Recent",board.HTML)
        self.assertIn("FUTURE_WATCH",board.HTML)
        self.assertIn("RECENT_ISSUED_NOW_RECHECK",board.HTML)

    def test_decision_first_page_keeps_accuracy_distinction_and_details_collapsed(self):
        page=board.HTML
        self.assertIn("Earliest upcoming departure",page)
        self.assertIn("Next departure windows",page)
        self.assertIn("Estimated landing",page)
        self.assertIn("LEAVE AT ",page)
        self.assertIn("RECHECK",page)
        self.assertIn('<details id="technical">',page)
        self.assertIn("Actual live success rate: not yet established",page)
        self.assertIn("A scenario percentage is not a verified chance of success",page)
        self.assertIn('recheckNow();',page)
        self.assertIn('Check this item NOW',page)
        self.assertIn('Recalculate this item NOW',page)
        self.assertIn('mismatch',page)
        self.assertNotIn("93% accurate",page)

    def test_true_pinned_roster_is_22_plus_two_exact_xanax_keys(self):
        from research.v128_full24_earliest_shadow import exact_roster
        source=ROOT/"research/v38_roster.json"
        base=json.loads(source.read_text(encoding="utf-8"))["items"]
        self.assertEqual(len(base),22)
        self.assertEqual(board.BASE_ROSTER_ROWS,22)
        self.assertEqual(board.EXTRA_XANAX_KEYS,
                         frozenset(("can:Xanax","uni:Xanax")))
        self.assertEqual(set(exact_roster(source)),
                         set(base)|board.EXTRA_XANAX_KEYS)

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

    def test_issued_now_signal_survives_past_30s_without_claiming_new_departure(self):
        """The exact reported 3/24 UI failure was caused by discarding NOW
        timestamps and calling a successful candidate 'No departure'."""
        with tempfile.TemporaryDirectory() as tmp:
            ledger,roster=fixture(Path(tmp))
            with closing(sqlite3.connect(ledger)) as db:
                key,body=db.execute(
                    "SELECT item_key,payload_json FROM v160_issued LIMIT 1"
                ).fetchone()
                value=json.loads(body)
                country=key.split(":",1)[0]
                v=value["models"]["independent"]
                v.update(departure_epoch=ISSUED,
                         arrival_epoch=ISSUED+board.FLIGHTS[country],
                         wait_seconds=0,
                         status="PROVISIONAL_SCENARIO_SUPPORTED_DEPARTURE")
                db.execute("UPDATE v160_issued SET payload_json=? WHERE item_key=?",
                           (json.dumps(value),key))
                db.commit()
            report=board.snapshot(ledger,roster,now=ISSUED+130)
            self.assertTrue(report["healthy"])
            row=next(r for r in report["items"] if r["item_key"]==key)
            signal=row["models"]["independent"]
            self.assertEqual(signal["signal"],"RECENT_ISSUED_NOW_RECHECK")
            self.assertTrue(signal["issued_now"])
            self.assertEqual(signal["issued_departure"],ISSUED)
            self.assertEqual(signal["issued_arrival"],
                             ISSUED+board.FLIGHTS[country])
            self.assertIsNone(signal["departure"])
            self.assertIsNone(signal["arrival"])
            self.assertTrue(row["recent_now_signal"])
            self.assertIn("Recently indicated",board.HTML)
            self.assertIn("RECHECK NOW SIGNAL",board.HTML)
            self.assertNotIn('return "No qualifying candidate";',board.HTML)

    def test_issued_now_signal_becomes_expired_not_a_forecast(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger,roster=fixture(Path(tmp))
            with closing(sqlite3.connect(ledger)) as db:
                key,body=db.execute(
                    "SELECT item_key,payload_json FROM v160_issued LIMIT 1"
                ).fetchone()
                value=json.loads(body)
                country=key.split(":",1)[0]
                v=value["models"]["paired_complete"]
                v.update(departure_epoch=ISSUED,
                         arrival_epoch=ISSUED+board.FLIGHTS[country],
                         wait_seconds=0)
                db.execute("UPDATE v160_issued SET payload_json=? WHERE item_key=?",
                           (json.dumps(value),key))
                db.commit()
            row=next(r for r in board.snapshot(ledger,roster,now=ISSUED+310)["items"]
                     if r["item_key"]==key)
            self.assertEqual(row["models"]["paired_complete"]["signal"],
                             "DEPARTURE_PASSED")
            self.assertIsNone(row["models"]["paired_complete"]["departure"])
            self.assertFalse(row["recent_now_signal"])

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
            output=board.snapshot(ledger,roster,now=ISSUED+631)
            self.assertTrue(output["healthy"])
            self.assertTrue(all(row["models"]["independent"]["departure"] is None
                for row in output["items"]))
            self.assertTrue(all(row["models"]["paired_complete"]["departure"]==ISSUED+900
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
                        self.assertIn("Where should I fly?",page)
                        self.assertIn("Provisional guidance",page)
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

    def test_user_clicked_one_item_recheck_is_loopback_protected_and_throttled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            ledger,roster=fixture(root)
            key="mex:Jaguar Plushie"
            fake=root/"one_item_test.py"
            fake.write_text(
                "import json,sys\n"
                "print(json.dumps({'status':'CURRENT_ITEM_RECHECK_RESEARCH_ONLY',"
                "'item_key':sys.argv[1],'issued_epoch':1791910605,"
                "'collector_written':False,'private_ledger_written':False,"
                "'models':{'independent':{},'paired_complete':{}}}))\n",
                encoding="utf-8")
            from urllib.error import HTTPError
            with ThreadingHTTPServer(("127.0.0.1",0),
                 board.handler_factory(ledger,roster,
                      helper=fake,python=Path(sys.executable),work=ROOT)) as server:
                worker=threading.Thread(target=server.serve_forever,daemon=True)
                worker.start()
                url="http://127.0.0.1:"+str(server.server_port)+"/api/recheck"
                body=json.dumps({"item_key":key}).encode()
                def request(with_header=True,**headers):
                    h={"Content-Type":"application/json"}
                    if with_header:
                        h["X-Torn-Fren-Action"]="user-recheck"
                    h.update(headers)
                    return Request(url,data=body,headers=h,method="POST")
                try:
                    with patch.object(board.time,"time",return_value=ISSUED+45):
                        with self.assertRaises(HTTPError) as missing:
                            urlopen(request(with_header=False),timeout=4)
                        self.assertEqual(missing.exception.code,403)
                        with self.assertRaises(HTTPError) as foreign:
                            urlopen(request(Origin="https://untrusted.example"),timeout=4)
                        self.assertEqual(foreign.exception.code,403)
                        with urlopen(request(),timeout=4) as response:
                            rec=json.load(response)
                            self.assertEqual(response.status,200)
                            self.assertEqual(rec["item_key"],key)
                            self.assertFalse(rec["collector_written"])
                            self.assertFalse(rec["private_ledger_written"])
                        with self.assertRaises(HTTPError) as cooldown:
                            urlopen(request(),timeout=4)
                        self.assertEqual(cooldown.exception.code,429)
                finally:
                    server.shutdown()
                    worker.join(timeout=4)

    def test_shared_flight_geometry_matches_research_contract(self):
        from research.plushie_champions.common import TRAVEL_SECONDS
        self.assertEqual(board.FLIGHTS,TRAVEL_SECONDS)
        self.assertEqual(board.MIN_STOCK,30)


if __name__=="__main__":
    unittest.main()
