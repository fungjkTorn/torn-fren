"""V34 prospective scorer: mocked clock/SQLite, no hindsight, no writes."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research.v34_prospective_ops_audit import (
    audit,arrival_truth,_readonly,TRAVEL,GRACE,MAX_POLL_GAP
)

T=1791499200
COUNTRY="can"
ITEM="Bear Gall"
KEY="can:Bear Gall"
EXP="pilot-beargall-v33"
GEN=T+15
DEP=GEN+900
ARR=DEP+TRAVEL[COUNTRY]
V2DEP=GEN+1300
V2ARR=V2DEP+TRAVEL[COUNTRY]
ASOF=T+16*3600


def setup_stock(path):
    with sqlite3.connect(path) as c:
        c.executescript("""
        CREATE TABLE stock_history(
            id INTEGER PRIMARY KEY, country TEXT,item_name TEXT,
            timestamp INTEGER, quantity INTEGER);
        CREATE TABLE poll_heartbeats(
            timestamp INTEGER,mode TEXT,success INTEGER);
        CREATE TABLE collection_gaps(
            start_timestamp INTEGER,end_timestamp INTEGER);
        """)
        for arrival,qty in ((ARR,47),(V2ARR,0)):
            for ts in (arrival-25,arrival+25):
                c.execute("INSERT INTO stock_history(country,item_name,timestamp,quantity) "
                          "VALUES(?,?,?,?)",(COUNTRY,ITEM,ts,qty))
                c.execute("INSERT INTO poll_heartbeats VALUES(?,?,?)",
                          (ts,"poll-cycle",1))


def setup_evidence(path,*,status="RECORDED",executed=True,
                   challenger_departure=DEP, v2_departure=V2DEP,
                   generated=GEN):
    with sqlite3.connect(path) as c:
        c.executescript("""
        CREATE TABLE shadow_capture_attempts(
            id INTEGER PRIMARY KEY,experiment_id TEXT,item_key TEXT,
            tick_epoch INTEGER,attempted_at INTEGER,completed_at INTEGER,
            status TEXT,evidence_id INTEGER);
        CREATE TABLE shadow_decisions(
            id INTEGER PRIMARY KEY,experiment_id TEXT,item_key TEXT,
            tick_epoch INTEGER,recorded_at INTEGER,source_generated_at INTEGER,
            challenger_status TEXT,challenger_executed INTEGER,
            challenger_departure INTEGER,challenger_arrival INTEGER,
            v2_status TEXT,v2_departure INTEGER,v2_arrival INTEGER);
        """)
        c.execute("INSERT INTO shadow_capture_attempts VALUES (?,?,?,?,?,?,?,?)",
          (1,EXP,KEY,T,T+2,T+25,status,1 if status=="RECORDED" else None))
        if status=="RECORDED":
            c.execute("INSERT INTO shadow_decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (1,EXP,KEY,T,T+25,generated,
                 "RESEARCH_PROPOSAL_ONLY" if executed else "NO_RECOMMENDATION",
                 int(executed),challenger_departure if executed else None,
                 (challenger_departure+1620) if executed else None,
                 "available",v2_departure,(v2_departure+1620) if v2_departure else None))


class V34Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name)
        self.stock=base/"collector.db"
        self.ev=base/"research_shadow.db"
        setup_stock(self.stock)
        setup_evidence(self.ev)

    def report(self,scheduled=None,asof=ASOF):
        return audit(self.ev,self.stock,experiment=EXP,freeze_epoch=T,
                     asof_epoch=asof,scheduled_from_epoch=scheduled,
                     policy_max_wait=43200)["items"][KEY]

    def test_same_start_v21_success_and_v2_miss(self):
        r=self.report()
        self.assertEqual(r["valid_decisions"],1)
        self.assertEqual(r["matured_attempts_or_missing_ticks"],1)
        self.assertEqual(r["v21"]["confirmed_success"],1)
        self.assertEqual(r["v21"]["conservative_success_lower_bound"],1)
        self.assertEqual(r["v2"]["confirmed_success"],0)
        self.assertEqual(r["v2"]["recorded_arrival_rate"],0)
        self.assertFalse(r["independent_window_certified"])

    def test_an_unmatured_forecast_is_not_scored(self):
        report=self.report(asof=T+10*3600)
        self.assertEqual(report["pending_attempts"],1)
        self.assertEqual(report["matured_attempts_or_missing_ticks"],0)
        self.assertIsNone(report["v21"]["conservative_success_lower_bound"])

    def test_failed_capture_stays_in_denominator(self):
        with sqlite3.connect(self.ev) as c:
            c.execute("UPDATE shadow_capture_attempts SET status='PRIVATE_FAILURE_TIMEOUT',"
                      "evidence_id=NULL WHERE id=1")
            c.execute("DELETE FROM shadow_decisions")
        r=self.report()
        self.assertEqual(r["matured_attempts_or_missing_ticks"],1)
        self.assertEqual(r["v21"]["confirmed_success"],0)
        self.assertEqual(r["v2"]["confirmed_success"],0)
        self.assertIn("PRIVATE_FAILURE_TIMEOUT",r["status_counts"])

    def test_missing_timer_slots_count_against_operational_lower_bound(self):
        # Every scheduled :01/:06/... tick from the supplied start is expected.
        scheduled=T+360  # :46 UTC, 60 sec after the :45 tick
        r=self.report(scheduled=scheduled)
        self.assertGreater(r["missing_timer_ticks"],1)
        self.assertEqual(r["matured_attempts_or_missing_ticks"],
                         1+sum(1 for t in range(scheduled,ASOF-179,300)
                               if t//300*300+43200+1620+10+180<=ASOF))
        self.assertLess(r["v21"]["conservative_success_lower_bound"],1)

    def test_rotating_four_item_schedule_penalizes_only_its_20min_slots(self):
        anchor=T+360   # expected :01/:06/... minute of first eligible 4-slot rotation
        once=audit(self.ev,self.stock,experiment=EXP,
             freeze_epoch=T,asof_epoch=ASOF,scheduled_from_epoch=anchor,
             policy_max_wait=43200,items=[KEY],schedule_stride_seconds=1200)
        every=audit(self.ev,self.stock,experiment=EXP,
             freeze_epoch=T,asof_epoch=ASOF,scheduled_from_epoch=anchor,
             policy_max_wait=43200,items=[KEY],schedule_stride_seconds=300)
        self.assertEqual(once["schedule_stride_seconds"],1200)
        a=once["items"][KEY]
        b=every["items"][KEY]
        self.assertGreater(b["missing_timer_ticks"],a["missing_timer_ticks"])
        self.assertLess(a["matured_attempts_or_missing_ticks"],
                        b["matured_attempts_or_missing_ticks"])

    def test_stock_gap_cannot_be_credited_as_success(self):
        with sqlite3.connect(self.stock) as c:
            c.execute("INSERT INTO collection_gaps VALUES (?,?)",(ARR-40,ARR+40))
        r=self.report()
        self.assertEqual(r["v21"]["confirmed_success"],0)
        self.assertEqual(r["v21"]["unknown_outcomes"],1)
        self.assertEqual(r["v21"]["conservative_success_lower_bound"],0)

    def test_ambiguous_high_to_low_transition_is_not_invented(self):
        with sqlite3.connect(self.stock) as c:
            c.execute("UPDATE stock_history SET quantity=0 WHERE timestamp=?",(ARR+25,))
        r=self.report()
        self.assertEqual(r["v21"]["confirmed_success"],0)
        self.assertEqual(r["v21"]["unknown_outcomes"],1)

    def test_no_recommendation_is_zero_coverage(self):
        with sqlite3.connect(self.ev) as c:
            c.execute("UPDATE shadow_decisions SET challenger_status='NO_RECOMMENDATION',"
                      "challenger_executed=0,challenger_departure=NULL,"
                      "challenger_arrival=NULL")
        r=self.report()
        self.assertEqual(r["v21"]["confirmed_success"],0)
        self.assertEqual(r["v21"]["actionable_coverage"],0)
        self.assertEqual(r["v21"]["unknown_outcomes"],0)

    def test_expired_v2_departure_cannot_count_as_success(self):
        with sqlite3.connect(self.ev) as c:
            c.execute("UPDATE shadow_decisions SET v2_departure=?,v2_arrival=?",
                      (T-100,T-100+1620))
        r=self.report()
        self.assertEqual(r["v2"]["actionable_coverage"],0)
        self.assertEqual(r["v2"]["confirmed_success"],0)

    def test_scoring_is_read_only_and_does_not_promote(self):
        before_e=self.ev.read_bytes()
        before_s=self.stock.read_bytes()
        report=audit(self.ev,self.stock,experiment=EXP,freeze_epoch=T,
                     asof_epoch=ASOF,scheduled_from_epoch=None)
        self.assertEqual(self.ev.read_bytes(),before_e)
        self.assertEqual(self.stock.read_bytes(),before_s)
        self.assertEqual(report["promotions_approved"],0)
        self.assertFalse(report["independent_window_certified"])

    def test_invalid_timer_anchor_fails_closed(self):
        with self.assertRaises(ValueError):
            self.report(scheduled=T+20)
        with self.assertRaises(ValueError):
            audit(self.ev,self.ev,experiment=EXP,freeze_epoch=T,
                  asof_epoch=ASOF,scheduled_from_epoch=None)

    def test_asof_does_not_look_ahead_to_future_stock(self):
        # Remove close post-bracket sample, move it past audit timestamp.
        with sqlite3.connect(self.stock) as c:
            c.execute("UPDATE stock_history SET timestamp=? WHERE timestamp=?",
                      (ASOF+20,ARR+25))
        r=self.report()
        self.assertEqual(r["v21"]["confirmed_success"],0)
        self.assertEqual(r["v21"]["unknown_outcomes"],1)

if __name__=="__main__":unittest.main()
