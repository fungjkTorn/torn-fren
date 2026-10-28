"""Forward evidence, publication and audited-site compatibility regressions."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from services import first_release_evidence as ev
from services.first_release_live import publish
from services.first_release_schedule import FIRST_RELEASE_MODELS

NOW=1790000000
SHA="a"*40


def make_issue(key,issued,departure,arrival,ordinal=1):
    return {"item_key":key,"asof_epoch":issued,"decision":{
        "estimated_departure_epoch":departure,"estimated_arrival_epoch":arrival,
        "selected_restock_event_index":ordinal,"forecast_events":[]}}


class ArrivalEvidenceTests(unittest.TestCase):
    def test_above_30_is_success_but_exactly_30_fails(self):
        for q,status in ((31,"SUCCESS"),(30,"FAILURE"),(0,"FAILURE")):
            r=ev.grade(1000,[(500,q,"p")],[990,1010],[],cutoff=1200)
            self.assertEqual(status,r["status"])

    def test_no_future_grace_threshold_switches_and_outages_are_unknown(self):
        r=ev.grade(1000,[(500,0,"p"),(1005,100,"p")],[990,1010],[],cutoff=1200)
        self.assertEqual("UNKNOWN",r["status"])
        r=ev.grade(1000,[(500,100,"p")],[990,1010],[(995,1005)],cutoff=1200)
        self.assertEqual("UNKNOWN",r["status"])
        self.assertEqual("PENDING",ev.grade(1000,[],[],[],cutoff=1100)["status"])

    def test_match_ordinal_does_not_choose_nearest_convenient_restock(self):
        rows=[(100,0,"p"),(200,100,"p"),(300,0,"p"),(400,100,"p")]
        issue=make_issue("mex:Dahlia",150,180,200,2)
        self.assertEqual(400,ev.target_for_issue(issue,rows,[])["epoch"])
        self.assertIsNone(ev.target_for_issue(issue,rows,[(250,350)]))

    def test_ledger_is_immutable_and_repeated_forecasts_are_one_trip(self):
        with tempfile.TemporaryDirectory() as td:
            db=ev.connect(Path(td)/"ledger.sqlite")
            source=sqlite3.connect(":memory:")
            source.executescript("""CREATE TABLE stock_history(id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,item_name TEXT,quantity INTEGER,source TEXT);
              CREATE TABLE collection_gaps(start_timestamp INTEGER,end_timestamp INTEGER);""")
            source.executemany("INSERT INTO stock_history VALUES(?,?,?,?,?,?)",[(1,100,"mex","Dahlia",0,"p"),(2,200,"mex","Dahlia",100,"p")])
            for issued,status in ((150,"FAILURE"),(160,"SUCCESS"),(170,"SUCCESS")):
                issue=make_issue("mex:Dahlia",issued,180,200)
                ev.record(db,issue,model_sha=SHA)
                db.execute("INSERT INTO publications VALUES(?,?,?)",(issued,issued,SHA))
                db.execute("INSERT INTO outcomes VALUES(?,?,?,?)",("mex:Dahlia",issued,400,json.dumps({"status":status})))
            result=ev.summary(db,source,item_key="mex:Dahlia",model_sha=SHA,cutoff=400)
            self.assertEqual(1,len(result["trips"]))
            self.assertEqual(1,result["failures"])
            self.assertEqual(0,result["successes"])
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE issues SET payload='{}'")
            with self.assertRaises(ValueError):
                ev.record(db,make_issue("mex:Dahlia",150,181,201),model_sha=SHA)
            db.close();source.close()

    def test_unmatched_failures_are_disclosed_and_percentage_withheld(self):
        with tempfile.TemporaryDirectory() as td:
            db=ev.connect(Path(td)/"ledger.sqlite");src=sqlite3.connect(":memory:")
            src.executescript("CREATE TABLE stock_history(id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,item_name TEXT,quantity INTEGER,source TEXT);CREATE TABLE collection_gaps(start_timestamp INTEGER,end_timestamp INTEGER);")
            ev.record(db,make_issue("mex:Dahlia",100,110,130),model_sha=SHA)
            db.execute("INSERT INTO publications VALUES(100,100,?)",(SHA,))
            db.execute("INSERT INTO outcomes VALUES('mex:Dahlia',100,400,?)",(json.dumps({"status":"FAILURE"}),))
            r=ev.summary(db,src,item_key="mex:Dahlia",model_sha=SHA,cutoff=400)
            self.assertEqual(1,r["unmatched_forecast_rows"]["FAILURE"])
            self.assertIsNone(r["success_fraction"])
            self.assertTrue(r["percentage_withheld_for_unmatched_misses"])
            db.close();src.close()

    def test_permanent_log_retains_selected_timing_not_64_duplicated_windows(self):
        with tempfile.TemporaryDirectory() as td:
            db=ev.connect(Path(td)/"ledger.sqlite")
            row=make_issue("mex:Dahlia",100,110,130,2)
            row["decision"]["forecast_events"]=[{"index":i,"predicted_restock_epoch":100+i*500,"predicted_stock_below_30_epoch":200+i*500} for i in range(1,65)]
            row['forecast']={'restock_events':[{'event_index':i} for i in range(1,65)]}
            ev.record(db,row,model_sha=SHA)
            saved=json.loads(db.execute('SELECT payload FROM issues').fetchone()[0])
            self.assertEqual(64,len(row['decision']['forecast_events']))
            self.assertEqual([2],[e['index'] for e in saved['decision']['forecast_events']])
            self.assertEqual(1200,saved['decision']['forecast_events'][0]['predicted_stock_below_30_epoch'])
            self.assertLess(len(json.dumps(saved)),2000)
            db.close()


class PublisherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Share the existing small, deterministic full native-engine fixture.
        from test_first_release_schedule import FirstReleaseNativeTests
        cls.fixture=FirstReleaseNativeTests
        cls.fixture.setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.fixture.tearDownClass()

    def test_real_ten_item_publication_persists_records_before_serving(self):
        with tempfile.TemporaryDirectory() as td:
            state=Path(td)
            before=self.fixture.source.read_bytes()
            result=publish(self.fixture.source,state,model_sha=SHA,clock=lambda:NOW)
            self.assertEqual("TEN_ITEM_SNAPSHOT_PUBLISHED",result["status"])
            s=json.loads((state/"latest.json").read_text())
            self.assertEqual(set(FIRST_RELEASE_MODELS),set(s["items"]))
            self.assertEqual(before,self.fixture.source.read_bytes())
            with sqlite3.connect(state/"forecasts.sqlite") as db:
                self.assertEqual(10,db.execute("SELECT COUNT(*) FROM issues").fetchone()[0])
                self.assertEqual(1,db.execute("SELECT COUNT(*) FROM publications").fetchone()[0])
            from web.first_release_bridge import read_board,attach_history
            b=read_board(now=NOW,path=state/"latest.json")
            self.assertEqual(10,len(b["rows"]))
            payload=attach_history({"country":"mex","item":"Dahlia","analysis":{"prediction_v2":{"arrival_success_rate":.99}}},b)
            self.assertIsNone(payload["analysis"]["prediction_v2"]["arrival_success_rate"])
            self.assertTrue(payload["analysis"]["prediction"]["first_release"])
            stale=read_board(now=NOW+301,path=state/"latest.json")
            self.assertTrue(all(r["decision"]["estimated_departure_epoch"] is None for r in stale["rows"]))

    def test_partial_or_slow_batch_does_not_replace_existing_feed(self):
        with tempfile.TemporaryDirectory() as td:
            state=Path(td);(state/"latest.json").write_text('KEEP')
            def fail(*a,**kw):raise RuntimeError("synthetic failed item")
            with self.assertRaisesRegex(RuntimeError,"incomplete"):
                publish(self.fixture.source,state,model_sha=SHA,item_runner=fail,clock=lambda:NOW)
            self.assertEqual('KEEP',(state/"latest.json").read_text())
            ticks=iter((NOW,NOW,NOW+46))
            with self.assertRaisesRegex(TimeoutError,"45-second"):
                publish(self.fixture.source,state,model_sha=SHA,item_runner=fail,clock=lambda:next(ticks))
            self.assertEqual('KEEP',(state/"latest.json").read_text())


class WebBridgeTests(unittest.TestCase):
    def test_all_three_views_use_bridge_and_stock_history_survives(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from fastapi.responses import HTMLResponse
        from web.first_release_bridge import install_first_release
        app=FastAPI()
        @app.get('/')
        def index():return HTMLResponse('<html><body>Original stock graph</body></html>')
        @app.get('/api/history')
        def history():return {"country":"mex","item":"Dahlia","rows":[{"quantity":55}],"analysis":{}}
        install_first_release(app)
        board={"status":"LIVE_BETA","rows":[]}
        with patch('web.first_release_bridge.read_board',return_value=board),TestClient(app) as client:
            for path in ('/','/experimental','/travel-decisions'):
                r=client.get(path);self.assertEqual(200,r.status_code)
                self.assertIn('beta.js',r.text)
            self.assertIn('Original stock graph',client.get('/').text)
            r=client.get('/api/history').json()
            self.assertEqual([{"quantity":55}],r['rows'])
            self.assertEqual('ITEM_UNDER_REVIEW',r['analysis']['first_release']['status'])
            self.assertEqual('LIVE_BETA',client.get('/api/first-release').json()['status'])


if __name__=='__main__':unittest.main()
