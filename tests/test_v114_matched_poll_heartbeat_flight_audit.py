"""V114: actual poll brackets vs sparse stock change rows, CLI tests."""
import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import v114_matched_poll_heartbeat_flight_audit as m
from research.v107_explicit_restock_cycle_baseline import StockObservation
from research.v111_arrival_proxy_evidence_audit import arrival_evidence

T0=1700000000
COUNTRY="uni"
ITEM="Red Fox Plushie"


def fixture_db(db):
    db.executescript("""
        CREATE TABLE stock_history (
            id INTEGER PRIMARY KEY,timestamp INTEGER,
            country TEXT,item_name TEXT,quantity INTEGER,source TEXT);
        CREATE TABLE collection_gaps (
            start_timestamp INTEGER,end_timestamp INTEGER);
        CREATE TABLE poll_heartbeats (
            id INTEGER PRIMARY KEY,timestamp INTEGER,
            mode TEXT,success INTEGER,source TEXT);
    """)


def long_stock_rows(n=500):
    rows=[]
    t=T0
    rows.append((t,COUNTRY,ITEM,0,"yata"))
    for _ in range(n):
        t+=900
        rows.append((t,COUNTRY,ITEM,300,"yata"))
        t+=1800
        rows.append((t,COUNTRY,ITEM,0,"yata"))
    return rows


class HeartbeatArrivalEvidenceTests(unittest.TestCase):
    def test_stable_stock_no_change_near_arrival_scored_by_poll(self):
        conn=sqlite3.connect(":memory:")
        try:
            fixture_db(conn)
            # The latest item CHANGE is four minutes before arrival.
            # Heartbeats establish actual polls before and after it.
            arrival=T0+900
            conn.execute("""INSERT INTO stock_history
                (timestamp,country,item_name,quantity,source)
                VALUES (?,?,?,?,?)""",(arrival-240,COUNTRY,ITEM,500,"yata"))
            for stamp in (arrival-30,arrival+40):
                conn.execute("""INSERT INTO poll_heartbeats
                    (timestamp,mode,success,source)
                    VALUES (?,'poll-cycle',1,'yata')""",(stamp,))
            conn.commit()
            ev=m.heartbeat_arrival_evidence(
                conn,COUNTRY,ITEM,arrival,arrival+500)
            self.assertEqual(ev["reason"],"POLL_STATE_PROXY_SUCCESS")
            self.assertTrue(ev["strict_bracket_proxy"])
            self.assertFalse(ev["polling_proxy_country_freshness_verified"])
            # V111 requires a second STOCK CHANGE row and stays unknown.
            raw=[StockObservation(arrival-240,500,"yata")]
            weaker=arrival_evidence(raw,[x.epoch for x in raw],(),arrival)
            self.assertIsNone(weaker["strict_bracket_proxy"])
        finally:
            conn.close()

    def test_old_carried_forward_item_change_is_censored(self):
        def fake(*args,**kw):
            return ("POLL_STATE_PROXY_SUCCESS",True,{
                "pre_state_age_s":5000,"post_state_age_s":5100})
        out=m.heartbeat_arrival_evidence(
            None,COUNTRY,ITEM,T0+800,T0+900,poll_func=fake)
        self.assertIsNone(out["strict_bracket_proxy"])
        self.assertEqual(out["reason"],"CARRIED_STOCK_CHANGE_TOO_OLD")

    def test_provider_switch_or_poll_gap_does_not_produce_success(self):
        def fake(*args,**kw):
            return ("PROVIDER_SWITCH",None,{
                "pre_poll_lag_s":20,"post_poll_lag_s":30})
        out=m.heartbeat_arrival_evidence(
            None,COUNTRY,ITEM,T0+800,T0+900,poll_func=fake)
        self.assertIsNone(out["strict_bracket_proxy"])
        self.assertEqual(out["reason"],"PROVIDER_SWITCH")

    def test_scored_poll_without_stock_ages_is_not_trusted(self):
        def broken(*args,**kw):
            return ("POLL_STATE_PROXY_SUCCESS",True,{})
        with self.assertRaisesRegex(AssertionError,"stock change ages"):
            m.heartbeat_arrival_evidence(
                None,COUNTRY,ITEM,T0+800,T0+900,poll_func=broken)

    def test_v113_identical_outcomes_remain_tied_under_poll_proxy(self):
        def same_model(item,historical,*,asof,collection_gaps):
            self.assertTrue(all(r.epoch<=asof for r in historical))
            return {"status":"FORECAST_AVAILABLE","windows":[{
                "earliest_expected_departure":asof}]}
        def scorer(obs,epochs,gaps,arrival):
            return {"strict_bracket_proxy":None,
                    "last_known_proxy":None,"reason":"NO_POLL_BRACKET"}
        observations=[
            StockObservation(x[0],x[4],x[5])
            for x in long_stock_rows()]
        from research.v113_phase_offset_departure_comparison import analyze_item
        r=analyze_item(
            observations,(),item_key=f"{COUNTRY}:{ITEM}",max_per_phase=2,
            predictor=same_model,scorer=scorer)
        for phase in ("STOCKED","DEPLETED"):
            for offset,group in r["phases"][phase].items():
                self.assertEqual(group["same_as_now"],2)
                self.assertEqual(group["model_delayed"],0)
                d=group["all_matched_proxy"][
                    "possible_delta_success_per_anchor_bounds"]
                self.assertEqual(d["lower"],0)
                self.assertEqual(d["upper"],0)

    def test_cli_readonly_json_and_text_reports_finish(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"history.sqlite"
            con=sqlite3.connect(path)
            try:
                fixture_db(con)
                con.executemany("""INSERT INTO stock_history
                    (timestamp,country,item_name,quantity,source)
                    VALUES (?,?,?,?,?)""",long_stock_rows())
                last=T0+500*2700
                for stamp in (last-40,last+60,last+200):
                    con.execute("""INSERT INTO poll_heartbeats
                        (timestamp,mode,success,source)
                        VALUES (?,'poll-cycle',1,'yata')""",(stamp,))
                con.commit()
            finally:
                con.close()
            with (patch.object(m,"SOURCE",str(path)),
                  patch.object(m,"approved_collector_source",return_value=True)):
                for json_mode in (False,True):
                    args=["v114","--target","redfox",
                          "--events-per-phase","2"]
                    if json_mode:args.append("--json")
                    output=io.StringIO()
                    with (patch.object(sys,"argv",args),
                          contextlib.redirect_stdout(output)):
                        m.main()
                    if json_mode:
                        report=json.loads(output.getvalue())
                        self.assertEqual(report["status"],
                            "V114_MATCHED_FLIGHT_POLL_HEARTBEAT_STATE_AUDIT")
                        self.assertTrue(report["read_only"])
                        self.assertFalse(report[
                            "country_fresh_provider_update_epoch_available"])
                        self.assertEqual(
                            report["items"]["redfox"]["phases"][
                                "STOCKED"]["5"]["selected_distinct_anchor_events"],2)
                    else:
                        self.assertIn(
                            "V114 V113 MATCHED FLIGHTS",
                            output.getvalue())
                        self.assertIn("elapsed_s",output.getvalue())


if __name__=="__main__":
    unittest.main()
