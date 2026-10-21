import sqlite3
import tempfile
import unittest
from pathlib import Path
from research.causal_replay_slice import CausalReplaySlice
from research.matched_champion_audit import causal_copy,native_plan


class SliceTests(unittest.TestCase):
    def test_incremental_matches_fresh_copies_including_late_gap_closure(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/'source.db'
            with sqlite3.connect(source) as c:
                c.executescript('''CREATE TABLE stock_history(id INTEGER PRIMARY KEY,timestamp,country,item_name,quantity,source);
                CREATE TABLE poll_heartbeats(timestamp,mode,success);
                CREATE TABLE collection_gaps(start_timestamp,end_timestamp);
                INSERT INTO stock_history VALUES(1,90,'can','Xanax',0,'a'),(2,110,'can','Xanax',100,'a'),(3,110,'can','Xanax',90,'a'),(4,140,'can','Xanax',0,'a');
                INSERT INTO poll_heartbeats VALUES(99,'poll-cycle',1),(111,'poll-cycle',1),(149,'poll-cycle',1);
                INSERT INTO collection_gaps VALUES(80,125),(130,NULL);''')
            before=source.read_bytes()
            with CausalReplaySlice(source,root/'incremental.db') as mirror:
                for t in (100,120,150):
                    incremental=mirror.advance(t);fresh=root/('fresh-%s.db'%t);causal_copy(source,fresh,t)
                    with sqlite3.connect(incremental) as a,sqlite3.connect(fresh) as b:
                        for table in ('stock_history','poll_heartbeats','collection_gaps'):
                            self.assertEqual(a.execute('SELECT * FROM '+table).fetchall(),b.execute('SELECT * FROM '+table).fetchall())
                    # Real adapter must see exactly the same truncated evidence.
                    self.assertEqual(native_plan(incremental,'can:Xanax',t)['departure'],native_plan(fresh,'can:Xanax',t)['departure'])
                with self.assertRaises(ValueError):mirror.advance(140)
            self.assertFalse((root/'incremental.db').exists());self.assertEqual(source.read_bytes(),before)
