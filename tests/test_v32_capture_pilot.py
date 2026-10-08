import io
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from research.v32_capture_pilot import capture_once,_safe_local_endpoint

class Response:
    def __init__(self,body):
        self.status=200
        self.body=io.BytesIO(json.dumps(body).encode())
    def __enter__(self):return self
    def __exit__(self,*args):self.body.close()
    def read(self,n):return self.body.read(n)


class PrivateCaptureTests(unittest.TestCase):
    def test_refuse_nonloopback_or_embedded_auth(self):
        for url in ("https://random-public-host.com","http://example.com",
                    "http://user:pass@127.0.0.1:8000","http://127.0.0.1:8000/?token=s3cret"):
            with self.assertRaises(ValueError):
                _safe_local_endpoint(url)
        self.assertEqual(_safe_local_endpoint("http://127.0.0.1:8000"),"http://127.0.0.1:8000")

    def test_real_private_capture_to_separate_sqlite_without_secret(self):
        token="strong_test_secret_not_for_production_1234567"
        now=int(time.time())
        data={
         "schema":"torn-fren-private-research-shadow-v29",
         "key":"can:Fire Hydrant","generated_at":now,
         "mode":"READ_ONLY_DIAGNOSTIC",
         "default_live_routing":"UNCHANGED",
         "champion_executed":False,"candidate_promoted":False,
         "chance_calibrated":False,"baseline":{"status":"unavailable"},
         "challenger":{"status":"DISABLED","champion_executed":False}
        }
        def fetch(req,**kwargs):
            self.assertEqual(req.get_header("X-torn-fren-shadow-token"),token)
            self.assertNotIn(token,req.full_url)
            return Response(data)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"pilot_only.db"
            out=capture_once("http://127.0.0.1:8000","can:Fire Hydrant",
                             p,"research-pilot",token,fetch=fetch)
            self.assertEqual(out["status"],"RECORDED")
            self.assertNotIn(token,p.read_bytes().decode("latin1"))
            again=capture_once("http://127.0.0.1:8000","can:Fire Hydrant",
                             p,"research-pilot",token,fetch=fetch)
            self.assertEqual(again["status"],"DUPLICATE_TICK_IGNORED")
            with sqlite3.connect(p) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM shadow_decisions").fetchone()[0],1)

    def test_mismatched_response_item_fails_before_capture(self):
        now=int(time.time())
        data={"key":"mex:Jaguar Plushie","generated_at":now}
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"evidence.db"
            with self.assertRaises(ValueError):
                capture_once("http://127.0.0.1:8000","can:Fire Hydrant",
                    p,"research-pilot","s"*40,fetch=lambda *a,**kw:Response(data))
            self.assertFalse(p.exists())


if __name__=="__main__":
    unittest.main()
