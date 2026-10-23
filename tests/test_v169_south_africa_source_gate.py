"""Regression for recovered 25th research item, without expanding live roster."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from research.japan_xanax.renewal_shadow import (
    RESEARCH_ONLY_ADDITIONAL_ITEMS, source_data,
)
from deploy.scripts.v163_readonly_event_first_preview import exact_roster


class SouthAfricaResearchSourceGateTests(unittest.TestCase):
    def _fixture(self,root):
        db=root/"history.db"
        with sqlite3.connect(db) as cx:
            cx.executescript("""
                CREATE TABLE stock_history(
                    id INTEGER PRIMARY KEY,
                    timestamp INTEGER, quantity INTEGER,
                    source TEXT, country TEXT, item_name TEXT
                );
                CREATE TABLE poll_heartbeats(
                    id INTEGER PRIMARY KEY,
                    timestamp INTEGER, mode TEXT, success INTEGER, source TEXT
                );
                CREATE TABLE collection_gaps(
                    start_timestamp INTEGER,end_timestamp INTEGER
                );
                INSERT INTO stock_history(timestamp,quantity,source,country,item_name)
                VALUES
                    (1000000,0,'yata','sou','Xanax'),
                    (1000500,1000,'yata','sou','Xanax'),
                    (1000750,50,'yata','sou','Xanax'),
                    (1001000,0,'yata','sou','Xanax'),
                    (1000000,0,'yata','jap','Xanax');
                INSERT INTO poll_heartbeats(timestamp,mode,success,source)
                VALUES (1000000,'poll-cycle',1,'yata'),
                       (1000500,'poll-cycle',1,'yata'),
                       (1001000,'poll-cycle',1,'yata');
            """)
        return db

    def test_south_africa_xanax_accepted_research_only_without_production_expansion(self):
        self.assertEqual(RESEARCH_ONLY_ADDITIONAL_ITEMS,frozenset({"sou:Xanax"}))
        self.assertNotIn("sou:Xanax",set(exact_roster()))
        self.assertIn("jap:Xanax",set(exact_roster()))
        with tempfile.TemporaryDirectory() as td:
            db=self._fixture(Path(td))
            before=db.read_bytes()
            rows,polls,_crosses,evidence,cutoff=source_data(
                db,now=1001000,item_key="sou:Xanax")
            self.assertEqual(cutoff,1001000)
            self.assertEqual(len(rows),4)
            self.assertEqual(rows[1][1],1000)
            self.assertEqual(polls[-1],1001000)
            self.assertIsNotNone(evidence)
            self.assertEqual(db.read_bytes(),before)

    def test_loader_retains_old_japan_and_rejects_unknown_country_item(self):
        with tempfile.TemporaryDirectory() as td:
            db=self._fixture(Path(td))
            self.assertEqual(len(source_data(
                db,now=1001000,item_key="jap:Xanax")[0]),1)
            for key in ("sou:Fake Xanax","madeup:Xanax",""):
                with self.subTest(key=key):
                    with self.assertRaisesRegex(ValueError,"Unverified item key"):
                        source_data(db,now=1001000,item_key=key)


if __name__=="__main__":
    unittest.main()
