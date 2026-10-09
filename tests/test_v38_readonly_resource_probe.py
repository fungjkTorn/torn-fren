"""V38 bounded original-engine resource probe does not collect or mutate."""
import json
import unittest
from unittest.mock import Mock
from research.v38_readonly_resource_probe import PROBES,ALL,probe


class V38ResourceProbeTests(unittest.TestCase):
    def test_exact_14_supported_and_representative_five(self):
        self.assertEqual(len(ALL),14)
        self.assertEqual(len(PROBES),5)
        self.assertIn("uni:Nessie Plushie",ALL)
        self.assertNotIn("jap:Xanax",ALL)

    def test_sequential_bounded_worker_and_no_v2(self):
        seen=[]
        def run(args,**kw):
            seen.append((args,kw))
            return Mock(returncode=0,stdout=json.dumps({
                "status":"RESEARCH_PROPOSAL_ONLY"}))
        x=probe("/readonly/stock.db",["uni:Heather","uni:Nessie Plushie"],
                per_item_seconds=8,budget_seconds=22,
                runner=run,clock=lambda:0.,wall_clock=lambda:1790000000)
        self.assertEqual(x["proposal_count"],2)
        self.assertEqual(len(seen),2)
        for args,kwargs in seen:
            self.assertEqual(args[0:2],[__import__("sys").executable,"-m"])
            self.assertIn("--db",args)
            self.assertEqual(kwargs["timeout"],8)
            self.assertTrue(kwargs["capture_output"])
            self.assertNotIn("http",str(args).lower())
        self.assertFalse(x["v2_http_called"])
        self.assertFalse(x["stock_db_modified"])

    def test_budget_skip_and_timeout_status_honest(self):
        import subprocess
        def timeout(args,**kw):
            raise subprocess.TimeoutExpired(args,kw["timeout"])
        x=probe("/none",["uni:Heather","not:approved"],
                per_item_seconds=2,budget_seconds=3,
                runner=timeout,clock=lambda:0,wall_clock=lambda:1790000000)
        self.assertEqual(x["items"][0]["status"],"WORKER_TIMEOUT")
        self.assertEqual(x["items"][1]["status"],"UNSUPPORTED")

    def test_invalid_limits_rejected(self):
        with self.assertRaises(ValueError):
            probe("/none",[],per_item_seconds=40,budget_seconds=20)


if __name__=="__main__":unittest.main()
