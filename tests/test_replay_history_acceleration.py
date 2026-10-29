from pathlib import Path
import sqlite3
import statistics
import tempfile
import unittest
from unittest.mock import patch
from services import history_service as h
from research.replay_history_acceleration import cached_history


class CacheTests(unittest.TestCase):
    def test_exact_integer_leave_one_out_means_and_restoration(self):
        original=h._leave_one_out_mean
        samples=[[1],[1,2],[1,2,6],[10**30,10**30+1,10**30+9],[-9,2,6],[3,3,3]]
        with cached_history():
            for values in samples:
                for i in range(len(values)):
                    expected=statistics.mean(values[:i]+values[i+1:]) if len(values)>1 else None
                    actual=h._leave_one_out_mean(values,i)
                    self.assertEqual(expected,actual);self.assertEqual(type(expected),type(actual))
            self.assertEqual(original([1.5,3.5,9.3],0),h._leave_one_out_mean([1.5,3.5,9.3],0))
        self.assertIs(original,h._leave_one_out_mean)

    def test_gap_metadata_change_invalidates_cached_intervals(self):
        calls=[]
        def query(a,b):calls.append((a,b));return {'version':len(calls)}
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/'causal.sqlite'
            with sqlite3.connect(db) as con:
                con.executescript("CREATE TABLE poll_heartbeats(timestamp,mode); INSERT INTO poll_heartbeats VALUES(10,'poll-cycle'); CREATE TABLE collection_gaps(start_timestamp,end_timestamp,reason);")
            with patch.object(h,'_collection_gap_overlap',side_effect=query),cached_history() as advance:
                advance(db,100)
                self.assertEqual(h._collection_gap_overlap(20,40),h._collection_gap_overlap(20,40))
                advance(db,110);h._collection_gap_overlap(20,40)
                self.assertEqual(1,len(calls))
                with sqlite3.connect(db) as con:con.execute("INSERT INTO collection_gaps VALUES(30,40,'new knowledge')")
                advance(db,120);h._collection_gap_overlap(20,40)
                self.assertEqual(2,len(calls))
                with self.assertRaises(ValueError):advance(db,120)


if __name__=='__main__':unittest.main()
