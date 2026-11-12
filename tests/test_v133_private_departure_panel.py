"""V133 explicit provisional time-to-leave display model, not the website."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research import v133_private_departure_panel as m
from research import v128_full24_earliest_shadow as v128

ISSUE=1790000000


def row(key,issue=ISSUE,delay=1200):
    country=key.split(":",1)[0]
    flight=v128.TRAVEL_SECONDS[country]
    dep=None if delay is None else issue+delay
    return {
        "item_key":key,
        "issued_epoch":issue,
        "policy_id":v128.GENERATION,
        "travel_seconds":flight,
        "min_stock_at_arrival":30,
        "research_only":True,
        "published_to_website":False,
        "earliest_departure":dep,
        "earliest_arrival":None if dep is None else dep+flight,
        "departure_state":"ABSTAIN" if dep is None else (
            "RESEARCH_NOW" if delay==0 else
            "RESEARCH_READY_WITHIN_5M" if delay<=300 else
            "RESEARCH_FUTURE_WATCH_UNCONFIRMED"),
        "baseline_leave_now_arrival":issue+flight,
        "last_stock_quantity":75,
        "phase":"HIGH","earliest_score":0.65625,
        "wait_minutes":None if dep is None else delay/60,
    }


class DepartureDisplayContract(unittest.TestCase):
    def test_near_term_not_certified_go(self):
        r=m.display_record(row("uni:Nessie Plushie",delay=300),
                           now=ISSUE+30)
        self.assertEqual(r["display_status"],"RESEARCH_NEAR_TERM_NOT_CERTIFIED")
        self.assertFalse(r["live_country_stock_freshness_verified"])
        self.assertFalse(r["actual_arrival_stock_verified"])
        self.assertTrue(r["display_never_issues_gameplay_instruction"])
        self.assertIsNone(r["next_restock_estimate_epoch"])
        self.assertIsNone(r["estimated_stock_depletion_epoch"])

    def test_long_watch_requires_new_issued_forecast(self):
        r=m.display_record(row("can:Xanax",delay=1200),now=ISSUE+60)
        self.assertEqual(r["display_status"],
                         "RESEARCH_FUTURE_WATCH_RECHECK_REQUIRED")
        self.assertEqual(r["seconds_until_proposed_departure"],1140)
        self.assertEqual(r["current_flight_seconds"],v128.TRAVEL_SECONDS["can"])

    def test_expiry_and_passed_do_not_repeat_stale_departures(self):
        expired=m.display_record(row("uni:Nessie Plushie",delay=1200),
                                 now=ISSUE+301)
        self.assertEqual(expired["display_status"],"RESEARCH_SNAPSHOT_EXPIRED")
        self.assertIsNone(expired["proposed_departure_epoch"])
        passed=m.display_record(row("uni:Nessie Plushie",delay=0),
                                now=ISSUE+1)
        self.assertEqual(passed["display_status"],
                         "PROPOSED_DEPARTURE_ALREADY_PASSED")
        self.assertIsNone(passed["proposed_departure_epoch"])
        future=m.display_record(row("uni:Nessie Plushie",issue=ISSUE+100,delay=0),
                                now=ISSUE)
        self.assertEqual(future["display_status"],"FUTURE_ISSUANCE_REJECTED")

    def test_unsupported_departure_never_misreported(self):
        abstain=m.display_record(row("uni:Nessie Plushie",delay=None),
                                 now=ISSUE)
        self.assertEqual(abstain["display_status"],
                         "NO_QUALIFYING_RESEARCH_DEPARTURE")
        self.assertIsNone(abstain["proposed_departure_epoch"])

    def test_exact24_batch_no_partial_public_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            side=Path(tmp)/"private.db"
            with sqlite3.connect(side) as c:
                c.execute("""CREATE TABLE v128_ticks(
                    issued_epoch INTEGER,captured_epoch INTEGER,
                    source_heartbeat INTEGER,roster_size INTEGER,
                    policy_id TEXT)""")
                c.execute("""CREATE TABLE v128_issued(
                    item_key TEXT,issued_epoch INTEGER,
                    policy_id TEXT,payload_json TEXT)""")
                c.execute("INSERT INTO v128_ticks VALUES (?,?,?,?,?)",
                    (ISSUE,ISSUE+5,ISSUE-10,24,v128.GENERATION))
                for key in v128.exact_roster():
                    x=row(key,delay=None if key=="uni:Nessie Plushie" else 1200)
                    c.execute("INSERT INTO v128_issued VALUES(?,?,?,?)",
                        (key,ISSUE,v128.GENERATION,json.dumps(x)))
                c.commit()
            preview=m.preview(sidecar=side,now=ISSUE+60)
            self.assertEqual(preview["status"],
                "V133_SAFE_RESEARCH_24_ITEM_DEPARTURE_PANEL_DATA")
            self.assertEqual(preview["roster_size"],24)
            self.assertEqual(len(preview["items"]),24)
            self.assertEqual(
                preview["display_status_counts"][
                    "RESEARCH_FUTURE_WATCH_RECHECK_REQUIRED"],23)
            self.assertEqual(
                preview["display_status_counts"][
                    "NO_QUALIFYING_RESEARCH_DEPARTURE"],1)
            self.assertTrue(preview["original_website_prediction_v2_untouched"])
            with sqlite3.connect(side) as c:
                c.execute("DELETE FROM v128_issued WHERE item_key=?",
                          ("uni:Nessie Plushie",))
                c.commit()
            withheld=m.preview(sidecar=side,now=ISSUE+60)
            self.assertEqual(withheld["status"],
                "INCOMPLETE_OR_INVALID_24_ITEM_ISSUE_BATCH")
            self.assertFalse(withheld["items"])


if __name__=="__main__":
    unittest.main()
