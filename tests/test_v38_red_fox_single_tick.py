"""Frozen Red Fox algorithm routing and future-data safety."""
import unittest
from unittest.mock import patch,Mock
from types import SimpleNamespace
from research import v38_red_fox_single_tick as red

NOW=1791540300


class RedFoxSingleTickTests(unittest.TestCase):
    def test_wrong_item_never_reads_source(self):
        with patch.object(red,"inspect_live_source") as inspector:
            self.assertEqual(red.predict("/no/db","jap","Xanax",NOW)["status"],
                             "NOT_APPROVED_RED_FOX_ANALOG")
            inspector.assert_not_called()

    def test_stale_or_future_source_rejected_before_model(self):
        with patch.object(red,"inspect_live_source",
                          return_value={"status":"FUTURE_RECORDS_PRESENT"}):
            with patch.object(red.ResearchContext,"build") as builder:
                self.assertEqual(red.predict("unused","uni","Red Fox Plushie",NOW)["status"],
                                 "FUTURE_RECORDS_PRESENT")
                builder.assert_not_called()

    def test_k18_and_global_weight_exact_and_causal_query(self):
        context=SimpleNamespace(grid=[NOW],con=Mock())
        with patch.object(red,"inspect_live_source",return_value={"status":"FRESH"}):
            with patch.object(red.ResearchContext,"build",return_value=context):
                with patch.object(red,"AnalogPlanner") as constructor:
                    constructor.return_value.plan.return_value=(NOW+600,.7,.7)
                    out=red.predict("unused","uni","Red Fox Plushie",NOW)
        self.assertEqual(out["status"],"RESEARCH_PROPOSAL_ONLY")
        self.assertEqual(out["recommended_arrival_timestamp"],
                         NOW+600+red.TRAVEL_SECONDS["uni"])
        self.assertEqual(constructor.call_args.kwargs["k"],18)
        self.assertEqual(constructor.call_args.kwargs["global_weight"],0.5)
        self.assertEqual(constructor.call_args.kwargs["cutoff"],NOW)
        self.assertFalse(out["probability_calibrated"])
        self.assertEqual(out["quantity_threshold"],30)
        self.assertEqual(out["grace_seconds"],10)
        context.con.close.assert_called_once()

    def test_live_builder_uses_heartbeat_attested_asof_without_rw(self):
        context=SimpleNamespace(grid=[NOW],con=Mock())
        with patch.object(red,"inspect_live_source",return_value={"status":"FRESH"}):
            with patch.object(red.ResearchContext,"build",return_value=context) as builder:
                with patch.object(red,"AnalogPlanner") as planner:
                    planner.return_value.plan.return_value=(NOW+300,.5,.5)
                    result=red.predict("unused","uni","Red Fox Plushie",NOW)
        self.assertEqual(result["status"],"RESEARCH_PROPOSAL_ONLY")
        builder.assert_called_once_with("unused",asof=NOW,readonly=True)

    def test_lagging_joint_context_abstains(self):
        context=SimpleNamespace(grid=[NOW-900],con=Mock())
        with patch.object(red,"inspect_live_source",return_value={"status":"FRESH"}):
            with patch.object(red.ResearchContext,"build",return_value=context):
                self.assertEqual(red.predict("unused","uni","Red Fox Plushie",NOW)["status"],
                                 "CROSS_ITEM_CONTEXT_LAGGING")


    def test_asof_context_extends_quiet_stock_without_hindsight(self):
        import sqlite3,tempfile
        from pathlib import Path
        from research.plushie_champions.common import ResearchContext, STEP
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"readonly.db"
            with sqlite3.connect(db) as con:
                con.execute("CREATE TABLE stock_history(timestamp INTEGER,country TEXT,item_name TEXT,quantity INTEGER,source TEXT)")
                con.execute("CREATE TABLE collection_gaps(start_timestamp INTEGER,end_timestamp INTEGER)")
                con.executemany("INSERT INTO stock_history VALUES(?,?,?,?,?)",[
                    (NOW-600,"uni","Red Fox Plushie",55,"test"),
                    (NOW-300,"uni","Red Fox Plushie",45,"test")])
            asof=ResearchContext.build(db,targets=[("uni","Red Fox Plushie")],
                                       asof=NOW,readonly=True)
            try:
                self.assertEqual(asof.grid[-1],NOW)
                self.assertEqual(asof.qty[0,-1],45)
                self.assertEqual(asof.active[0,-1],1)
            finally:
                asof.con.close()
            old=ResearchContext.build(db,targets=[("uni","Red Fox Plushie")])
            try:
                self.assertEqual(old.grid[-1],NOW-300)
            finally:
                old.con.close()

    def test_asof_rejects_future_stock_in_context(self):
        import sqlite3,tempfile
        from pathlib import Path
        from research.plushie_champions.common import ResearchContext
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/"readonly.db"
            with sqlite3.connect(db) as con:
                con.execute("CREATE TABLE stock_history(timestamp INTEGER,country TEXT,item_name TEXT,quantity INTEGER,source TEXT)")
                con.execute("CREATE TABLE collection_gaps(start_timestamp INTEGER,end_timestamp INTEGER)")
                con.execute("INSERT INTO stock_history VALUES(?,?,?,?,?)",
                            (NOW+300,"uni","Red Fox Plushie",55,"test"))
            with self.assertRaises(ValueError):
                ResearchContext.build(db,targets=[("uni","Red Fox Plushie")],
                                      asof=NOW,readonly=True)

if __name__=="__main__":
    unittest.main()
