"""Real loopback readiness probe catches the immediate-after-restart race."""
import importlib.util
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
PROBE=ROOT/"deploy/scripts/v160_beta_http_readiness.py"
spec=importlib.util.spec_from_file_location("beta_readiness",PROBE)
health=importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)


class Fixtures:
    def __init__(self,*,api_code=200,valid_items=True,have_recheck=True):
        self.api_code=api_code
        self.valid_items=valid_items
        self.have_recheck=have_recheck

    def handler(self):
        outer=self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path=="/":
                    page="<html><body><h1>Where should I fly?</h1>"
                    if outer.have_recheck:
                        page+="Recalculate this item NOW RECENT_ISSUED_NOW_RECHECK"
                    page+="</body></html>"
                    body=page.encode()
                    code=200
                elif self.path=="/api/live":
                    rows=[{"item_key":str(i),"models":{
                        "independent":{"signal":"DUE_NOW"},
                        "paired_complete":{"signal":"FUTURE_WATCH"}}}
                          for i in range(24 if outer.valid_items else 23)]
                    body=json.dumps({"healthy":outer.api_code==200,
                                     "items":rows}).encode()
                    code=outer.api_code
                else:
                    body=b"missing"
                    code=404
                self.send_response(code)
                self.send_header("Content-Length",str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self,*args):
                pass
        return Handler


class BetaReadinessTests(unittest.TestCase):
    def test_actual_http_retry_survives_server_startup_delay(self):
        # A socket bound but not yet served may simply block the first
        # request until ready. Explicitly inject the connection-refused
        # window so the regression deterministically verifies retry.
        with ThreadingHTTPServer(("127.0.0.1",0),Fixtures().handler()) as server:
            task=threading.Thread(target=server.serve_forever,daemon=True)
            task.start()
            calls=[0]
            def transient_bind(url,**kwargs):
                calls[0]+=1
                if calls[0]<=2:
                    raise URLError("Connection refused during service restart")
                return urlopen(url,**kwargs)
            try:
                report=health.readiness(port=server.server_port,
                                        expected="new",deadline_seconds=3,
                                        interval=.05,open_fn=transient_bind)
                self.assertEqual(report["records"],24)
                self.assertTrue(report["source_healthy"])
                self.assertEqual(report["mode"],"new")
                self.assertGreaterEqual(report["attempts"],3)
            finally:
                server.shutdown()
                task.join(timeout=2)

    def test_persistent_connection_refusal_is_not_called_success(self):
        def refused(*args,**kwargs):
            raise URLError("Connection refused")
        with self.assertRaisesRegex(TimeoutError,"Connection refused"):
            health.readiness(expected="new",deadline_seconds=.15,
                             interval=.05,open_fn=refused)

    def test_new_live_api_503_is_failure_but_stale_old_rollback_counts_as_restored(self):
        with ThreadingHTTPServer(("127.0.0.1",0),
                                 Fixtures(api_code=503).handler()) as server:
            task=threading.Thread(target=server.serve_forever,daemon=True)
            task.start()
            try:
                with self.assertRaisesRegex(TimeoutError,"API HTTP 503"):
                    health.readiness(port=server.server_port,expected="new",
                                     deadline_seconds=.2,interval=.05)
                backup=health.readiness(port=server.server_port,expected="rollback",
                                        deadline_seconds=.3,interval=.05)
                self.assertEqual(backup["http"],503)
                self.assertEqual(backup["records"],24)
            finally:
                server.shutdown()
                task.join(timeout=2)

    def test_missing_ui_action_fails_closed(self):
        with ThreadingHTTPServer(("127.0.0.1",0),
                                 Fixtures(have_recheck=False).handler()) as server:
            task=threading.Thread(target=server.serve_forever,daemon=True)
            task.start()
            try:
                with self.assertRaisesRegex(TimeoutError,"missing"):
                    health.readiness(port=server.server_port,expected="new",
                                     deadline_seconds=.2,interval=.05)
            finally:
                server.shutdown()
                task.join(timeout=2)

    def test_incomplete_24_items_rejected(self):
        with ThreadingHTTPServer(("127.0.0.1",0),
                                 Fixtures(valid_items=False).handler()) as server:
            task=threading.Thread(target=server.serve_forever,daemon=True)
            task.start()
            try:
                with self.assertRaisesRegex(TimeoutError,"24 complete items"):
                    health.readiness(port=server.server_port,expected="new",
                                     deadline_seconds=.2,interval=.05)
            finally:
                server.shutdown()
                task.join(timeout=2)


if __name__=="__main__":
    unittest.main()
