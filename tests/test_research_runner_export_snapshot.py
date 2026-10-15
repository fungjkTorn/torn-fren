"""Research snapshot contains ONLY allowlisted stock data; never original DB secrets."""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location(
    "restricted_snapshot",ROOT/"deploy/research_runner/export_snapshot.py")
mod=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

KEYS=[
    "mex:Jaguar Plushie","uni:Nessie Plushie","jap:Xanax"
]


def fixture(root):
    root=Path(root)
    src=root/"original-live.db"
    private=root/"snapshot-dir"
    private.mkdir(mode=0o700)
    private.chmod(0o700)
    roster=root/"v38_roster.json"
    base={f"mex:Item {i:02}":{} for i in range(19)}
    base.update({key:{} for key in KEYS})
    base.pop("jap:Xanax") # Japan is among the canonical 22
    base["jap:Xanax"]={}
    assert len(base)==22
    # exact extras are added by exporter
    roster.write_text(json.dumps({"items":base}),encoding="utf8")
    with sqlite3.connect(src) as db:
        db.executescript("""
        CREATE TABLE stock_history(
            id INTEGER PRIMARY KEY,timestamp INTEGER,quantity INTEGER,
            source TEXT,country TEXT,item_name TEXT,
            secret_api_token TEXT DEFAULT NULL);
        CREATE TABLE collection_gaps(start_timestamp INTEGER,end_timestamp INTEGER,
            secret_info TEXT DEFAULT NULL);
        CREATE TABLE poll_heartbeats(timestamp INTEGER,mode TEXT,success INTEGER,
            internal_agent_secret TEXT DEFAULT NULL);
        CREATE TABLE player_api_keys(player_id INTEGER,api_key TEXT);
        INSERT INTO player_api_keys VALUES(4321,'SENSITIVE_DO_NOT_COPY');
        INSERT INTO poll_heartbeats VALUES(100000,'poll-cycle',1,'HEARTBEAT_SECRET');
        INSERT INTO poll_heartbeats VALUES(100200,'poll-cycle',1,'HEARTBEAT_SECRET');
        INSERT INTO collection_gaps VALUES(99900,99920,'SENSITIVE_GAP');
        """)
        for key in base:
            c,item=key.split(":",1)
            for t,q in ((100,0),(100100,0),(100150,50),
                        (100180,0),(100250,120)):
                db.execute(
                    """INSERT INTO stock_history
                       (timestamp,quantity,source,country,item_name,secret_api_token)
                       VALUES(?,?,?,?,?,?)""",
                    (t,q,"yata",c,item,"SHOULD_NOT_COPY"))
    return src,roster,private


class SnapshotTests(unittest.TestCase):
    def test_no_secret_column_or_game_identifiers_and_consistent_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,roster,dst=fixture(tmp)
            result=mod.export(src,roster,dst/"history.db",
                              asof=100300,days=14)
            self.assertEqual(result["items"],24)
            self.assertEqual(result["status"],"RESEARCH_SNAPSHOT_READY")
            path=dst/"history.db"
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o640)
            with sqlite3.connect(path) as db:
                tables={row[0] for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertEqual(tables,{"stock_history","collection_gaps",
                    "poll_heartbeats","research_metadata","country_stock_observations"})
                cols=[r[1] for r in db.execute("PRAGMA table_info(stock_history)")]
                self.assertEqual(cols,["id","timestamp","quantity",
                                       "source","country","item_name"])
                self.assertEqual(
                    db.execute("SELECT COUNT(*) FROM stock_history").fetchone()[0],
                    len(json.loads(roster.read_text())["items"])*5)
                self.assertEqual(
                    db.execute("SELECT COUNT(*) FROM poll_heartbeats").fetchone()[0],2)
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0],"ok")
                self.assertEqual(db.execute(
                    "SELECT value FROM research_metadata WHERE key='sanitized_stock_only'"
                ).fetchone()[0],"true")
            raw=path.read_bytes()
            for secret in (b"SENSITIVE_DO_NOT_COPY",b"HEARTBEAT_SECRET",
                           b"SHOULD_NOT_COPY",b"SENSITIVE_GAP",b"player_api_keys"):
                self.assertNotIn(secret,raw)

    def test_optional_country_clocks_are_allowlisted_bounded_and_not_backfilled(self):
        from services.country_freshness import DDL,record
        with tempfile.TemporaryDirectory() as tmp:
            src,roster,dst=fixture(tmp)
            path=dst/'history.db'
            mod.export(src,roster,path,asof=100300,days=14)
            with sqlite3.connect(path) as cx:
                self.assertEqual(cx.execute('SELECT count(*) FROM country_stock_observations').fetchone()[0],0)
                self.assertEqual(cx.execute("SELECT value FROM research_metadata WHERE key='country_clock_schema_available'").fetchone()[0],'false')
            with sqlite3.connect(src) as cx:
                cx.executescript(DDL)
                cx.execute('ALTER TABLE country_stock_observations ADD COLUMN secret TEXT')
                for receipt,update in ((100100,100000),(100200,100000),(100400,100399)):
                    record(cx,'jap',{'update':update,'stocks':[{}]},'yata',receipt,receipt)
                cx.execute("UPDATE country_stock_observations SET secret='COUNTRY_SECRET'")
            before=src.read_bytes()
            mod.export(src,roster,path,asof=100300,days=14)
            self.assertEqual(src.read_bytes(),before)
            with sqlite3.connect(path) as cx:
                rows=cx.execute('SELECT received_epoch,country_update_epoch FROM country_stock_observations').fetchall()
                self.assertEqual(rows,[(100100,100000),(100200,100000)])
                self.assertNotIn('secret',[x[1] for x in cx.execute('PRAGMA table_info(country_stock_observations)')])
            self.assertNotIn(b'COUNTRY_SECRET',path.read_bytes())

    def test_snapshot_replaces_atomically_without_writing_collector(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,roster,dst=fixture(tmp)
            before=src.read_bytes()
            path=dst/"history.db"
            mod.export(src,roster,path,asof=100300,days=14)
            original=path.read_bytes()
            mod.export(src,roster,path,asof=100180,days=14)
            self.assertNotEqual(path.read_bytes(),original)
            self.assertEqual(src.read_bytes(),before)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute(
                    "SELECT max(timestamp) FROM stock_history").fetchone()[0],100180)

    def test_invalid_destination_and_row_count_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,roster,dst=fixture(tmp)
            with self.assertRaises(ValueError):
                mod.export(src,roster,src,asof=100300,days=14)
            with self.assertRaises(ValueError):
                mod.export(src,roster,dst/"history.db",
                           asof=100300,days=3)
            with self.assertRaises(ValueError):
                mod.export(src,roster,dst/"history.db",
                           asof=100300,days=14,max_total=2400,
                           max_rows=2)
            self.assertFalse((dst/"history.db").exists())
            dst.chmod(0o755)
            with self.assertRaisesRegex(ValueError,"export directory"):
                mod.export(src,roster,dst/"history.db",asof=100300,days=14)


def roster_and_extras(path):
    return set(json.loads(Path(path).read_text())["items"])|mod.BASE_EXTRAS


if __name__=="__main__":
    unittest.main()
