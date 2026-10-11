"""V115 unit checks for bounded item-filtered forward report."""
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from research import v115_targeted_v88_forward_evidence as audit
from research import v88_poll_state_forward_report as base


class FilteredAuditTests(unittest.TestCase):
    def test_global_capacity_and_item_pushdown(self):
        with TemporaryDirectory() as d:
            ledger=Path(d)/"ledger.sqlite"
            stock=Path(d)/"stock.sqlite"
            issue=1700001000
            now=1700012000
            arrival=issue+6360
            with sqlite3.connect(ledger) as c:
                c.execute("""CREATE TABLE v42_candidate_decisions(
                    id INTEGER PRIMARY KEY,item_key TEXT,computed_at INTEGER,
                    stock_as_of INTEGER,status TEXT,valid_until INTEGER,
                    departure INTEGER,arrival INTEGER,
                    actual_player_departure INTEGER)""")
                rows=[(f"uni:Other {i}",issue,issue,
                       "RESEARCH_PROPOSAL_ONLY",issue+300,
                       issue,arrival,0) for i in range(1305)]
                rows += [(key,issue,issue,"RESEARCH_PROPOSAL_ONLY",
                          issue+300,issue,arrival,0)
                         for key in audit.ITEMS.values()]
                c.executemany("""INSERT INTO v42_candidate_decisions
                    (item_key,computed_at,stock_as_of,status,valid_until,
                     departure,arrival,actual_player_departure)
                    VALUES (?,?,?,?,?,?,?,?)""",rows)
                c.commit()
            with sqlite3.connect(stock) as c:
                c.execute("""CREATE TABLE stock_history(
                    id INTEGER PRIMARY KEY,timestamp INTEGER,
                    quantity INTEGER,country TEXT,item_name TEXT,source TEXT)""")
                c.execute("""CREATE TABLE poll_heartbeats(
                    id INTEGER PRIMARY KEY,timestamp INTEGER,
                    source TEXT,mode TEXT,success INTEGER)""")
                c.execute("""CREATE TABLE collection_gaps(
                    start_timestamp INTEGER,end_timestamp INTEGER)""")
                for item in ("Red Fox Plushie","Nessie Plushie"):
                    c.execute("""INSERT INTO stock_history
                        (timestamp,quantity,country,item_name,source)
                        VALUES (?,?,?,?,?)""",
                        (arrival-200,100,"uni",item,"yata"))
                for t in (arrival-30,arrival+40):
                    c.execute("""INSERT INTO poll_heartbeats
                        (timestamp,source,mode,success)
                        VALUES (?,'yata','poll-cycle',1)""",(t,))
                c.commit()
            with self.assertRaisesRegex(ValueError,"more arrival targets"):
                base.report(ledger=ledger,stock=stock,days=1,
                            limit=1200,now=now)
            result=audit.audit(ledger=ledger,stock=stock,now=now,hours=24)
            self.assertEqual(result[
                "all_roster_raw_candidate_rows_NOT_ALL_SCORED"],1307)
            report=result["targeted_v88_evidence"]
            self.assertEqual(report["unique_item_arrival_targets"],2)
            self.assertEqual(report["proxy_success"],2)
            self.assertEqual(report[
                "matched_immediate_departure_baseline"]["both_success"],2)
            self.assertFalse(result["upstream_country_stock_freshness_verified"])
            with sqlite3.connect(ledger) as c:
                c.row_factory=sqlite3.Row
                with self.assertRaisesRegex(ValueError,"narrow --hours"):
                    audit.select_item_arrivals(
                        c,start=issue-1,end=issue+1,
                        keys=tuple(audit.ITEMS.values()),cap=1)
            empty=audit.audit(ledger=ledger,stock=stock,now=now,hours=1)
            self.assertEqual(empty["targeted_v88_evidence"][
                "unique_item_arrival_targets"],0)


if __name__=="__main__":
    unittest.main()
