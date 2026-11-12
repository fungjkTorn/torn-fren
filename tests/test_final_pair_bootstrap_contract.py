"""Verifies the isolated final-pair/Japan full-export bootstrap contract.

No VM DB, API key, systemd service or production path is accessed.
"""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from deploy.research_runner.export_snapshot import DDL
from services.challenger_live import bootstrap


class FinalPairBootstrapContractTests(unittest.TestCase):
    def test_japan_only_reseed_does_not_read_other_cohort_and_collector_is_untouched(self):
        with tempfile.TemporaryDirectory() as td:
            collector=Path(td)/"collector.sqlite"
            export=Path(td)/"japan-private.sqlite"
            now=int(time.time())-5
            with closing(sqlite3.connect(collector)) as db:
                db.executescript(DDL)
                for country,item in (("jap","Xanax"),("can","Xanax")):
                    db.execute(
                        "INSERT INTO stock_history(timestamp,quantity,source,country,item_name) VALUES(?,?,?,?,?)",
                        (now-10,100,"fixture",country,item))
                    db.execute(
                        """INSERT INTO country_stock_observations(
                        received_epoch,country,source,country_update_epoch,
                        export_epoch,clock_status,export_clock_status,item_count)
                        VALUES(?,?,?,?,?,?,?,?)""",
                        (now,country,"fixture",now,now,"FRESH","FRESH",1))
                db.execute("INSERT INTO poll_heartbeats(timestamp,mode,success,source) VALUES(?,?,?,?)",
                           (now,"poll-cycle",1,"fixture"))
                db.commit()
            before=collector.read_bytes()
            result=bootstrap(str(collector),str(export),
                model_roster={"jap:Xanax":("JAPAN_QUANTITY_RATE","strict31")})
            self.assertEqual(result["status"],"CHALLENGER_SOURCE_READY")
            self.assertFalse(result["collector_modified"])
            self.assertEqual(collector.read_bytes(),before)
            with closing(sqlite3.connect(export)) as db:
                rows=db.execute("SELECT DISTINCT country,item_name FROM stock_history").fetchall()
                clocks=db.execute("SELECT DISTINCT country FROM country_stock_observations").fetchall()
                self.assertEqual(rows,[("jap","Xanax")])
                self.assertEqual(clocks,[("jap",)])
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0],"ok")

    def test_export_requires_new_filename(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"existing.sqlite"
            path.write_text("do not overwrite")
            with self.assertRaises(ValueError):
                bootstrap(path,path,model_roster={"jap:Xanax":("JAPAN_QUANTITY_RATE","strict31")})
            self.assertEqual(path.read_text(),"do not overwrite")


if __name__=="__main__":
    unittest.main()
