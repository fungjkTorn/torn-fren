"""V116: family attribution; avoid treating 5m replans as independent."""
import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import v116_attributed_hourly_forward_audit as m


class FirstHourlyFamilyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger=Path(self.temp.name)/"private.sqlite"
        self.stock=Path(self.temp.name)/"stock.sqlite"
        self.now=1700012000
        base=self.now-4*3600
        self.issued=base
        self.arrival=base+6360
        with sqlite3.connect(self.ledger) as con:
            con.execute("""CREATE TABLE v42_candidate_decisions (
                id INTEGER PRIMARY KEY,
                item_key TEXT,
                computed_at INTEGER,
                model_family TEXT,
                model_config TEXT,
                stock_as_of INTEGER,
                status TEXT,
                departure INTEGER,
                arrival INTEGER,
                valid_until INTEGER,
                actual_player_departure INTEGER
            )""")
            rows=[
                (m.ITEMS["redfox"],base,"redfox_specialist","{}",
                 base,"RESEARCH_PROPOSAL_ONLY",base,self.arrival,base+300,0),
                (m.ITEMS["redfox"],base+300,"redfox_specialist","{}",
                 base+300,"RESEARCH_PROPOSAL_ONLY",base+300,
                 self.arrival+300,base+600,0),
                (m.ITEMS["redfox"],base+600,"redfox_specialist","{}",
                 base+600,"RESEARCH_PROPOSAL_ONLY",base+600,
                 self.arrival+600,base+900,0),
                (m.ITEMS["nessie"],base,"nessie_challenger","{}",
                 base,"RESEARCH_PROPOSAL_ONLY",base+600,
                 self.arrival+600,base+300,0),
                (m.ITEMS["nessie"],base+300,"nessie_challenger","{}",
                 base+300,"RESEARCH_PROPOSAL_ONLY",base+300,
                 self.arrival+300,base+600,0),
            ]
            con.executemany("""INSERT INTO v42_candidate_decisions
                (item_key,computed_at,model_family,model_config,stock_as_of,
                 status,departure,arrival,valid_until,actual_player_departure)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",rows)
            con.commit()
        with sqlite3.connect(self.stock) as con:
            con.execute("""CREATE TABLE stock_history (
                id INTEGER PRIMARY KEY,timestamp INTEGER,
                quantity INTEGER,country TEXT,item_name TEXT,source TEXT
            )""")
            con.execute("""CREATE TABLE collection_gaps (
                start_timestamp INTEGER,end_timestamp INTEGER
            )""")
            con.execute("""CREATE TABLE poll_heartbeats (
                id INTEGER PRIMARY KEY,timestamp INTEGER,
                source TEXT,mode TEXT,success INTEGER
            )""")
            for item in ("Red Fox Plushie","Nessie Plushie"):
                con.execute("""INSERT INTO stock_history
                    (timestamp,quantity,country,item_name,source)
                    VALUES (?,?,?,?,?)""",
                    (base+4500,100,"uni",item,"yata"))
            for arrival in (base+6360,base+6960):
                for timestamp in (arrival-30,arrival+40):
                    con.execute("""INSERT INTO poll_heartbeats
                        (timestamp,source,mode,success)
                        VALUES (?,'yata','poll-cycle',1)""",(timestamp,))
            con.commit()

    def test_attribution_and_first_hour_rep_before_outcome(self):
        result=m.audit(ledger=self.ledger,stock=self.stock,now=self.now,hours=6)
        self.assertEqual(result["unique_item_arrival_targets"],5)
        self.assertEqual(result["first_per_item_UTC_hour"],2)
        self.assertEqual(result["unique_arrival_targets_by_family"],{
            "nessie_challenger":2,"redfox_specialist":3,
        })
        scoped=result["hourly_representative_matched_poll_proxy"]
        self.assertEqual(scoped["all"]["issued"],2)
        self.assertEqual(scoped["all"]["both_scorable"],2)
        self.assertEqual(scoped["all"]["both_hit"],2)
        self.assertIn("redfox_specialist",scoped["per_family"])
        self.assertIn("nessie_challenger",scoped["per_family"])
        self.assertEqual(scoped["per_departure_lead"]["immediate"]["issued"],1)
        self.assertEqual(scoped["per_departure_lead"][
            "delay_5_to_15m"]["issued"],1)
        self.assertFalse(result["actual_gameplay_success_verified"])

    def test_first_per_hour_does_not_choose_winning_forecasts(self):
        with sqlite3.connect(self.ledger) as conn:
            conn.row_factory=sqlite3.Row
            rows,raw,bad=m.select_candidates(
                conn,start=self.issued-1,end=self.now,
                keys=tuple(m.ITEMS.values()))
        selected=m.first_per_item_hour(rows)
        self.assertEqual(len(selected),2)
        self.assertEqual(
            {x["item_key"]:x["computed_at"] for x in selected},
            {m.ITEMS["redfox"]:self.issued,
             m.ITEMS["nessie"]:self.issued})
        self.assertEqual(raw,5)
        self.assertEqual(bad,{})

    def test_model_family_is_attributed_only_to_scored_target(self):
        with sqlite3.connect(self.ledger) as con:
            con.execute("""INSERT INTO v42_candidate_decisions
                (item_key,computed_at,model_family,model_config,stock_as_of,
                 status,departure,arrival,valid_until,actual_player_departure)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (m.ITEMS["redfox"],self.issued,
                 "unapproved_candidate","{}",self.issued,
                 "NON_ACTIONABLE",None,None,self.issued+300,0))
            con.commit()
        result=m.audit(ledger=self.ledger,stock=self.stock,now=self.now,hours=6)
        self.assertEqual(result["unique_item_arrival_targets"],5)
        self.assertEqual(result["invalid_or_abstained_rows"],{
            "INVALID_OR_ABSTAINED":1})
        self.assertNotIn("unapproved_candidate",
                         result["unique_arrival_targets_by_family"])

    def test_invalid_targets_and_cap_fail_closed(self):
        with sqlite3.connect(self.ledger) as conn:
            conn.row_factory=sqlite3.Row
            with self.assertRaisesRegex(ValueError,"more than 1200 target arrivals"):
                pass
            # A deliberately lower limit cannot silently drop a valid item.
            with self.assertRaisesRegex(ValueError,"more than 1200"):
                m.select_candidates(
                    conn,start=self.issued-1,end=self.now,
                    keys=tuple(m.ITEMS.values()),limit=1)
        with self.assertRaises(ValueError):
            m.audit(ledger=self.ledger,stock=self.stock,now=self.now,hours=25)
        with self.assertRaises(ValueError):
            m.audit(ledger=self.ledger,stock=self.stock,now=self.now,
                    keys=("uni:nonexistent",))

    def test_complete_main_for_both_output_styles(self):
        original=m.audit
        def fixture(**kwargs):
            return original(ledger=self.ledger,stock=self.stock,
                            now=self.now,**kwargs)
        with (patch.object(m,"audit",side_effect=fixture),
              patch("research.v88_poll_state_forward_report.SOURCE",
                    self.stock),
              patch.object(m,"approved_collector_source",return_value=True)):
            for as_json in (True,False):
                argv=["v116","--hours","6"]
                if as_json:argv.append("--json")
                buffer=io.StringIO()
                with (patch.object(sys,"argv",argv),
                      contextlib.redirect_stdout(buffer)):
                    m.main()
                if as_json:
                    x=json.loads(buffer.getvalue())
                    self.assertEqual(x["status"],
                        "V116_FIRST_PER_ITEM_UTC_HOUR_FAMILY_ATTRIBUTED_FORWARD_AUDIT")
                    self.assertEqual(x["first_per_item_UTC_hour"],2)
                else:
                    self.assertIn("V116 ATTRIBUTED V75 FORWARD",
                                  buffer.getvalue())


if __name__=="__main__":
    unittest.main()
