"""V113 fixed event-phase offsets, matched choices and full CLI smoke."""
import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import v113_phase_offset_departure_comparison as m
from research.v107_explicit_restock_cycle_baseline import StockObservation

T0=1700000000


def cycles(n=160,low=900,high=1800):
    t=T0
    obs=[StockObservation(t,0,"yata")]
    for _ in range(n):
        t+=low
        obs.append(StockObservation(t,300,"yata"))
        t+=high
        obs.append(StockObservation(t,0,"yata"))
    return obs


def programmed_prediction(item,historical,*,asof,collection_gaps):
    assert all(r.epoch<=asof for r in historical)
    assert historical[-1].epoch<=asof
    # Delayed decision deliberately supported on starts not divisible by
    # 15-minute stock cycles; deterministic pre-outcome fixture.
    dep=asof if asof%1800==0 else asof+600
    return {
        "status":"FORECAST_AVAILABLE",
        "windows":[{"earliest_expected_departure":dep}],
    }


class EventOffsetDiagnostics(unittest.TestCase):
    def test_original_depleted_and_stocked_anchors_are_distinct_events(self):
        obs=cycles()
        events,_=m.transition_episodes(obs)
        lo=m.prespecified_anchors(obs,events,"DEPLETED",12)
        hi=m.prespecified_anchors(obs,events,"STOCKED",12)
        self.assertEqual(len(lo),12)
        self.assertEqual(len(hi),12)
        self.assertTrue(all(x["phase"]=="DEPLETED" for x in lo))
        self.assertTrue(all(x["phase"]=="STOCKED" for x in hi))
        self.assertEqual(len(set(x["issue"] for x in lo)),12)

    def test_live_decision_sees_only_rows_known_at_fixed_issue_time(self):
        obs=cycles()
        epochs=[r.epoch for r in obs]
        ep=m.prespecified_anchors(
            obs,m.transition_episodes(obs)[0],"DEPLETED",2)[0]
        issue=ep["issue"]+300
        seen=[]
        def forecast(key,hist,*,asof,collection_gaps):
            self.assertTrue(all(x.epoch<=asof for x in hist))
            seen.append(asof)
            return {"status":"FORECAST_AVAILABLE","windows":[
                {"earliest_expected_departure":asof+600}]}
        result,reason=m.one_decision(
            obs,epochs,(),issued_at=issue,
            item_key="uni:Nessie Plushie",predictor=forecast)
        self.assertIsNone(reason)
        self.assertEqual(result["departure"],issue+600)
        self.assertEqual(seen,[issue])

    def test_same_departure_uncertain_proxy_has_exact_zero_difference(self):
        obs=cycles()
        x=m.analyze_item(
            obs,(),item_key="uni:Nessie Plushie",max_per_phase=2,
            predictor=lambda key,hist,*,asof,collection_gaps:{
                "status":"FORECAST_AVAILABLE","windows":[
                    {"earliest_expected_departure":asof}]})
        for phase in ("STOCKED","DEPLETED"):
            for offset in ("0","5","15","30"):
                z=x["phases"][phase][offset]
                self.assertEqual(z["same_as_now"],2)
                self.assertEqual(z["model_delayed"],0)
                bounds=z["all_matched_proxy"][
                    "possible_delta_success_per_anchor_bounds"]
                self.assertEqual(bounds["lower"],0)
                self.assertEqual(bounds["upper"],0)
                self.assertEqual(z["DELAYED_ONLY_matched_proxy"]["anchors"],0)

    def test_delayed_subset_separately_excludes_identical_choices(self):
        obs=cycles()
        x=m.analyze_item(
            obs,(),item_key="uni:Red Fox Plushie",max_per_phase=2,
            predictor=lambda key,hist,*,asof,collection_gaps:{
                "status":"FORECAST_AVAILABLE","windows":[
                    {"earliest_expected_departure":asof+600}]})
        for phase in ("STOCKED","DEPLETED"):
            for offset in ("0","5","15","30"):
                z=x["phases"][phase][offset]
                self.assertEqual(z["model_delayed"],2)
                self.assertEqual(z["same_as_now"],0)
                self.assertEqual(
                    z["DELAYED_ONLY_matched_proxy"]["anchors"],2)

    def test_asof_collector_gap_disqualifies_issue_not_silent_forecast(self):
        obs=cycles()
        issue=obs[30].epoch+180
        result,reason=m.one_decision(
            obs,[x.epoch for x in obs],
            [(obs[30].epoch+5,issue+5)],
            issued_at=issue,item_key="uni:Nessie Plushie",
            predictor=programmed_prediction)
        self.assertIsNone(result)
        self.assertEqual(reason,"COLLECTOR_GAP_SINCE_OBSERVATION")

    def test_no_prior_stock_observation_is_ineligible(self):
        obs=cycles()
        result,reason=m.one_decision(
            obs,[x.epoch for x in obs],(),
            issued_at=T0-20,item_key="uni:Nessie Plushie",
            predictor=programmed_prediction)
        self.assertIsNone(result)
        self.assertEqual(reason,"NO_PRIOR_ROW")

    def test_cli_runs_json_and_text_through_complete_reporting_path(self):
        obs=cycles()
        with tempfile.TemporaryDirectory() as tmp:
            dbpath=Path(tmp)/"sample.sqlite"
            conn=sqlite3.connect(dbpath)
            try:
                conn.execute("""CREATE TABLE stock_history (
                    id INTEGER PRIMARY KEY,
                    timestamp INTEGER NOT NULL,
                    country TEXT, item_name TEXT, quantity INTEGER, source TEXT
                )""")
                conn.execute("""CREATE TABLE collection_gaps (
                    start_timestamp INTEGER,end_timestamp INTEGER
                )""")
                conn.executemany(
                    """INSERT INTO stock_history
                       (timestamp,country,item_name,quantity,source)
                       VALUES (?,?,?,?,?)""",
                    [(x.epoch,"uni","Nessie Plushie",x.quantity,x.source)
                     for x in obs])
                conn.commit()
            finally:
                conn.close()
            with (patch.object(m,"SOURCE",str(dbpath)),
                  patch.object(m,"approved_collector_source",return_value=True)):
                for json_mode in (False,True):
                    args=["v113","--target","nessie","--events-per-phase","2"]
                    if json_mode:args.append("--json")
                    buf=io.StringIO()
                    with (patch.object(sys,"argv",args),
                          contextlib.redirect_stdout(buf)):
                        m.main()
                    output=buf.getvalue()
                    if json_mode:
                        report=json.loads(output)
                        self.assertEqual(report["status"],
                                         "V113_PHASE_OFFSET_DELAY_DISCRIMINATION_AUDIT")
                        self.assertTrue(report["read_only"])
                        self.assertEqual(report["items"]["nessie"]["phases"][
                            "DEPLETED"]["5"]["selected_distinct_anchor_events"],2)
                    else:
                        self.assertIn(
                            "V113 FIXED-OFFSET EVENT-BASED DECISIONS",
                            output)
                        self.assertIn("elapsed_seconds:",output)


if __name__=="__main__":
    unittest.main()
