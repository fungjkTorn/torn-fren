"""V71 historical as-issued validation: elapsed departures are not fabricated errors."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research import v71_full20_issued_audit as m
from research.v38_prediction_store import record,open_writer
from research.plushie_champions.common import TRAVEL_SECONDS,STEP

NOW=1791650000
HEARTBEAT=NOW-15
FIVE=("cay:Banana Orchid","cay:Stingray Plushie",
      "mex:Dahlia","uni:Heather","uni:Xanax")


class IssuedAuditTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        self.snapshot=root/"snapshot.db"
        self.sidecar=root/"isolated.db"
        with sqlite3.connect(self.snapshot) as s:
            s.execute("CREATE TABLE poll_heartbeats(timestamp INTEGER, mode TEXT, success INTEGER)")
            s.execute("INSERT INTO poll_heartbeats VALUES(?,'poll-cycle',1)",(HEARTBEAT,))
        self.keys=set(m.exact_roster())|{m.MONKEY}
        self.assertEqual(len(self.keys),20)
        c=open_writer(self.sidecar)
        try:
            for key in sorted(self.keys):
                country=key.split(":",1)[0]
                departure=NOW+(10 if key in FIVE else 1800)
                output={
                    "status":"RESEARCH_PROPOSAL_ONLY",
                    "recommended_departure_timestamp":departure,
                    "recommended_arrival_timestamp":departure+TRAVEL_SECONDS[country],
                    "replan_step_seconds":STEP,"quantity_threshold":30,
                    "grace_seconds":10,"probability_calibrated":False,
                }
                if key==m.MONKEY:
                    family,config=m.FAMILY,m.CONFIG
                else:
                    family,config="frozen-specialist","research-test"
                status=record(c,key=key,family=family,config=config,
                    output=output,now=NOW,stock_as_of=HEARTBEAT,
                    executed=True,next_due=NOW+STEP)
                self.assertEqual(status,"RESEARCH_PROPOSAL_ONLY")
        finally:
            c.close()

    def audit(self,ts=NOW+120):
        return m.audit(self.snapshot,self.sidecar,clock=lambda:ts)

    def test_five_departures_passed_but_20_proposals_were_valid_at_issue(self):
        out=self.audit()
        self.assertEqual(out["status"],m.SUCCESS)
        self.assertTrue(out["verified_as_issued"])
        self.assertEqual(out["historical_valid_proposal_count"],20)
        self.assertEqual(out["persisted_count"],20)
        self.assertEqual(out["frozen_evidence_count"],20)
        self.assertEqual(out["departure_passed_by_audit_count"],5)
        self.assertEqual(out["departure_passed_by_audit"],sorted(FIVE))
        self.assertEqual(out["five_minute_validity_elapsed_count"],0)
        self.assertEqual(out["currently_actionable_in_this_old_snapshot_count"],15)
        self.assertFalse(out["model_20_scheduled"])
        self.assertFalse(out["website_changed"])

    def test_expired_snapshot_does_not_rewrite_historical_evidence(self):
        out=self.audit(NOW+7200)
        self.assertEqual(out["status"],m.SUCCESS)
        self.assertEqual(out["five_minute_validity_elapsed_count"],20)
        self.assertEqual(out["currently_actionable_in_this_old_snapshot_count"],0)

    def test_out_of_bounds_departure_at_issue_fails(self):
        with sqlite3.connect(self.sidecar) as c:
            for table in ("latest_predictions","v42_candidate_decisions"):
                c.execute(f"UPDATE {table} SET departure=? WHERE item_key=?",
                          (NOW-1,m.MONKEY))
        r=self.audit()
        self.assertEqual(r["status"],"V71_FULL20_AS_ISSUED_REJECTED")
        self.assertIn("DEPARTURE_INVALID_AT_ISSUE",r["source_pinned_invalid_issues"][m.MONKEY])

    def test_source_staleness_when_issued_is_a_real_error(self):
        with sqlite3.connect(self.sidecar) as c:
            for table in ("latest_predictions","v42_candidate_decisions"):
                c.execute(f"UPDATE {table} SET stock_as_of=? WHERE item_key=?",
                          (NOW-400,"uni:Heather"))
        r=self.audit()
        self.assertFalse(r["verified_as_issued"])
        self.assertIn("SOURCE_NOT_FRESH_AT_ISSUE",
                      r["source_pinned_invalid_issues"]["uni:Heather"])

    def test_mismatched_frozen_immutable_evidence_detected(self):
        with sqlite3.connect(self.sidecar) as c:
            c.execute("""UPDATE v42_candidate_decisions
                        SET departure=departure+300 WHERE item_key=?""",
                      (m.MONKEY,))
        r=self.audit()
        self.assertIn("FROZEN_EVIDENCE_MISMATCH",
                      r["source_pinned_invalid_issues"][m.MONKEY])

    def test_monkey_wrong_selector_identity_fails_closed(self):
        with sqlite3.connect(self.sidecar) as c:
            for table in ("latest_predictions","v42_candidate_decisions"):
                c.execute(f"UPDATE {table} SET model_family=? WHERE item_key=?",
                          ("generic",m.MONKEY))
        r=self.audit()
        self.assertIn("MONKEY_WRONG_ORIGINAL_SELECTOR",
                      r["source_pinned_invalid_issues"][m.MONKEY])

    def test_missing_model_fails_exact_roster(self):
        with sqlite3.connect(self.sidecar) as c:
            for table in ("latest_predictions","v42_candidate_decisions"):
                c.execute(f"DELETE FROM {table} WHERE item_key=?",("uni:Heather",))
        r=self.audit()
        self.assertEqual(r["persisted_count"],19)
        self.assertIn("uni:Heather",r["missing_item_keys"])
        self.assertEqual(r["status"],"V71_FULL20_AS_ISSUED_REJECTED")

    def test_fake_player_departure_is_rejected(self):
        with sqlite3.connect(self.sidecar) as c:
            c.execute("UPDATE v42_candidate_decisions SET actual_player_departure=1 WHERE item_key=?",
                      (m.MONKEY,))
        r=self.audit()
        self.assertIn("FALSE_PLAYER_DEPARTURE",r["source_pinned_invalid_issues"][m.MONKEY])

    def test_arrival_travel_duration_incorrect_fails(self):
        with sqlite3.connect(self.sidecar) as c:
            for table in ("latest_predictions","v42_candidate_decisions"):
                c.execute(f"UPDATE {table} SET arrival=arrival+60 WHERE item_key=?",
                          ("cay:Banana Orchid",))
        r=self.audit()
        self.assertIn("ARRIVAL_TRAVEL_MISMATCH",
                      r["source_pinned_invalid_issues"]["cay:Banana Orchid"])

    def test_wrong_snapshot_heartbeat_fails(self):
        with sqlite3.connect(self.snapshot) as c:
            c.execute("UPDATE poll_heartbeats SET timestamp=?",(HEARTBEAT+1,))
        r=self.audit()
        self.assertFalse(r["verified_as_issued"])
        self.assertIn("NOT_FROM_FROZEN_SNAPSHOT",
                      r["source_pinned_invalid_issues"][m.MONKEY])

    def test_read_only_does_not_alter_history_or_ledger(self):
        with sqlite3.connect(self.sidecar) as c:
            before=c.execute("SELECT COUNT(*), MAX(computed_at) FROM latest_predictions").fetchone()
        r=self.audit()
        self.assertEqual(r["status"],m.SUCCESS)
        with sqlite3.connect(self.sidecar) as c:
            after=c.execute("SELECT COUNT(*), MAX(computed_at) FROM latest_predictions").fetchone()
        self.assertEqual(before,after)

    def test_missing_results_db_does_not_create_new_one(self):
        gone=self.snapshot.parent/"no-such.db"
        with self.assertRaises((OSError,ValueError)):
            m.audit(self.snapshot,gone,clock=lambda:NOW)
        self.assertFalse(gone.exists())


if __name__=="__main__":
    unittest.main()
