"""Pure bounded probe tests: no production access, never touch a collector DB."""
import subprocess
import unittest
from unittest.mock import Mock

from research.v38_readonly_resource_probe import PROBES, ALL, probe


class V38ResourceProbeTests(unittest.TestCase):
    def test_probe_roster_and_safe_default(self):
        self.assertEqual(len(ALL),13)
        self.assertEqual(len(PROBES),4)
        self.assertEqual(set(PROBES)-set(ALL),set())

    def test_exact_source_pinned_execution_and_no_http_or_write(self):
        invocations=[]
        def runner(args,**kwargs):
            invocations.append((args,kwargs))
            return Mock(returncode=0,stdout='{"status":"RESEARCH_PROPOSAL_ONLY"}')
        result=probe("/tmp/read-only-test.db",PROBES,per_item_seconds=20,
                     budget_seconds=100,runner=runner,
                     clock=lambda:0,wall_clock=lambda:1791499800)
        self.assertEqual(result["proposal_count"],4)
        self.assertEqual(result["tested_count"],4)
        self.assertFalse(result["v2_http_called"])
        for argv,kwargs in invocations:
            self.assertIn("--db",argv)
            self.assertEqual(argv[argv.index("--db")+1],"/tmp/read-only-test.db")
            self.assertLessEqual(kwargs["timeout"],20)
            self.assertNotIn("--evidence-db",argv)

    def test_enforces_shared_budget_and_per_worker_timeout(self):
        counts=[0]
        def clock():
            counts[0]+=1
            # First item may begin; all following items exceed the shared budget.
            return 0 if counts[0]<=3 else 5
        result=probe("/tmp/read-only-test.db",PROBES,
                     per_item_seconds=3,budget_seconds=3,
                     runner=lambda *a,**k: Mock(returncode=0,stdout='{}'),
                     clock=clock,wall_clock=lambda:1791499800)
        self.assertEqual(result["tested_count"],1)
        self.assertTrue(all(r["status"]=="SKIPPED_BUDGET" for r in result["items"][1:]))

    def test_timeout_is_recorded_not_turned_into_success(self):
        def timeout(*args,**kwargs):
            raise subprocess.TimeoutExpired(args[0],kwargs["timeout"])
        r=probe("/tmp/read-only-test.db",PROBES[:1],
                runner=timeout,clock=lambda:0,wall_clock=lambda:1791499800)
        self.assertEqual(r["items"][0]["status"],"WORKER_TIMEOUT")
        self.assertEqual(r["proposal_count"],0)

    def test_bad_limits_raise(self):
        for per,budget in [(0,100),(61,100),(20,10),(20,601)]:
            with self.assertRaises(ValueError):
                probe("/tmp/stock.db",PROBES,per_item_seconds=per,
                      budget_seconds=budget)


if __name__=="__main__":
    unittest.main()
