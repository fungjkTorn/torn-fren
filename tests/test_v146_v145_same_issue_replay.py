"""V146: representative issue-locked comparison including mature vs pending."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import v146_v145_same_issue_replay as m
from research import v128_full24_earliest_shadow as original
from research.v107_explicit_restock_cycle_baseline import StockObservation as O

T=1791800000
ITEM="uni:Nessie Plushie"


def phases():
    t=T-50000
    result=[O(t,0,"yata")]
    for _ in range(11):
        t+=600
        result.append(O(t,110,"yata"))
        t+=100
        result.append(O(t,105,"prometheus"))
        t+=100
        result.append(O(t,100,"yata"))
        t+=800
        result.append(O(t,0,"yata"))
        t+=100
        result.append(O(t,0,"prometheus"))
        t+=100
        result.append(O(t,0,"yata"))
    return result,t


def make_db(folder):
    src=Path(folder)/"stock.db"
    side=Path(folder)/"shadow.db"
    observations,issued=phases()
    with sqlite3.connect(src) as con:
        con.execute("""CREATE TABLE stock_history(
           id INTEGER PRIMARY KEY,timestamp INTEGER,quantity INTEGER,
           source TEXT,country TEXT,item_name TEXT)""")
        con.execute("""CREATE TABLE collection_gaps(
           start_timestamp INTEGER,end_timestamp INTEGER)""")
        con.execute("""CREATE TABLE poll_heartbeats(
           id INTEGER PRIMARY KEY,timestamp INTEGER,source TEXT,
           mode TEXT, success INTEGER)""")
        con.executemany("""INSERT INTO stock_history(
           timestamp,quantity,source,country,item_name) VALUES (?,?,?,?,?)""",[
           (x.epoch,x.quantity,x.source,"uni","Nessie Plushie")
           for x in observations])
    roster=original.exact_roster()
    record=original.item_record(
        ITEM,roster[ITEM],observations,[],issued=issued)
    with sqlite3.connect(side) as con:
        con.execute("""CREATE TABLE v128_issued(
            item_key TEXT, issued_epoch INTEGER,
            source_status TEXT,decision_status TEXT,payload_json TEXT)""")
        con.execute("""INSERT INTO v128_issued VALUES (?,?,?,?,?)""",(
            ITEM,issued,record["source_status"],record["decision_status"],
            json.dumps(record)))
    return src,side,issued


class SameIssueReplayTests(unittest.TestCase):
    def test_strict_old_recovery_is_not_new_live_success_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            src,side,issued=make_db(temp)
            earlier_bytes=(src.read_bytes(),side.read_bytes())
            with patch.object(m,"_pair_score",return_value="HIT"), (
                patch.object(m,"earliest_credible_for_country",
                    side_effect=lambda curve,key: {
                        "status":"EARLIEST_NOW","departure":curve["asof_epoch"],
                        "arrival":curve["asof_epoch"]+original.TRAVEL_SECONDS["uni"],
                        "score":.65,
                    })
            ):
                result=m.replay(collector=src,sidecar=side,
                                now=issued+12000,max_model_evals=10)
            self.assertEqual(result["exact_item_roster"],24)
            self.assertEqual(result["hourly_issued_cohorts"],1)
            self.assertEqual(result["monte_carlo_replayed"],1)
            row=result["items"][ITEM]
            self.assertEqual(row["recovered"],1)
            self.assertEqual(row["new_proposals"],1)
            self.assertEqual(row["original_proposals"],0)
            self.assertEqual(row["matched_new_vs_now"],1)
            self.assertEqual(row["new_only"],0)
            self.assertFalse(result["real_player_trip_success_certified"])
            self.assertFalse(result["backfill_provenance_frozen_at_original_issue"])
            self.assertFalse(result["new_future_watch_freshly_reconfirmed"])
            self.assertTrue(result["no_writes"])
            self.assertEqual(src.read_bytes(),earlier_bytes[0])
            self.assertEqual(side.read_bytes(),earlier_bytes[1])

    def test_explicit_restock_candidate_compares_on_exact_same_issue(self):
        with tempfile.TemporaryDirectory() as temp:
            src,side,issued=make_db(temp)
            recovered={
                "status":"PROVISIONAL_FIRST_REACHABLE_STOCK_WINDOW",
                "first_reachable":{
                    "cycle_number":7,
                    "earliest_departure_epoch":issued+300,
                    "arrival_epoch":issued+300+
                                    original.TRAVEL_SECONDS["uni"],
                    "provisional":True,
                },
            }
            with patch.object(m,"first_reachable_stock_cycles",
                              return_value=recovered), (
                 patch.object(m,"_pair_score",return_value="HIT")
            ):
                result=m.replay(collector=src,sidecar=side,
                                now=issued+12000,max_model_evals=10)
            row=result["items"][ITEM]
            self.assertEqual(row["explicit_proposals"],1)
            self.assertEqual(row["matched_explicit_vs_now"],1)
            self.assertEqual(row["explicit_departure_median_wait_seconds"],300)
            self.assertEqual(row["explicit_only_vs_now"],0)
            self.assertEqual(row["now_only_vs_explicit"],0)
            self.assertFalse(result["source_provider_freshness_certified"])

    def test_a_mutated_historical_snapshot_is_not_claimed_matched(self):
        with tempfile.TemporaryDirectory() as temp:
            src,side,issued=make_db(temp)
            with sqlite3.connect(side) as con:
                raw=json.loads(con.execute(
                    "SELECT payload_json FROM v128_issued").fetchone()[0])
                raw["last_stock_quantity"]=100000
                con.execute("UPDATE v128_issued SET payload_json=?",
                            (json.dumps(raw),))
            with patch.object(m,"empirical_arrival_scores") as scorer:
                result=m.replay(collector=src,sidecar=side,
                                now=issued+12000,max_model_evals=10)
                scorer.assert_not_called()
            self.assertEqual(result["monte_carlo_replayed"],0)
            self.assertEqual(result["items"][ITEM][
                "ISSUED_SOURCE_SNAPSHOT_MISMATCH"],1)

    def test_unmatured_new_outcome_cannot_count_as_hit_or_miss(self):
        with tempfile.TemporaryDirectory() as temp:
            src,side,issued=make_db(temp)
            with patch.object(m,"_pair_score",return_value="PENDING"), (
                patch.object(m,"earliest_credible_for_country",
                    side_effect=lambda curve,key: {
                        "status":"EARLIEST_WAIT_SUPPORTED",
                        "departure":curve["asof_epoch"]+600,
                        "arrival":curve["asof_epoch"]+600+
                                  original.TRAVEL_SECONDS["uni"],
                        "score":.7,
                    })
            ):
                result=m.replay(collector=src,sidecar=side,
                                now=issued+800,max_model_evals=10)
            item=result["items"][ITEM]
            self.assertEqual(item["PENDING"],1)
            self.assertEqual(item["matched_new_vs_now"],0)
            self.assertEqual(item["new_proxy_hit"] if "new_proxy_hit" in item
                             else 0,0)

    def test_replay_input_limits_guard_mutation_and_unbounded_cpu(self):
        with tempfile.TemporaryDirectory() as temp:
            src,side,issued=make_db(temp)
            for args in ({"collector":src,"sidecar":src,"now":issued},
                         {"collector":src,"sidecar":side,
                          "now":issued,"max_model_evals":0},
                         {"collector":src,"sidecar":side,"now":issued,"days":99}):
                with self.subTest(args=args),self.assertRaises(ValueError):
                    m.replay(**args)


if __name__=="__main__":
    unittest.main()
