"""All 236 rows are represented, with no implied live accuracy or execution."""
import tempfile
import unittest
from pathlib import Path
from research.v38_catalog_seed import build_registry,seed
from research.v38_prediction_store import read,open_writer,record


class CatalogSeedTests(unittest.TestCase):
    def test_frozen_count_and_pending_classes(self):
        roster=build_registry()
        self.assertEqual(len(roster),236)
        self.assertEqual(sum(x["live_adapter"] for x in roster.values()),16)
        self.assertEqual(roster["jap:Xanax"]["status"],"SPECIALIST_NOT_INTEGRATED")
        self.assertEqual(roster["uni:Red Fox Plushie"]["status"],
                         "SPECIALIST_NOT_INTEGRATED")
        self.assertEqual(roster["uni:Heather"]["status"],
                         "BENCHMARK_GATED_ADAPTER")

    def test_dry_run_is_nonwriting(self):
        with tempfile.TemporaryDirectory() as d:
            side=Path(d)/"never-created.db"
            out=seed(side)
            self.assertEqual(out["items"],236)
            self.assertFalse(side.exists())

    def test_all_rows_fallback_and_seed_idempotent(self):
        now=1791540000
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"research.db"
            seed(path,execute=True,now=now)
            rows=read(path,now,limit=236)
            self.assertEqual(len(rows),236)
            self.assertTrue(all(r["fallback_required"] for r in rows))
            self.assertTrue(all(r["recommended_departure_timestamp"] is None
                                for r in rows))
            # Never overwrite actual research results on a second seed.
            with open_writer(path) as con:
                record(con,key="uni:Heather",family="V18",config="dyn3",
                       output={"status":"WORKER_TIMEOUT"},now=now+100,
                       stock_as_of=now+70,executed=True)
            seed(path,execute=True,now=now+120)
            self.assertEqual(read(path,now+120,"uni:Heather")["worker_status"],
                             "WORKER_TIMEOUT")


if __name__=="__main__":
    unittest.main()
