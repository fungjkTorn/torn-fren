"""V38 source-versioned V2 result cache: freshness, causal invalidation, safe use."""
from __future__ import annotations
import os
import sqlite3
import tempfile
import time
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch
from web.v38_revision_fingerprint import revision
from web import app as webapp


class SourceVersionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/"test.db"
        with sqlite3.connect(self.db) as con:
            con.execute("CREATE TABLE poll_heartbeats(timestamp INTEGER,mode TEXT,success INTEGER)")
            con.execute("CREATE TABLE collection_gaps(id INTEGER PRIMARY KEY,end_timestamp INTEGER)")
            con.execute("INSERT INTO poll_heartbeats VALUES(1030,'poll-cycle',1)")
        self.state={"timestamp":700,"quantity":35,"cost":900,"source":"yata"}

    def rev(self, now=1030, **updates):
        return revision(self.db,country="uni",item="Heather",
                        item_state={**self.state,**updates},now=now)

    def test_quiet_item_remains_fresh_and_unmodified_for_five_minutes(self):
        status,first=self.rev()
        self.assertEqual(status,"FRESH")
        self.assertEqual(self.rev(now=1040)[1],first)
        self.assertEqual(self.rev(now=1199)[1],first)
        self.assertNotEqual(self.rev(now=1200)[1],first)
        self.assertEqual(self.rev(now=1030,quantity=34)[0],"FRESH")
        self.assertNotEqual(self.rev(now=1030,quantity=34)[1],first)

    def test_gap_and_end_of_gap_force_refresh(self):
        first=self.rev()[1]
        with sqlite3.connect(self.db) as con:
            con.execute("INSERT INTO collection_gaps VALUES(1,850)")
        second=self.rev()[1]
        self.assertNotEqual(first,second)
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE collection_gaps SET end_timestamp=1010 WHERE id=1")
        self.assertNotEqual(second,self.rev()[1])

    def test_stale_future_or_missing_heartbeat_never_fresh(self):
        self.assertEqual(self.rev(now=1500)[0],"COLLECTOR_STALE_OR_NO_HEARTBEAT")
        self.assertEqual(self.rev(now=1030,timestamp=1200)[0],"FUTURE_STOCK")
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE poll_heartbeats SET timestamp=1200")
        self.assertEqual(self.rev()[0],"COLLECTOR_STALE_OR_NO_HEARTBEAT")
        with sqlite3.connect(self.db) as con:
            con.execute("DELETE FROM poll_heartbeats")
        self.assertEqual(self.rev()[0],"COLLECTOR_STALE_OR_NO_HEARTBEAT")

    def test_missing_source_never_creates_database(self):
        missing=Path(self.tmp.name)/"absent.db"
        self.assertEqual(revision(missing,country="uni",item="Heather",
            item_state=self.state,now=1030)[0],"NO_VERIFIABLE_REVISION")
        self.assertFalse(missing.exists())

    def test_revision_cache_prevents_repeated_expensive_jobs(self):
        key=("uni","heather")
        rev=("uni","heather",700,35,900,"yata",0,0,3)
        calls=[]
        class ImmediateExecutor:
            def submit(self,fn,*args):
                calls.append((fn,args))
                f=Future()
                f.set_result({"status":"waiting_for_restock",
                              "predictions":[],"display_prediction":None})
                return f
        with patch.object(webapp,"_PREDICTION_EXECUTOR",ImmediateExecutor()):
            with patch.object(webapp,"_PREDICTION_CACHE",{}):
                with patch.object(webapp,"_PREDICTION_FUTURES",{}):
                    for _ in range(30):
                        prediction,stale=webapp._get_prediction_nonblocking(
                            "uni","Heather",revision=rev)
                        self.assertFalse(stale)
                        self.assertEqual(prediction["status"],"waiting_for_restock")
                    self.assertEqual(len(calls),1)
                    prediction,stale=webapp._get_prediction_nonblocking(
                        "uni","Heather",revision=(*rev[:-1],4))
                    self.assertFalse(stale)
                    self.assertEqual(len(calls),2)

    def test_analysis_cache_reuses_graph_and_preserves_response_shape(self):
        rev=("uni","heather",700,35,900,"yata",0,0,3)
        calls=[]
        class ImmediateExecutor:
            def submit(self,fn,*args):
                calls.append((fn,args))
                future=Future()
                future.set_result({"current_stock":35,
                                   "events":[],"prediction":{"status":"baseline"}})
                return future
        with patch.object(webapp,"_PREDICTION_EXECUTOR",ImmediateExecutor()):
            with patch.object(webapp,"_ANALYSIS_CACHE",{}):
                with patch.object(webapp,"_ANALYSIS_FUTURES",{}):
                    for _ in range(25):
                        graph,warming=webapp._get_analysis_nonblocking(
                            "uni","Heather",revision=rev)
                        self.assertFalse(warming)
                        self.assertEqual(graph["current_stock"],35)
                        self.assertNotIn("display_prediction",graph)
                    self.assertEqual(len(calls),1)
                    graph,warming=webapp._get_analysis_nonblocking(
                        "uni","Heather",revision=(*rev[:-1],4))
                    self.assertEqual(len(calls),2)
                    self.assertFalse(warming)

    def test_unversioned_production_default_uses_existing_ttl(self):
        self.assertIsNone(webapp._get_prediction_nonblocking.__defaults__[0])
        self.assertEqual(webapp._PREDICTION_CACHE_TTL_SECONDS,20)


if __name__=="__main__":unittest.main()
