"""V36 isolated capture safety, data provenance and round-robin regression."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from research.v36_isolated_museum_sampler import (
    ORDER,NATIVE,PILOT,TRAVEL,scheduled_item,capture,
    _v2_from_public_history,_native_single_tick
)
from research.v34_prospective_ops_audit import audit

T=1791499800


def native(_db,key,now):
    if key not in NATIVE:
        return {"status":"SPECIALIST_NOT_INTEGRATED","champion_executed":False}
    return {"status":"RESEARCH_PROPOSAL_ONLY","champion_executed":True,
            "departure":now+900,"arrival":now+900+TRAVEL[key[:3]],
            "config":NATIVE[key]}


def v2(country,item):
    return {"status":"available",
        "recommended_leave_by_timestamp":T+1100,
        "recommended_arrival_timestamp":T+1100+TRAVEL[country]}


class V36IsolatedCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"shadow.db"
        self.stock=Path(self.temp.name)/"collector.db"
        with sqlite3.connect(self.stock) as con:
            con.execute("CREATE TABLE stock_history(timestamp INTEGER)")

    def capture(self,key,epoch=T,fetch_native=native,fetch_v2=v2):
        return capture(key,db=self.stock,ledger=self.path,clock=lambda:epoch,
                       native_fn=fetch_native,v2_fn=fetch_v2)

    def test_rotation_guarantees_one_of_each_every_four_ticks(self):
        for i in range(80):
            self.assertEqual(scheduled_item(T+i*300),ORDER[(T//300+i)%4])
        self.assertEqual(len({scheduled_item(T+i*300) for i in range(4)}),4)

    def test_two_real_v18_champions_capture_actual_future_departures(self):
        for i,key in enumerate(("uni:Heather","can:Wolverine Plushie")):
            r=self.capture(key,epoch=T+i*300,
                           fetch_v2=lambda c,n:{"status":"warming"})
            self.assertEqual(r["status"],"RECORDED",r)
            self.assertTrue(r["champion_executed"])
            self.assertEqual(r["native_status"],"RESEARCH_PROPOSAL_ONLY")
        with sqlite3.connect(self.path) as con:
            rows=con.execute("""SELECT item_key,source_schema,
                challenger_executed,challenger_arrival,challenger_departure
                FROM shadow_decisions ORDER BY id""").fetchall()
        self.assertEqual(len(rows),2)
        self.assertTrue(all(x[1]=="torn-fren-v36-isolated-native-with-public-v2-reference"
                            for x in rows))
        self.assertTrue(all(x[2]==1 and x[3]>x[4] for x in rows))

    def test_nessie_and_xanax_are_baseline_only(self):
        for i,key in enumerate(("uni:Nessie Plushie","jap:Xanax")):
            r=self.capture(key,epoch=T+i*300)
            self.assertEqual(r["status"],"RECORDED")
            self.assertFalse(r["champion_executed"])
            self.assertEqual(r["native_status"],"SPECIALIST_NOT_INTEGRATED")
        with sqlite3.connect(self.path) as con:
            rows=con.execute("SELECT item_key,challenger_executed,challenger_status,"
                             "v2_departure FROM shadow_decisions ORDER BY id").fetchall()
        self.assertEqual(len(rows),2)
        self.assertTrue(all(x[1]==0 and x[2]=="SPECIALIST_NOT_INTEGRATED"
                            for x in rows))
        self.assertTrue(all(x[3] is not None for x in rows))

    def test_worker_timeout_records_abstention_not_false_champion(self):
        bad=lambda db,key,now:{"status":"NATIVE_WORKER_TIMEOUT","champion_executed":False}
        r=self.capture("uni:Heather",fetch_native=bad)
        self.assertEqual(r["status"],"RECORDED")
        self.assertFalse(r["champion_executed"])
        with sqlite3.connect(self.path) as con:
            row=con.execute("SELECT challenger_executed,challenger_status "
                            "FROM shadow_decisions").fetchone()
        self.assertEqual(row,(0,"NATIVE_WORKER_TIMEOUT"))

    def test_duplicate_same_tick_does_not_erase_original(self):
        a=self.capture("uni:Heather")
        before=self.path.read_bytes()
        b=self.capture("uni:Heather",T+40)
        self.assertEqual(a["status"],"RECORDED")
        self.assertEqual(b["status"],"DUPLICATE_FIVE_MINUTE_SLOT")
        self.assertEqual(self.path.read_bytes(),before)

    def test_never_writes_stock_and_public_not_private_token(self):
        before=self.stock.read_bytes()
        self.capture("jap:Xanax")
        self.assertEqual(self.stock.read_bytes(),before)
        content=self.path.read_bytes().decode("latin1")
        self.assertNotIn("X-Torn-Fren-Shadow-Token",content)
        self.assertNotIn("TORN_FREN_CHAMPION_SHADOW_TOKEN",content)

    def test_live_native_response_requires_frozen_identity_and_no_calibration(self):
        def worker(args,**kwargs):
            return Mock(returncode=0,stdout=json.dumps({
                "status":"RESEARCH_PROPOSAL_ONLY","key":"uni:Heather",
                "model_generation":"V18","model_config":"dyn3",
                "probability_calibrated":False,
                "recommended_departure_timestamp":T+900,
                "recommended_arrival_timestamp":T+900+6360,
                "replan_step_seconds":300,"research_horizon_seconds":28800}),stderr="")
        a=_native_single_tick(self.stock,"uni:Heather",T,runner=worker)
        self.assertTrue(a["champion_executed"])
        def bad(args,**kwargs):
            d=json.loads(worker(args,**kwargs).stdout)
            d["model_config"]="dyn8"
            return Mock(returncode=0,stdout=json.dumps(d),stderr="")
        b=_native_single_tick(self.stock,"uni:Heather",T,runner=bad)
        self.assertEqual(b["status"],"NATIVE_RESULT_REJECTED")

    def test_v2_reads_loopback_history_nonblocking_with_no_secrets(self):
        class R:
            status=200
            def read(self,size):
                return json.dumps({"country":"jap","item":"Xanax",
                    "analysis":{"prediction_v2":{"display_prediction":{
                    "recommended_leave_by_timestamp":T+2000,
                    "recommended_arrival_timestamp":T+2000+8940}}}}).encode()
        class Connection:
            def __init__(self,host,port,timeout):
                self.assertion=(host,port,timeout)
            def request(self,m,u,headers=None):
                self.path=u
                self.method=m
            def getresponse(self):return R()
            def close(self):pass
        arr=[]
        def factory(host,port,timeout):
            o=Connection(host,port,timeout)
            arr.append(o)
            return o
        obj=_v2_from_public_history("jap","Xanax",connection_factory=factory)
        self.assertEqual(obj["status"],"available")
        self.assertEqual(arr[0].assertion,("127.0.0.1",8000,3))
        self.assertEqual(arr[0].method,"GET")
        self.assertNotIn("token",arr[0].path.lower())

    def test_live_capture_never_marks_unapproved_item(self):
        with self.assertRaises(ValueError):
            self.capture("can:Bear Gall")

if __name__=="__main__":unittest.main()
