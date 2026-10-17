"""V117: prove future watches cannot be scored as executable flights."""
import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import v117_first_executable_replan_audit as m

T0=1700000000
ITEM="uni:Red Fox Plushie"


class FiveMinuteReplanTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger=Path(self.temp.name)/"sidecar.sqlite"
        self.stock=Path(self.temp.name)/"stock.sqlite"
        self.now=T0+10000
        self.issue=T0+600
        with sqlite3.connect(self.ledger) as db:
            db.execute("""CREATE TABLE v42_candidate_decisions (
                id INTEGER PRIMARY KEY,item_key TEXT,
                computed_at INTEGER,model_family TEXT,model_config TEXT,
                stock_as_of INTEGER,status TEXT,
                departure INTEGER,arrival INTEGER,valid_until INTEGER,
                actual_player_departure INTEGER
            )""")
            db.commit()
        with sqlite3.connect(self.stock) as db:
            db.execute("""CREATE TABLE stock_history (
                id INTEGER PRIMARY KEY,timestamp INTEGER,
                country TEXT,item_name TEXT,quantity INTEGER,source TEXT
            )""")
            db.execute("""CREATE TABLE poll_heartbeats (
                id INTEGER PRIMARY KEY,timestamp INTEGER,
                source TEXT,mode TEXT,success INTEGER
            )""")
            db.execute("""CREATE TABLE collection_gaps (
                start_timestamp INTEGER,end_timestamp INTEGER
            )""")
            for item in ("Red Fox Plushie","Nessie Plushie"):
                db.execute("""INSERT INTO stock_history
                    (timestamp,country,item_name,quantity,source)
                    VALUES (?,?,?,?,?)""",
                    (self.issue-100,"uni",item,300,"yata"))
            for t in (
                self.issue+6360-30,self.issue+6360+40,
                self.issue+7800-30,self.issue+7800+40,
                self.issue+7200-30,self.issue+7200+40,
            ):
                db.execute("""INSERT INTO poll_heartbeats
                    (timestamp,source,mode,success)
                    VALUES (?,'yata','poll-cycle',1)""",(t,))
            db.commit()

    def add(self,when,depart,*,item=ITEM,family="global_regime_analog",
            status="RESEARCH_PROPOSAL_ONLY"):
        with sqlite3.connect(self.ledger) as db:
            db.execute("""INSERT INTO v42_candidate_decisions
                (item_key,computed_at,model_family,model_config,
                 stock_as_of,status,departure,arrival,valid_until,
                 actual_player_departure)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (item,when,family,"test",when,status,depart,
                 depart+6360 if depart is not None else None,
                 when+300,0))
            db.commit()

    def test_delayed_watch_requires_new_executable_issue(self):
        self.add(self.issue,self.issue+7200)
        self.add(self.issue+300,self.issue+1800)
        self.add(self.issue+600,self.issue+840)
        self.add(self.issue+900,self.issue+900)
        with sqlite3.connect(self.ledger) as db:
            db.row_factory=sqlite3.Row
            timeline,times,n=m.future_candidate_timelines(
                db,start=self.issue,end=self.now,keys=(ITEM,))
            chosen=m.first_actionable_tick(
                timeline[ITEM][0],timeline[ITEM],times[ITEM],now=self.now)
        self.assertEqual(chosen["status"],"EXECUTABLE_WITHIN_5M")
        self.assertEqual(chosen["ready_issue"],self.issue+600)
        self.assertEqual(chosen["departure"],self.issue+840)
        self.assertEqual(chosen["ticks_inspected"],3)
        self.assertEqual(chosen["rejected_tick_reasons"][
            "FUTURE_WATCH_NOT_YET_EXECUTABLE"],2)

    def test_maturing_horizon_can_not_claim_no_action(self):
        self.add(self.issue,self.issue+7200)
        with sqlite3.connect(self.ledger) as db:
            db.row_factory=sqlite3.Row
            timeline,times,n=m.future_candidate_timelines(
                db,start=self.issue,end=self.now,keys=(ITEM,))
            waiting=m.first_actionable_tick(
                timeline[ITEM][0],timeline[ITEM],times[ITEM],
                now=self.issue+500)
            no_action=m.first_actionable_tick(
                timeline[ITEM][0],timeline[ITEM],times[ITEM],
                now=self.issue+28800)
        self.assertEqual(waiting["status"],"STILL_WAITING_HORIZON_NOT_MATURE")
        self.assertEqual(no_action["status"],
                         "NO_EXECUTABLE_DEPARTURE_WITHIN_8H")
        self.assertIsNone(waiting["arrival"])

    def test_same_hour_start_frozen_and_first_ready_are_distinct(self):
        self.add(self.issue,self.issue+7200)
        self.add(self.issue+300,self.issue+1800)
        self.add(self.issue+600,self.issue+840)
        # Test end-to-end SQL validity+no lookahead and snapshot readiness.
        result=m.audit(
            ledger=self.ledger,stock=self.stock,
            now=self.now,hours=5,keys=(ITEM,))
        self.assertEqual(result["first_per_item_UTC_hour_start_cohort"],1)
        self.assertEqual(result["overall"]["EXECUTABLE_WITHIN_5M"],1)
        self.assertEqual(result["overall"]["ready_departure_issued"],1)
        self.assertEqual(result["overall"]["paired_scorable"],1)
        self.assertEqual(result["overall"]["both_hit"],1)
        self.assertEqual(result["overall"]["immediate_arrival_matured"],1)
        self.assertTrue(result["departure_scheduled_without_future_stock_outcome"])
        self.assertFalse(result["country_specific_provider_age_verified"])

    def test_abstained_ticks_are_not_actions(self):
        self.add(self.issue,self.issue+7200)
        self.add(self.issue+300,None,status="NO_RECOMMENDATION")
        self.add(self.issue+600,self.issue+780)
        with sqlite3.connect(self.ledger) as db:
            db.row_factory=sqlite3.Row
            tl,ts,_=m.future_candidate_timelines(
                db,start=self.issue,end=self.now,keys=(ITEM,))
            r=m.first_actionable_tick(tl[ITEM][0],tl[ITEM],ts[ITEM],
                                      now=self.now)
        self.assertEqual(r["ready_issue"],self.issue+600)
        self.assertEqual(r["ticks_inspected"],3)
        self.assertEqual(r["rejected_tick_reasons"][
            "INVALID_OR_ABSTAINED"],1)

    def test_complete_cli_json_and_text(self):
        self.add(self.issue,self.issue+7200)
        self.add(self.issue+600,self.issue+840)
        original=m.audit
        def fixture(**kwargs):
            return original(ledger=self.ledger,stock=self.stock,
                            now=self.now,**kwargs)
        with (patch.object(m,"audit",side_effect=fixture),
              patch.object(m,"approved_collector_source",return_value=True)):
            for as_json in (True,False):
                argv=["v117","--hours","5","--items","redfox"]
                if as_json:argv.append("--json")
                text=io.StringIO()
                with (patch.object(sys,"argv",argv),
                      contextlib.redirect_stdout(text)):
                    m.main()
                if as_json:
                    r=json.loads(text.getvalue())
                    self.assertEqual(r["status"],
                        "V117_FROZEN_FIVE_MINUTE_REPLAN_FIRST_ACTIONABLE_AUDIT")
                    self.assertEqual(r["overall"]["ready_departure_issued"],1)
                else:
                    self.assertIn("FIRST EXECUTABLE DEPARTURE",text.getvalue())


if __name__=="__main__":
    unittest.main()
