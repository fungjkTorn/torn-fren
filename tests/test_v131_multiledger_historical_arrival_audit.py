"""V131 read-only existing V75 first-issued-hour stocks and V128 separation."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import v131_multiledger_historical_arrival_audit as m
from research import v128_full24_earliest_shadow as v128

T0=(1790000000//3600)*3600
KEY="uni:Nessie Plushie"
FLIGHT=m.TRAVEL_SECONDS["uni"]


def case(issue,status,wait=0):
    dep=None if status!="RESEARCH_PROPOSAL_ONLY" else issue+wait
    return (
        KEY,issue,issue-15,status,issue+300,
        dep,None if dep is None else dep+FLIGHT,0,
        "recent_phase_template",None
    )


def ledger_at(p,rows):
    with sqlite3.connect(p) as c:
        c.execute("""CREATE TABLE v42_candidate_decisions(
            id INTEGER PRIMARY KEY,
            item_key TEXT NOT NULL,
            computed_at INTEGER NOT NULL,
            stock_as_of INTEGER,
            status TEXT NOT NULL,
            valid_until INTEGER,
            departure INTEGER,
            arrival INTEGER,
            actual_player_departure INTEGER,
            model_family TEXT,
            model_config TEXT
        )""")
        c.executemany("""INSERT INTO v42_candidate_decisions(
            item_key,computed_at,stock_as_of,status,valid_until,
            departure,arrival,actual_player_departure,model_family,model_config
        ) VALUES (?,?,?,?,?,?,?,?,?,?)""",rows)
        c.commit()


class MultiledgerAuditTests(unittest.TestCase):
    def test_first_hour_first_issued_must_not_switch_on_outcome(self):
        with tempfile.TemporaryDirectory() as temp:
            old=Path(temp)/"old.db"
            stock=Path(temp)/"stock.db"
            ledger_at(old,[
                case(T0,"RESEARCH_PROPOSAL_ONLY",wait=600),
                case(T0+300,"RESEARCH_PROPOSAL_ONLY",wait=0),
                case(T0+600,"RESEARCH_PROPOSAL_ONLY",wait=0),
                case(T0+3600,"INSUFFICIENT_SOURCE_CYCLES"),
                case(T0+3900,"RESEARCH_PROPOSAL_ONLY",wait=0),
            ])
            with sqlite3.connect(stock) as c:
                c.execute("CREATE TABLE sanity(x)")
            calls=[]
            def scorer(db,country,item,arrival,asof):
                calls.append((country,item,arrival,asof))
                if arrival==T0+600+FLIGHT:
                    return "POLL_STATE_PROXY_SUCCESS",True,{
                        "pre_quantity":75,"post_quantity":60}
                if arrival==T0+FLIGHT:
                    return "POLL_STATE_PROXY_MISS",False,{
                        "pre_quantity":0,"post_quantity":0}
                return "POLL_COVERAGE_TOO_SPARSE",None,{}
            result=m.v75_report(
                ledger=old,stock=stock,asof=T0+8000,
                days=1,scorer=scorer)
            self.assertEqual(
                result["unique_item_UTC_hourly_first_issues_in_scope"],2)
            s=result["summary"]
            self.assertEqual(s["first_item_UTC_hourly_starts"],2)
            self.assertEqual(s["valid_departure_proposals"],1)
            self.assertEqual(s["no_valid_departure_or_abstention"],1)
            self.assertEqual(s["matched_flight_outcomes"],1)
            self.assertEqual(s["matched_only_old_model_stocked"],1)
            self.assertEqual(s["matched_only_leave_now_stocked"],0)
            self.assertEqual(s["old_model_arrival_stock_at_least_30"],1)
            self.assertEqual(len(calls),2)
            self.assertEqual(
                result["recent_paired_arrival_observations"][0][
                    "observed_bracketing_stock_quantities"],[75,60])
            self.assertFalse(result[
                "recent_paired_arrival_observations"][0][
                    "country_update_freshness_verified"])

    def test_pending_unknown_is_not_claimed_miss(self):
        with tempfile.TemporaryDirectory() as temp:
            old=Path(temp)/"old.db"
            stock=Path(temp)/"stock.db"
            ledger_at(old,[case(T0,"RESEARCH_PROPOSAL_ONLY",600)])
            with sqlite3.connect(stock) as c:c.execute("CREATE TABLE sanity(x)")
            def scorer(db,country,item,arrival,asof):
                return "PENDING",None,{}
            summary=m.v75_report(
                ledger=old,stock=stock,asof=T0+1100,
                days=1,scorer=scorer)["summary"]
            self.assertEqual(summary["old_model_arrival_unknown_or_pending"],1)
            self.assertEqual(summary["old_model_arrival_stock_below_30"],0)
            self.assertEqual(summary["old_model_arrivals_still_pending"],1)
            self.assertEqual(summary["matched_flight_outcomes"],0)

    def test_legacy_validity_validation_blocks_false_departure(self):
        with tempfile.TemporaryDirectory() as temp:
            old=Path(temp)/"old.db"
            stock=Path(temp)/"stock.db"
            ledger_at(old,[case(T0,"RESEARCH_PROPOSAL_ONLY",30000)])
            with sqlite3.connect(stock) as c:c.execute("CREATE TABLE sanity(x)")
            def should_not_score(*args):
                self.fail("outside-horizon invalid issue must not be scored")
            summary=m.v75_report(ledger=old,stock=stock,
                                 asof=T0+1000,days=1,
                                 scorer=should_not_score)["summary"]
            self.assertEqual(summary["valid_departure_proposals"],0)
            self.assertEqual(summary["no_valid_departure_or_abstention"],1)

    def test_max_limit_aborts_large_raw_dataset(self):
        with tempfile.TemporaryDirectory() as temp:
            old=Path(temp)/"old.db"
            stock=Path(temp)/"stock.db"
            ledger_at(old,[
                case(T0,"RESEARCH_PROPOSAL_ONLY",0),
                case(T0+300,"RESEARCH_PROPOSAL_ONLY",0),
            ])
            with sqlite3.connect(stock) as c:c.execute("CREATE TABLE sanity(x)")
            with self.assertRaisesRegex(ValueError,"bounded cap"):
                m.v75_report(ledger=old,stock=stock,
                             asof=T0+2000,days=1,max_raw=1)

    def test_inventory_absent_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(m,"OPTIONAL",(
                ("notfound",Path(temp)/"nonexistent.db",
                 "v42_candidate_decisions","computed_at"),
            )):
                a=m.inventory(asof=T0)
                self.assertEqual(a["notfound"]["status"],
                                 "NOT_FOUND_AT_KNOWN_LOCATION")

    def test_whole_24_item_roster_includes_empty_item_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            old=Path(temp)/"old.db"
            stock=Path(temp)/"stock.db"
            ledger_at(old,[case(T0,"INSUFFICIENT_SOURCE_CYCLES")])
            with sqlite3.connect(stock) as c:c.execute("CREATE TABLE sanity(x)")
            result=m.v75_report(ledger=old,stock=stock,asof=T0+2000,days=1)
            self.assertEqual(len(result["per_item"]),24)
            self.assertEqual(result["per_item"][
                "mex:Jaguar Plushie"]["first_item_UTC_hourly_starts"],0)


if __name__=="__main__":
    unittest.main()
