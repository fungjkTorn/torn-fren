"""V33 prospective private shadow capture regression and safety tests."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research.v33_private_shadow_sampler import (
    capture_one, _open_ledger, fetch_private,
    ALLOWED, PrivateSamplingError
)

TEST_TOKEN="test_only_private_token_0123456789abcdef0123456789"
T=1791498000


def fake_snapshot(country,item,generated=T,executed=True):
    return {
        "schema":"torn-fren-private-research-shadow-v29",
        "generated_at":generated,
        "key":f"{country}:{item}",
        "mode":"READ_ONLY_DIAGNOSTIC",
        "default_live_routing":"UNCHANGED",
        "candidate_model_family":"v21",
        "candidate_config":"dyn12" if item=="Bear Gall" else "dyn13",
        "candidate_promoted":False,
        "chance_calibrated":False,
        "champion_executed":executed,
        "baseline":{"status":"available",
            "recommended_leave_by_timestamp":generated+1300,
            "recommended_arrival_timestamp":generated+2920},
        "challenger":{"status":"RESEARCH_PROPOSAL_ONLY" if executed else "NO_RECOMMENDATION",
            "champion_executed":executed,
            "recommended_departure_timestamp":generated+900 if executed else None,
            "recommended_arrival_timestamp":generated+2520 if executed else None},
    }


class ShadowSamplerTests(unittest.TestCase):
    def test_one_capture_then_duplicate_does_not_change_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/"shadow_only.db"
            fetch=lambda c,i,t:fake_snapshot(c,i)
            x=capture_one("can:Bear Gall",ledger=ledger,experiment="pilot-v33",
                          token=TEST_TOKEN,clock=lambda:T,fetcher=fetch)
            y=capture_one("can:Bear Gall",ledger=ledger,experiment="pilot-v33",
                          token=TEST_TOKEN,clock=lambda:T+20,fetcher=fetch)
            self.assertEqual(x["status"],"RECORDED")
            self.assertEqual(y["status"],"DUPLICATE_FIVE_MINUTE_SLOT")
            with sqlite3.connect(ledger) as con:
                self.assertEqual(con.execute("select count(*) from shadow_decisions").fetchone()[0],1)
                self.assertEqual(con.execute("select count(*) from shadow_capture_attempts").fetchone()[0],1)
                row=con.execute("select status,evidence_id from shadow_capture_attempts").fetchone()
                self.assertEqual(row,("RECORDED",1))
            self.assertNotIn(TEST_TOKEN,ledger.read_bytes().decode("latin1"))

    def test_both_allowed_items_same_tick_and_no_recommendation_is_recorded(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/"evidence.db"
            for key in ("can:Bear Gall","can:Fire Hydrant"):
                c,i=key.split(":",1)
                x=capture_one(key,ledger=ledger,experiment="pilot-v33",
                       token=TEST_TOKEN,clock=lambda:T,
                       fetcher=lambda co,it,t:fake_snapshot(co,it,executed=it!="Fire Hydrant"))
                self.assertEqual(x["status"],"RECORDED")
            with sqlite3.connect(ledger) as con:
                self.assertEqual(con.execute("select count(*) from shadow_decisions").fetchone()[0],2)
                missing=con.execute("select challenger_executed from shadow_decisions "
                    "where item_key='can:Fire Hydrant'").fetchone()[0]
                self.assertEqual(missing,0)

    def test_http_failure_still_writes_attempt_and_no_fake_forecast(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/"evidence.db"
            def error(c,i,t):
                raise PrivateSamplingError("PRIVATE_HTTP_NON_200")
            result=capture_one("can:Bear Gall",ledger=ledger,experiment="pilot-v33",
                         token=TEST_TOKEN,clock=lambda:T,fetcher=error)
            self.assertEqual(result["status"],"PRIVATE_REJECTED_PRIVATE_HTTP_NON_200")
            with sqlite3.connect(ledger) as con:
                self.assertEqual(con.execute("select count(*) from shadow_capture_attempts").fetchone()[0],1)
                tables=[r[0] for r in con.execute("select name from sqlite_master where type='table'")]
                if "shadow_decisions" in tables:
                    self.assertEqual(con.execute("select count(*) from shadow_decisions").fetchone()[0],0)
                self.assertEqual(con.execute("select status from shadow_capture_attempts").fetchone()[0],
                                 "PRIVATE_REJECTED_PRIVATE_HTTP_NON_200")
            self.assertNotIn(TEST_TOKEN,ledger.read_bytes().decode("latin1"))

    def test_stale_backdated_and_cross_tick_results_are_rejected(self):
        for generated in (T-4,T+305):
            with self.subTest(generated=generated), tempfile.TemporaryDirectory() as td:
                ledger=Path(td)/"ledger.db"
                status=capture_one("can:Bear Gall",ledger=ledger,experiment="pilot-v33",
                             token=TEST_TOKEN,clock=lambda:T,
                             fetcher=lambda c,i,t:fake_snapshot(c,i,generated=generated))
                self.assertTrue(status["status"].startswith("PRIVATE_REJECTED_"))

    def test_reject_forecast_for_other_item_and_unapproved_items(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=Path(td)/"ledger.db"
            with self.assertRaises(ValueError):
                capture_one("mex:Unsupported",ledger=ledger,experiment="pilot-v33",
                            token=TEST_TOKEN,clock=lambda:T,
                            fetcher=lambda c,i,t:fake_snapshot(c,i))
            result=capture_one("can:Bear Gall",ledger=ledger,experiment="pilot-v33",
                          token=TEST_TOKEN,clock=lambda:T,
                          fetcher=lambda c,i,t:fake_snapshot("can","Fire Hydrant"))
            self.assertEqual(result["status"],
                             "PRIVATE_REJECTED_PRIVATE_RESPONSE_IDENTITY_MISMATCH")

    def test_never_write_to_stock_history_even_when_renamed(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"renamed.db"
            with sqlite3.connect(source) as con:
                con.execute("CREATE TABLE stock_history (timestamp INTEGER)")
            before=source.read_bytes()
            with self.assertRaises(ValueError):
                capture_one("can:Bear Gall",ledger=source,experiment="pilot-v33",
                            token=TEST_TOKEN,clock=lambda:T,
                            fetcher=lambda c,i,t:fake_snapshot(c,i))
            self.assertEqual(source.read_bytes(),before)

    def test_private_http_fetch_rejects_redirect_without_following_it(self):
        class FakeResponse:
            status=302
            def read(self,n):return b"{}"
        class FakeConnection:
            def __init__(self,host,port,timeout):
                self.host=host;self.port=port;self.timeout=timeout
            def request(self,method,uri,headers):
                self.method=method;self.uri=uri
                self.headers=headers
            def getresponse(self):return FakeResponse()
            def close(self):pass
        con=[]
        def factory(host,port,timeout):
            self.assertEqual((host,port),("127.0.0.1",8000))
            obj=FakeConnection(host,port,timeout)
            con.append(obj)
            return obj
        with self.assertRaises(PrivateSamplingError):
            fetch_private("can","Bear Gall",TEST_TOKEN,connection_factory=factory)
        self.assertEqual(len(con),1)
        self.assertNotIn(TEST_TOKEN,con[0].uri)
        self.assertEqual(con[0].headers["X-Torn-Fren-Shadow-Token"],TEST_TOKEN)

if __name__=="__main__":
    unittest.main()
