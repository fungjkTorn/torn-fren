"""V66 original Monkey resolved-bank readiness with entirely read-only inputs."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import v66_monkey_readonly_selector_probe as v66
from research.v47_online_expert_cache import CACHE_TABLE, STATE_TABLE, gap_fingerprint
from research.v45_online_template_probe import EXPERTS
from research.plushie_champions.common import DAY

NOW=1791650000
ANCHOR=NOW-40000
KEY="arg:Monkey Plushie"


class Planner:
    def __init__(self,*args,**kwargs):
        pass
    def plan(self,q):
        return q+600,0.7,{"fit":0.9,"maxfit":0.95,"refs":2.0}


class DifferentPlanner(Planner):
    def plan(self,q):
        return q+900,0.7,{"fit":0.9,"maxfit":0.95,"refs":2.0}


class AlreadyDepartedPlanner(Planner):
    def plan(self,q):
        return q,0.7,{"fit":0.9,"maxfit":0.95,"refs":2.0}


class MonkeySelectorReadOnlyTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.source=self.root/"mirror.db"
        self.cache=self.root/"cache.db"
        with sqlite3.connect(self.source) as s:
            s.execute("""CREATE TABLE stock_history(
             id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,
             item_name TEXT,quantity INTEGER,source TEXT)""")
            s.execute("""CREATE TABLE poll_heartbeats(
             timestamp INTEGER,mode TEXT,success INTEGER)""")
            s.execute("""CREATE TABLE collection_gaps(
             id INTEGER PRIMARY KEY,start_timestamp INTEGER,end_timestamp INTEGER)""")
            s.execute("INSERT INTO stock_history VALUES(1,?,?,?,?,?)",
                      (NOW-9*DAY,"arg","Monkey Plushie",50,"test"))
            s.execute("INSERT INTO stock_history VALUES(2,?,?,?,?,?)",
                      (NOW-10000,"arg","Monkey Plushie",0,"test"))
            s.execute("INSERT INTO poll_heartbeats VALUES(?,'poll-cycle',1)",
                      (NOW-10,))
        with sqlite3.connect(self.cache) as c:
            c.execute(CACHE_TABLE)
            c.execute(STATE_TABLE)
            c.execute("INSERT INTO expert_source_state VALUES(?,?,?)",
                      (KEY,gap_fingerprint([],[]),2))
            for e in range(len(EXPERTS)):
                c.execute("""INSERT INTO expert_resolutions VALUES(
                    ?,?,?,'RESOLVED_EXPERT_DECISION',?,?,?,?)""",
                    (KEY,ANCHOR,e,1 if e%2==0 else 0,
                     NOW-120,ANCHOR+300,ANCHOR+6960))

    def probe(self,**kwargs):
        with patch.object(v66,"eligible_starts",return_value=[ANCHOR]):
            return v66.audit(self.source,self.cache,clock=lambda:NOW,
                fast_planner=Planner,original_planner=Planner,**kwargs)

    def test_complete_bank_exact_winner_readonly_and_original_parity(self):
        before_source=self.source.read_bytes()
        before_cache=self.cache.read_bytes()
        out=self.probe()
        self.assertEqual(out["status"],"V66_MONKEY_SELECTOR_VALIDATED")
        self.assertEqual(out["required_decisions"],24)
        self.assertEqual(out["cached_decisions"],24)
        self.assertEqual(out["missing_decisions"],0)
        self.assertEqual(out["required_anchors"],1)
        self.assertTrue(out["source_parity_one_slot"])
        self.assertEqual(out["chosen_expert_index"],0)
        self.assertEqual(out["heartbeat_age_seconds"],10)
        self.assertFalse(out["live_admission"])
        self.assertFalse(out["v48_cache_written"])
        self.assertEqual(self.source.read_bytes(),before_source)
        self.assertEqual(self.cache.read_bytes(),before_cache)

    def test_missing_one_of_24_abstains(self):
        with sqlite3.connect(self.cache) as c:
            c.execute("DELETE FROM expert_resolutions WHERE item_key=? AND expert_id=23",(KEY,))
        r=self.probe()
        self.assertEqual(r["status"],"V66_CACHE_NOT_READY")
        self.assertEqual(r["missing_decisions"],1)

    def test_stale_mirror_fails_before_reading_cache(self):
        with sqlite3.connect(self.source) as c:
            c.execute("UPDATE poll_heartbeats SET timestamp=?",(NOW-224,))
        r=self.probe()
        self.assertEqual(r["status"],"V66_STALE_SNAPSHOT")
        self.assertEqual(r["heartbeat_age_seconds"],224)

    def test_revision_fingerprint_fails_closed(self):
        with sqlite3.connect(self.cache) as c:
            c.execute("UPDATE expert_source_state SET gap_fingerprint='invalid' WHERE item_key=?",(KEY,))
        r=self.probe()
        self.assertEqual(r["status"],"V66_CACHE_GAP_REVISION_INVALID")

    def test_later_historical_target_row_invalidates_cached_evidence(self):
        with sqlite3.connect(self.source) as c:
            c.execute("INSERT INTO stock_history VALUES(3,?,?,?,?,?)",
                      (NOW-180,"arg","Monkey Plushie",50,"backdated"))
        r=self.probe()
        self.assertEqual(r["status"],"V66_BACKDATED_TARGET_REQUIRES_REFRESH")

    def test_new_unrelated_item_does_not_invalidate_monkey(self):
        with sqlite3.connect(self.source) as c:
            c.execute("INSERT INTO stock_history VALUES(3,?,?,?,?,?)",
                      (NOW-180,"jap","Xanax",40,"independent"))
        r=self.probe()
        self.assertEqual(r["status"],"V66_MONKEY_SELECTOR_VALIDATED")

    def test_observed_target_row_after_rounded_slot_is_not_future_data(self):
        # The checker runs at 5-minute FLOOR(now), whereas the snapshot
        # legitimately includes collector observations made after that slot.
        # A later valid row must not block the original bank/parity check.
        q=(NOW//v66.STEP)*v66.STEP
        row_ts=NOW-75
        self.assertGreater(row_ts,q)
        self.assertLess(row_ts,NOW-10)  # no observations after heartbeat
        with sqlite3.connect(self.source) as source:
            source.execute("INSERT INTO stock_history VALUES(3,?,?,?,?,?)",
                           (row_ts,"arg","Monkey Plushie",45,"observed"))
        result=self.probe()
        self.assertEqual(result["status"],"V66_MONKEY_SELECTOR_VALIDATED")
        self.assertTrue(result["source_parity_one_slot"])
        self.assertEqual(result["missing_decisions"],0)

    def test_stock_row_after_verified_heartbeat_still_abstains(self):
        # Do not confuse accepting post-5m-slot observations with allowing
        # observations beyond the last verified collector heartbeat.
        with sqlite3.connect(self.source) as source:
            source.execute("INSERT INTO stock_history VALUES(3,?,?,?,?,?)",
                           (NOW-5,"arg","Monkey Plushie",45,"unverified"))
        result=self.probe()
        self.assertEqual(result["status"],"V66_SOURCE_AFTER_VERIFIED_HEARTBEAT")

    def test_future_resolution_refused_as_invalid_evidence(self):
        with sqlite3.connect(self.cache) as c:
            c.execute("""UPDATE expert_resolutions SET resolved_at=?
                      WHERE item_key=? AND expert_id=0""",(NOW+1,KEY))
        r=self.probe()
        self.assertEqual(r["status"],"V66_CACHE_NOT_READY")
        self.assertEqual(r["invalid_rows"],1)

    def test_parity_mismatch_blocks_admission(self):
        with patch.object(v66,"eligible_starts",return_value=[ANCHOR]):
            r=v66.audit(self.source,self.cache,clock=lambda:NOW,
                        fast_planner=Planner,original_planner=DifferentPlanner)
        self.assertEqual(r["status"],"V66_ORIGINAL_PARITY_MISMATCH")
        self.assertFalse(r["source_parity_one_slot"])

    def test_candidate_departure_already_passed_is_not_actionable(self):
        with patch.object(v66,"eligible_starts",return_value=[ANCHOR]):
            result=v66.audit(self.source,self.cache,clock=lambda:NOW,
                 fast_planner=AlreadyDepartedPlanner,
                 original_planner=AlreadyDepartedPlanner)
        self.assertEqual(result["status"],"V66_DEPARTURE_OUT_OF_BOUNDS")
        self.assertTrue(result["source_parity_one_slot"])

    def test_missing_no_schedule_is_not_inferred_as_failure(self):
        with sqlite3.connect(self.cache) as c:
            c.execute("""UPDATE expert_resolutions
                      SET status='NO_RESOLVED_EXPERT_DECISION',
                          success=NULL,resolved_at=NULL,departure=NULL,
                          arrival=NULL WHERE item_key=? AND expert_id=0""",(KEY,))
        r=self.probe()
        self.assertEqual(r["status"],"V66_MONKEY_SELECTOR_VALIDATED")
        self.assertEqual(r["cached_decisions"],24)

    def test_cache_and_source_must_be_distinct(self):
        with self.assertRaises(ValueError):
            v66.audit(self.source,self.source,clock=lambda:NOW)

    def test_no_readonly_cache_data_fabrication(self):
        with sqlite3.connect(self.cache) as c:
            c.execute("""UPDATE expert_resolutions
                      SET status='INVENTED',success=1
                      WHERE item_key=? AND expert_id=0""",(KEY,))
        r=self.probe()
        self.assertEqual(r["status"],"V66_CACHE_NOT_READY")


if __name__=="__main__":
    unittest.main()
