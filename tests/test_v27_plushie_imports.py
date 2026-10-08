"""Verify imported specialist source and a causal planning contract on a toy database.

This is a tiny executable integration smoke test, *not* a real-stock accuracy claim.
"""
from __future__ import annotations
import importlib
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECIALISTS = ROOT / "research" / "plushie_champions"
sys.path.insert(0, str(SPECIALISTS))
from common import (ResearchContext, AnalogPlanner, TemplatePlanner,
                    TRAVEL_SECONDS, STEP, MAX_WAIT, MIN_QTY, GRACE,
                    PLUSHIES, valid_starts, connect)

FILES = {
    "nessie": "recent_phase_select",
    "redfox": "rf_localgrid",
    "lion": "lion_pair_selector_ml",
    "panda": "panda_pair_selector_ml",
    "monkey/chamois": "checkpoint4_online_selector",
    "camel": "camel_fast_selector",
}

class ImportedChampionSmoke(unittest.TestCase):
    def test_import_all_seven_specialists(self):
        for label, module in FILES.items():
            with self.subTest(label=label):
                self.assertIsNotNone(importlib.import_module(module))
        self.assertEqual(set(importlib.import_module("replay").TARGETS), {"nessie","redfox","lion","panda","camel"})

    def test_contract_matches_handoff(self):
        self.assertEqual((STEP, MAX_WAIT, MIN_QTY, GRACE),(300, 28800, 30, 10))
        self.assertEqual(len(PLUSHIES),10)
        self.assertEqual(TRAVEL_SECONDS["jap"],8940)

    def test_seven_models_keep_winning_config(self):
        mapping = json.loads((ROOT/"research"/"plushie_flower_champions_v26.json").read_text())
        self.assertEqual(len(mapping["items"]),21)
        for m in ("recent_phase_select","rf_localgrid","lion_pair_selector_ml","panda_pair_selector_ml","camel_fast_selector"):
            conf=getattr(importlib.import_module(m),"WINNING_CONFIG")
            self.assertTrue(conf)
        self.assertEqual(importlib.import_module("checkpoint4_online_selector").WINNING_WINDOWS,
                         {"Monkey Plushie":2,"Chamois Plushie":3})

    def test_replay_opens_database_strictly_read_only(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/"db.db"
            self.assertRaises(FileNotFoundError, connect, str(db))
            self.assertFalse(db.exists())
            with sqlite3.connect(db) as con:
                con.execute("create table x(i integer)")
            with connect(str(db)) as con:
                with self.assertRaises(sqlite3.OperationalError):
                    con.execute("insert into x values(1)")

    def test_synthetic_history_planning_without_external_keys(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td)/"fake_stock.db"
            con=sqlite3.connect(db)
            con.executescript("""
            CREATE TABLE stock_history
              (timestamp INTEGER, country TEXT, item_name TEXT, quantity INTEGER, source TEXT);
            CREATE TABLE collection_gaps (start_timestamp INTEGER, end_timestamp INTEGER);
            """)
            epoch=1790000000
            data=[]
            for country,item in PLUSHIES:
                for h in range(24*12):
                    q=100 if h%6<3 else 0
                    data.append((epoch+h*3600,country,item,q,"synthetic"))
            con.executemany("INSERT INTO stock_history VALUES (?,?,?,?,?)",data)
            con.commit();con.close()
            ctx=ResearchContext.build(str(db))
            country,item="uni","Nessie Plushie"
            self.assertTrue(valid_starts(ctx,country,item))
            tl=ctx.timelines[(country,item)]
            q=float(ctx.grid[-1]-2*3600)
            template=TemplatePlanner(ctx,country,item,lags=(1,),lookback=7200,shift_range=3600,minfit=.5)
            t=template.plan(q)
            self.assertIsNotNone(t)
            self.assertGreaterEqual(t[0],q)
            self.assertLessEqual(t[0],q+MAX_WAIT)
            analog=AnalogPlanner(ctx,country,item,k=18,global_weight=.5,cutoff=q)
            a=analog.plan(q)
            self.assertIsNotNone(a)
            self.assertGreaterEqual(a[0],q)
            self.assertLessEqual(a[0],q+MAX_WAIT)

if __name__ == "__main__":
    unittest.main()
