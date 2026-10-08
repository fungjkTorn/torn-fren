"""No-live-side-effects tests for frozen champion replay orchestration."""
import unittest
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
from services.frozen_champion_shadow_v24 import (
    _match,_resolve_config,_champion_entries,OLD_NATIVE,
    _install_frozen_readonly_history,_digest_file
)

class FrozenReplayTests(unittest.TestCase):
    def test_all_start_denominator_and_pairwise_outcomes(self):
        x={"shared_starts":3,"eligible_start_times":[10,20,30],
           "versions":{
              "v19":{"rows":[{"start":10,"success":True},{"start":20,"success":False}]},
              "v21":{"rows":[{"start":10,"success":False},
                               {"start":20,"success":True},{"start":30,"success":True}]}
           }}
        r=_match(x)
        self.assertEqual(r["common_starts"],3)
        self.assertEqual(r["versions"]["v19"]["hits"],1)
        self.assertEqual(r["versions"]["v19"]["paired_n"],3)
        self.assertAlmostEqual(r["versions"]["v19"]["coverage"],2/3)
        self.assertAlmostEqual(r["versions"]["v19"]["all_start_success_rate"],1/3)
        self.assertEqual(r["versions"]["v19"]["no_recommendation_starts"],1)
        self.assertEqual(r["versions"]["v21"]["hits"],2)
        self.assertEqual(r["head_to_head"]["v19_vs_v21"]["v19_only_successes"],1)
        self.assertEqual(r["head_to_head"]["v19_vs_v21"]["v21_only_successes"],2)

    def test_both_missing_recommendation_not_silently_removed(self):
        data={"shared_starts":4,"eligible_start_times":[10,20,30,40],
              "versions":{"v19":{"rows":[{"start":10,"success":True}]},
                          "v20":{"rows":[]}}}
        result=_match(data)
        self.assertEqual(result["common_starts"],4)
        self.assertEqual(result["versions"]["v19"]["paired_n"],4)
        self.assertEqual(result["versions"]["v20"]["recommendations"],0)
        self.assertEqual(result["versions"]["v20"]["coverage"],0.0)
        self.assertIsNone(result["versions"]["v20"]["conditional_success_rate"])

    def test_reject_malformed_start_sets(self):
        for bad in (
            {"shared_starts":2,"eligible_start_times":[10,10],"versions":{}},
            {"shared_starts":2,"eligible_start_times":[10],"versions":{}},
            {"shared_starts":1,"eligible_start_times":[10],
             "versions":{"v19":{"rows":[{"start":20,"success":True}]}}},
            {"shared_starts":1,"eligible_start_times":[10],
             "versions":{"v19":{"rows":[{"start":10,"success":True},
                                      {"start":10,"success":False}]}}},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                _match(bad)

    def test_v20_default_replan_is_900_not_300(self):
        self.assertEqual(OLD_NATIVE["v19"]["replan_step"],300)
        self.assertEqual(OLD_NATIVE["v20"]["replan_step"],900)
        self.assertEqual(OLD_NATIVE["v20"]["departure_grid"],300)
        self.assertEqual(OLD_NATIVE["v21"]["replan_step"],900)

    def test_frozen_config_not_selected_afresh(self):
        entry={"key":"arg:Tear Gas","provisional_model":"v19"}
        models={"v19":{"results":{"arg:Tear Gas":{
            "status":"complete","selected_on_training":{"config":{"name":"dyn3"}}}
        }}}
        ver,cfg,item=_resolve_config(entry,models)
        self.assertEqual(ver,"v19")
        self.assertEqual(cfg["name"],"dyn3")

    def test_snapshot_is_never_writable(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/"frozen.db"
            with sqlite3.connect(db) as con:
                con.execute("CREATE TABLE test_stock (quantity INTEGER)")
                con.execute("INSERT INTO test_stock VALUES (30)")
            original=_digest_file(db)
            fake_history=SimpleNamespace()
            _install_frozen_readonly_history(fake_history,db)
            self.assertTrue(fake_history._DB_READY)
            self.assertEqual(fake_history.DB_PATH,db.resolve())
            fake_history.init_db()
            with fake_history._connect() as con:
                self.assertEqual(con.execute("SELECT quantity FROM test_stock").fetchone()[0],30)
                self.assertEqual(con.execute("PRAGMA query_only").fetchone()[0],1)
                with self.assertRaises(sqlite3.OperationalError):
                    con.execute("INSERT INTO test_stock VALUES (40)")
                with self.assertRaises(sqlite3.OperationalError):
                    con.execute("CREATE TABLE forbidden(x)")
            self.assertEqual(_digest_file(db),original)

    def test_only_valid_champions(self):
        self.assertIsNone(_resolve_config({"key":"jap:Xanax","provisional_model":"specialist"},{}))
        self.assertIn("v20",OLD_NATIVE)
        self.assertEqual(len(_champion_entries({"entries":[{"key":"arg:Tear Gas"}]})),1)

if __name__=="__main__":
    unittest.main()
