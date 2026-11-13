import sqlite3
import tempfile
import unittest
from pathlib import Path
from bot.restock_monitor import StockAlertMonitor


class ObservedAlertTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "history.sqlite"
        self.state = Path(self.tmp.name) / "cursor.json"
        self.clock = [1000]
        with sqlite3.connect(self.db) as db:
            db.executescript("""
                CREATE TABLE stock_history (
                    id INTEGER PRIMARY KEY, timestamp INTEGER, country TEXT,
                    item_name TEXT, quantity INTEGER, source TEXT
                );
                CREATE TABLE poll_heartbeats (
                    id INTEGER PRIMARY KEY, timestamp INTEGER, success INTEGER, mode TEXT
                );
                CREATE TABLE country_stock_observations (
                    id INTEGER PRIMARY KEY, received_epoch INTEGER, country TEXT,
                    country_update_epoch INTEGER, clock_status TEXT
                );
                INSERT INTO stock_history VALUES(1,1000,'sou','Xanax',0,'prometheus');
                INSERT INTO poll_heartbeats VALUES(1,1000,1,'poll-cycle');
                INSERT INTO country_stock_observations
                    VALUES(1,1000,'sou',1000,'REPORTED');
            """)
        self.monitor = StockAlertMonitor(self.db, self.state, ["sou:Xanax"],
                                         clock=lambda: self.clock[0])

    def insert(self, quantity, epoch, *, report=True):
        with sqlite3.connect(self.db) as db:
            db.execute("INSERT INTO stock_history(timestamp,country,item_name,quantity,source)"
                       " VALUES(?,?,?,?,?)", (epoch, "sou", "Xanax", quantity, "prometheus"))
            if report:
                db.execute("INSERT INTO poll_heartbeats(timestamp,success,mode)"
                           " VALUES(?,1,'poll-cycle')", (epoch,))
                db.execute("INSERT INTO country_stock_observations"
                           "(received_epoch,country,country_update_epoch,clock_status)"
                           " VALUES(?,'sou',?,'REPORTED')", (epoch, epoch))

    def test_bootstrap_then_one_crossing_no_duplicate_after_reconnect(self):
        self.assertEqual(self.monitor.scan(), [])
        self.clock[0] = 1001
        self.insert(53, 1001)
        alerts = self.monitor.scan()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["quantity"], 53)
        self.assertEqual(self.monitor.scan(), [])
        new_monitor = StockAlertMonitor(self.db, self.state, ["sou:Xanax"],
                                       clock=lambda: self.clock[0])
        self.assertEqual(new_monitor.scan(), [])
        self.insert(70, 1002)
        self.clock[0] = 1002
        self.assertEqual(new_monitor.scan(), [])

    def test_stale_country_clock_blocks_alert(self):
        self.monitor.scan()
        self.clock[0] = 1400
        self.insert(100, 1400, report=False)
        self.assertEqual(self.monitor.scan(), [])

    def test_missing_watch_does_not_alert(self):
        self.monitor.watched_items.clear()
        self.monitor.scan()
        self.clock[0] = 1001
        self.insert(100, 1001)
        self.assertEqual(self.monitor.scan(), [])


if __name__ == "__main__":
    unittest.main()
