"""Safety tests for the opt-in V38 serial planner (no VM services)."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from research.v38_budgeted_runner import choose,run_tick,PINNED_WORKERS
from research.v38_prediction_store import read

NOW=1791540000


class BudgetedRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.stock=Path(self.tmp.name)/"stock.db"
        self.side=Path(self.tmp.name)/"side.db"
        with sqlite3.connect(self.stock) as c:
            c.execute("""CREATE TABLE stock_history(
                id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,
                item_name TEXT,quantity INTEGER)""")
            c.execute("CREATE TABLE collection_gaps(id INTEGER PRIMARY KEY)")
            c.execute("INSERT INTO stock_history VALUES(1,?,?,?,?)",
                      (NOW-30,"uni","Heather",40))
            c.execute("INSERT INTO stock_history VALUES(2,?,?,?,?)",
                      (NOW-30,"can","Wolverine Plushie",40))

    def test_explicit_opt_in_default_never_touches_collector(self):
        out=run_tick(stock_db="/nonexistent/collector.db",
                     sidecar_db=self.side,now=NOW)
        self.assertEqual(out["mode"],"PLAN_ONLY")
        self.assertFalse(self.side.exists())
        self.assertFalse(out["collector_written"])
        self.assertEqual(len(out["plan"]["pending_specialists"]),6)

    def test_six_missing_specialists_never_route_to_wrong_model(self):
        roster={"jap:Xanax":{},"arg:Monkey Plushie":{},
                "uni:Heather":{}}
        selection=choose(roster,{},now=NOW,active=("jap:Xanax","uni:Heather"))
        self.assertEqual(selection["execute"],["uni:Heather"])
        self.assertEqual(selection["pending_specialists"],
                         ["arg:Monkey Plushie","jap:Xanax"])

    def test_capped_bootstrap_and_valid_proposal(self):
        first=run_tick(stock_db=self.stock,sidecar_db=self.side,
                       execute=True,max_rows=1,now=NOW)
        self.assertEqual(first["mode"],"SOURCE_BOOTSTRAP")
        self.assertEqual(first["executed"],[])
        def fake(args,**kwargs):
            self.assertIn("research.v38_v18_single_tick",args)
            self.assertLessEqual(kwargs["timeout"],20)
            return Mock(returncode=0,stdout=(
                '{"status":"RESEARCH_PROPOSAL_ONLY",'
                '"recommended_departure_timestamp":'+str(NOW+600)+','
                '"recommended_arrival_timestamp":'+str(NOW+6960)+','
                '"quantity_threshold":30,"grace_seconds":10,'
                '"replan_step_seconds":300,"probability_calibrated":false}'))
        out=run_tick(stock_db=self.stock,sidecar_db=self.side,execute=True,
                     max_rows=10,max_jobs=1,active=["uni:Heather"],
                     now=NOW,runner=fake,clock=lambda:0)
        self.assertEqual(out["mode"],"EXECUTED_RESEARCH_ONLY")
        self.assertEqual(out["executed"][0]["item_key"],"uni:Heather")
        self.assertEqual(out["executed"][0]["status"],"RESEARCH_PROPOSAL_ONLY")
        self.assertFalse(read(self.side,NOW,"uni:Heather")["fallback_required"])

    def test_invalid_subprocess_remains_abstention(self):
        out=run_tick(stock_db=self.stock,sidecar_db=self.side,execute=True,
                     max_jobs=1,active=["uni:Heather"],now=NOW,
                     runner=lambda *a,**k: Mock(returncode=5,stdout=""),
                     clock=lambda:0)
        self.assertEqual(out["executed"][0]["status"],"WORKER_ERROR")
        self.assertTrue(read(self.side,NOW,"uni:Heather")["fallback_required"])

    def test_resource_limits_and_adapters_are_pinned(self):
        self.assertEqual(len(PINNED_WORKERS),16)
        with self.assertRaises(ValueError):
            run_tick(stock_db=self.stock,sidecar_db=self.side,execute=True,
                     max_jobs=17)
        with self.assertRaises(ValueError):
            run_tick(stock_db=self.stock,sidecar_db=self.side,execute=True,
                     worker_seconds=50,budget_seconds=20)


if __name__=="__main__":
    unittest.main()
