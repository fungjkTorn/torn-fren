"""V112 identical-issue direct-flight benchmark and uncertain-outcome bounds."""
import unittest
import contextlib
import io
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from research import v112_matched_immediate_vs_restock_flight_audit as m
from research.v107_explicit_restock_cycle_baseline import StockObservation

T0=1700000000


def evidence(strict,weak=None,reason="FIXTURE"):
    return {
        "strict_bracket_proxy":strict,
        "last_known_proxy":strict if weak is None else weak,
        "reason":reason,
    }


def fake_record(issue,model,now,wait=600):
    return {
        "issue":issue,
        "departure":issue+wait,
        "model_evidence":evidence(model),
        "now_evidence":evidence(now),
    }


def stock_cycles(n=400,low=900,high=1800):
    t=T0
    obs=[StockObservation(t,0,"yata")]
    for _ in range(n):
        t+=low
        obs.append(StockObservation(t,200,"yata"))
        t+=high
        obs.append(StockObservation(t,0,"yata"))
    return obs


class MatchedArrivalEvidenceTests(unittest.TestCase):
    def test_identical_anchors_counts_matched_not_independent(self):
        rec=[
            fake_record(T0,True,False),
            fake_record(T0+900,None,True),
            fake_record(T0+1800,True,None),
        ]
        out=m.paired_summary(rec)
        self.assertEqual(out["anchors"],3)
        self.assertEqual(out["model"]["evidence_hits"],2)
        self.assertEqual(out["model"]["uncertain"],1)
        self.assertEqual(out["depart_now"]["evidence_hits"],1)
        self.assertEqual(out["certain_model_better_now_worse"],1)
        self.assertEqual(out["certain_model_worse_now_better"],0)
        self.assertEqual(out["paired_known_comparisons"],1)
        self.assertEqual(out["possible_delta_success_per_anchor_bounds"],
            {"lower":0.0,"upper":0.6667,
             "meaning":"deterministic unknown-outcome sensitivity bounds; NOT statistical CI"})

    def test_model_can_lose_against_immediate_on_same_start(self):
        rec=[fake_record(T0,False,True)]
        out=m.paired_summary(rec)
        self.assertEqual(out["certain_model_worse_now_better"],1)
        self.assertEqual(out["possible_delta_success_per_anchor_bounds"]["lower"],-1)
        self.assertEqual(out["possible_delta_success_per_anchor_bounds"]["upper"],-1)

    def test_both_positive_is_not_a_model_specific_win(self):
        rec=[fake_record(T0,True,True)]
        out=m.paired_summary(rec)
        self.assertEqual(out["joint_strict_evidence"],{"HIT_vs_HIT":1})
        self.assertEqual(out["certain_model_better_now_worse"],0)
        self.assertEqual(out["certain_model_worse_now_better"],0)
        self.assertEqual(out["possible_delta_success_per_anchor_bounds"]["lower"],0)
        self.assertEqual(out["possible_delta_success_per_anchor_bounds"]["upper"],0)

    def test_no_anchor_is_not_100_percent(self):
        out=m.paired_summary([])
        self.assertEqual(out["anchors"],0)
        self.assertIsNone(out["forecasted_departure_coverage"])
        self.assertIsNone(out["possible_delta_success_per_anchor_bounds"]["upper"])

    def test_same_causal_depletion_issues_for_both_policies(self):
        data=stock_cycles()
        seen=[]
        def model(item,historical,*,asof,collection_gaps):
            self.assertTrue(historical)
            self.assertEqual(historical[-1].epoch,asof)
            self.assertTrue(all(row.epoch<=asof for row in historical))
            self.assertLess(historical[-1].quantity,30)
            seen.append(asof)
            return {"windows":[
                {"earliest_expected_departure":asof+300},
                {"earliest_expected_departure":asof+1800},
            ]}
        out=m.audit_item(
            data,(),item_key="uni:Nessie Plushie",max_events=5,
            predictor=model)
        self.assertEqual(out["anchors"],5)
        self.assertEqual(len(seen),5)
        self.assertEqual(out["forecasted_departures"],5)
        self.assertEqual(out["hop_distribution"],{"1":5})
        self.assertEqual(out["model_wait_minutes"]["mean"],5)
        self.assertEqual(out["model"]["evidence_hits"]
                         +out["model"]["evidence_misses"]
                         +out["model"]["uncertain"],5)
        self.assertEqual(out["depart_now"]["evidence_hits"]
                         +out["depart_now"]["evidence_misses"]
                         +out["depart_now"]["uncertain"],5)
        self.assertFalse(out["country_provider_asof_verified"])

    def test_first_reachable_plan_is_minimum_departure_not_latest_hop(self):
        data=stock_cycles()
        def model(item,historical,*,asof,collection_gaps):
            return {"windows":[
                {"earliest_expected_departure":None},
                {"earliest_expected_departure":asof+900},
                {"earliest_expected_departure":asof+600},
            ]}
        out=m.audit_item(
            data,(),item_key="uni:Red Fox Plushie",max_events=4,
            predictor=model)
        self.assertEqual(out["hop_distribution"],{"3":4})
        self.assertEqual(out["model_wait_minutes"]["mean"],10)

    def test_past_only_forecast_can_abstain_and_now_still_scored(self):
        data=stock_cycles()
        def abstain(item,historical,*,asof,collection_gaps):
            return {"windows":[]}
        out=m.audit_item(
            data,(),item_key="uni:Red Fox Plushie",max_events=4,
            predictor=abstain)
        self.assertEqual(out["forecasted_departures"],0)
        self.assertEqual(out["anchors"],4)
        self.assertEqual(out["model"]["uncertain"],0)
        self.assertEqual(out["model"]["not_departed"],4)
        self.assertEqual(out["possible_delta_success_per_anchor_bounds"]["upper"],0.0)
        self.assertEqual(out["depart_now"]["evidence_hits"]
                         +out["depart_now"]["evidence_misses"]
                         +out["depart_now"]["uncertain"],4)


    def test_cli_report_completes_with_sqlite_fixture_in_json_and_text_modes(self):
        # V112 previously finished its calculations and crashed at the
        # final report due to an undefined stopwatch variable. Exercise
        # main() all the way through formatting, not only audit_item().
        obs=stock_cycles()
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"raw_fixture.sqlite"
            db=sqlite3.connect(path)
            try:
                db.execute("""CREATE TABLE stock_history (
                    id INTEGER PRIMARY KEY,
                    timestamp INTEGER NOT NULL,
                    country TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    source TEXT NOT NULL
                )""")
                db.execute("""CREATE TABLE collection_gaps (
                    start_timestamp INTEGER, end_timestamp INTEGER
                )""")
                db.executemany(
                    """INSERT INTO stock_history
                       (timestamp,country,item_name,quantity,source)
                       VALUES (?,?,?,?,?)""",
                    [(r.epoch,"uni","Nessie Plushie",r.quantity,r.source)
                     for r in obs])
                db.commit()
            finally:
                db.close()

            with (patch.object(m,"SOURCE",str(path)),
                  patch.object(m,"approved_collector_source",return_value=True)):
                for is_json in (True,False):
                    argv=["v112","--target","nessie","--events","2"]
                    if is_json:argv.append("--json")
                    capture=io.StringIO()
                    with (patch.object(sys,"argv",argv),
                          contextlib.redirect_stdout(capture)):
                        m.main()
                    output=capture.getvalue()
                    if is_json:
                        result=json.loads(output)
                        self.assertEqual(result["status"],
                          "V112_MATCHED_DEPART_NOW_VS_MULTI_CYCLE_FLIGHT_EVIDENCE")
                        self.assertTrue(result["read_only"])
                        self.assertEqual(result["items"]["nessie"]["anchors"],2)
                        self.assertGreaterEqual(result["duration_seconds"],0)
                    else:
                        self.assertIn(
                            "V112 MATCHED DEPART NOW VS MULTI-RESTOCK FLIGHT",
                            output)
                        self.assertIn("elapsed seconds:",output)


if __name__=="__main__":
    unittest.main()
