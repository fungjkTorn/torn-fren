"""Offline 6-core controller: safe roster, resume, metadata, reports."""
from pathlib import Path
import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_pc_historical_sixcore as pc


class PcHistoricalTests(unittest.TestCase):
    def test_roster_is_exact_24_with_all_medication_specialties(self):
        roster=pc.exact_roster()
        self.assertEqual(len(roster),24)
        self.assertEqual(len(set(roster)),24)
        self.assertIn("jap:Xanax",roster)
        self.assertIn("can:Xanax",roster)
        self.assertIn("uni:Xanax",roster)
        self.assertIn("uni:Nessie Plushie",roster)

    def test_each_worker_runs_pinned_readonly_independent_item_process(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/"stock.db"
            out=Path(td)/"task"
            cmd=pc.commands_for("jap:Xanax",source=source,sha="a"*40,
                                days=6,target=out)
            self.assertEqual(cmd[1:3],["-m","research.restock_event_clock"])
            self.assertEqual(cmd[cmd.index("--item-key")+1],"jap:Xanax")
            self.assertEqual(cmd[cmd.index("--days")+1],"6")
            self.assertEqual(cmd[cmd.index("--source")+1],str(source))
            self.assertEqual(cmd[cmd.index("--out")+1],str(out))

    def test_local_source_never_requires_vm_api_or_write_connection(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"sample.db"
            with closing(sqlite3.connect(path)) as db:
                db.execute("CREATE TABLE stock_history(timestamp INTEGER)")
                db.execute("CREATE TABLE collection_gaps(start_timestamp INTEGER)")
                db.execute("CREATE TABLE poll_heartbeats(timestamp INTEGER,mode TEXT,success INTEGER)")
                db.execute("INSERT INTO poll_heartbeats VALUES(12345,'poll-cycle',1)")
                db.commit()
            before=pc.hash_source(path)
            found,meta=pc.verify_local_source(path)
            self.assertEqual(found,path.resolve())
            self.assertEqual(meta["max_heartbeat_epoch"],12345)
            self.assertEqual(pc.hash_source(path),before)

    def test_scores_are_explicitly_later_and_no_automatic_winner(self):
        entry={"starts":24,"scored":12,"success_fraction":0.75,
               "departure_coverage":0.5,"mean_wait_minutes":44.0,
               "matched_vs_now":{"matched_resolved":9,
                  "challenger_only_success":3,"baseline_only_success":1}}
        report={"item_key":"mex:Jaguar Plushie","restock_timing":{
                    "phase_empirical":{"chronological_slices":{
                        "later_validation":{"scored":9,
                         "distinct_target_restocks":3,
                         "mean_absolute_error_minutes":15.0}}}},
                "chronological_slices":{"later_validation":{
                    "phase_empirical_expected":entry,"leave_now":entry}}}
        rows=pc.score_rows("mex:Jaguar Plushie",report)
        self.assertEqual(len(rows),18)
        r=next(x for x in rows if x["split"]=="later_validation"
               and x["policy"]=="phase_empirical_expected")
        self.assertEqual(r["restock_distinct_targets"],3)
        self.assertEqual(r["model_only_hits"],3)
        self.assertEqual(r["leave_now_only_hits"],1)
        self.assertEqual(r["flight_success_fraction"],0.75)

    def test_summary_cannot_claim_complete_when_any_item_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);src=root/"input.db"
            report={"item_key":"mex:Jaguar Plushie","_local_model_sha":"a"*40,
                    "_local_days":1,"production_promotion":False,
                    "restock_timing":{},"chronological_slices":{}}
            out=pc.write_summary(root,source=src,source_sha="1"*64,
                    sha="a"*40,days=1,
                    requested=["mex:Jaguar Plushie","jap:Xanax"],
                    outcomes={"mex:Jaguar Plushie":{"status":"COMPLETED","result":report},
                              "jap:Xanax":{"status":"ERROR","error":"fixture"}})
            self.assertEqual(out["status"],"PARTIAL_NO_PROMOTION")
            self.assertEqual(out["completed"],1)
            self.assertFalse(out["automatic_model_promotion"])
            self.assertTrue((root/"scores.csv").is_file())
            self.assertTrue((root/"summary.json").is_file())

    def test_bad_worker_or_day_count_rejected(self):
        with self.assertRaises(SystemExit):
            pc.main(["--source","/notfound.db","--workers","7"])
        with self.assertRaises(SystemExit):
            pc.main(["--source","/notfound.db","--days","7"])


if __name__ == "__main__":
    unittest.main()
