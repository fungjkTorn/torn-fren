import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research.v29_prefix_lookahead_audit import completed_peaks,tiny_flags,compare_one,audit


def history_for_peaks(peaks):
    rows=[(100,0)]
    t=200
    for peak in peaks:
        rows.append((t,peak))
        rows.append((t+60,0))
        t+=120
    return rows


class PrefixSensitivityTests(unittest.TestCase):
    def test_future_outlier_changes_historical_tiny_flag(self):
        rows=history_for_peaks([2,10,10,1000])
        s=compare_one(rows,510)
        self.assertEqual(s["precutoff_raw_cycles"],3)
        self.assertEqual(s["future_peaks_change_tiny_flag_count"],1)

    def test_truncating_at_cutoff_has_no_lookahead(self):
        rows=history_for_peaks([2,10,10,1000])
        earlier=[r for r in rows if r[0]<=510]
        self.assertEqual(compare_one(earlier,510)["future_peaks_change_tiny_flag_count"],0)
        self.assertEqual(len(completed_peaks(earlier)),3)

    def test_missing_database_never_gets_created(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"missing.db"
            with self.assertRaises(FileNotFoundError):
                audit(path,510)
            self.assertFalse(path.exists())

    def test_sqlite_audit_is_read_only(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"history.db"
            with sqlite3.connect(p) as con:
                con.executescript("""CREATE TABLE stock_history
                    (timestamp INTEGER,country TEXT,item_name TEXT,quantity INTEGER);""")
                con.executemany("INSERT INTO stock_history VALUES (?,?,?,?)",
                    [(ts,"arg","Testing Stock",q) for ts,q in history_for_peaks([2,10,10,1000])])
            data=audit(p,510)
            self.assertEqual(data["affected_keys"],["arg:Testing Stock"])
            self.assertTrue(p.exists())


if __name__=="__main__":
    unittest.main()
