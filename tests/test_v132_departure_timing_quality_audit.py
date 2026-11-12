"""V132 controls: never count watch as executed, no source mutation."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from research import v132_departure_timing_quality_audit as m
from research import v128_full24_earliest_shadow as v128

T0=(1790000000//3600)*3600
ITEM="uni:Red Fox Plushie"


def issued(at,*,departure_delay=1200,onset=T0-600,stock_ts=T0-300,
           status=None,key=ITEM):
    country=key.split(":",1)[0]
    flight=v128.TRAVEL_SECONDS[country]
    departure=None if departure_delay is None else at+departure_delay
    return {
        "item_key":key,"policy_id":v128.GENERATION,
        "issued_epoch":at,"travel_seconds":flight,
        "min_stock_at_arrival":30,"research_only":True,
        "published_to_website":False,
        "earliest_departure":departure,
        "earliest_arrival":None if departure is None else departure+flight,
        "departure_state":"ABSTAIN" if departure is None else
            "RESEARCH_NOW" if departure_delay==0 else
            "RESEARCH_READY_WITHIN_5M" if departure_delay<=300 else
            "RESEARCH_FUTURE_WATCH_UNCONFIRMED",
        "baseline_leave_now_departure":at,
        "baseline_leave_now_arrival":at+flight,
        "decision_status":status or (
            "ABSTAIN_CURRENT_PHASE_ONSET_UNKNOWN" if departure is None else
            "EARLIEST_NOW" if departure_delay==0 else
            "EARLIEST_WAIT_SUPPORTED"),
        "source_status":"CURRENT_PHASE_ONSET_UNKNOWN" if departure is None
            else "ISSUED_EMPIRICAL_TWO_PHASE_CURVE",
        "phase":"HIGH","phase_onset":onset,
        "last_stock_change_epoch":stock_ts,"collector_source":"yata",
        "last_stock_quantity":120,
    }


class TimingQualityTests(unittest.TestCase):
    def test_replanning_drift_with_unchanged_last_stock_input(self):
        x=issued(T0,departure_delay=1800)
        y=issued(T0+300,departure_delay=3300)
        r=m.one_item([x,y],asof=T0+99999)
        self.assertEqual(r["issued_future_watches_not_executable"],2)
        self.assertEqual(r["unchanged_collector_observed_state_pairs"],1)
        self.assertEqual(r["same_observed_state_absolute_departure_shift_gt_15min"],1)
        self.assertEqual(r["issued_proposals"],2)
        self.assertEqual(r["first_issued_item_UTC_hours"],1)
        self.assertFalse(r["reconfirmation_counts_for_first_hour_proposals"].get(
            "RECONFIRMED_FRESH_NEAR_DEPARTURE",0))

    def test_future_wait_reconfirms_only_when_fresh_ready_same_target(self):
        start=issued(T0,departure_delay=1200)
        near=issued(T0+900,departure_delay=300)
        r=m.one_item([start,near],asof=T0+1800+v128.TRAVEL_SECONDS["uni"])
        self.assertEqual(r["reconfirmation_counts_for_first_hour_proposals"][
            "RECONFIRMED_FRESH_NEAR_DEPARTURE"],1)
        self.assertEqual(r["maturity_counts_for_first_hour_proposals"][
            "matured_watch_properly_reconfirmed"],1)

    def test_no_target_vs_pending_kept_separate(self):
        series=[
            issued(T0,departure_delay=None),
            issued(T0+3600,departure_delay=1200),
        ]
        out=m.one_item(series,asof=T0+4000)
        self.assertEqual(out["issued_abstentions_or_no_supported_window"],1)
        self.assertEqual(out["issued_future_watches_not_executable"],1)
        self.assertEqual(out["maturity_counts_for_first_hour_proposals"][
            "arrival_not_yet_matured"],1)
        self.assertEqual(out["reconfirmation_counts_for_first_hour_proposals"][
            "hourly_start_abstained"],1)

    def test_unknown_stock_difference_not_called_equal(self):
        a=issued(T0)
        b=issued(T0+300,stock_ts=T0)
        self.assertFalse(m.same_observed_stock(a,b))
        self.assertIsNone(m.shifted_departure(
            issued(T0,departure_delay=None),b))

    def test_bounded_full_roster_audit_from_immutable_rows(self):
        with tempfile.TemporaryDirectory() as t:
            ledger=Path(t)/"ledger.sqlite"
            k2="mex:Jaguar Plushie"
            base=T0
            rows=[
                issued(base,departure_delay=1200),
                issued(base+300,departure_delay=2700),
                issued(base,departure_delay=None,key=k2),
            ]
            with sqlite3.connect(ledger) as db:
                db.execute("""CREATE TABLE v128_issued(
                    item_key TEXT,issued_epoch INTEGER,
                    policy_id TEXT,payload_json TEXT)""")
                db.executemany(
                    "INSERT INTO v128_issued VALUES (?,?,?,?)",
                    [(r["item_key"],r["issued_epoch"],
                      v128.GENERATION,json.dumps(r)) for r in rows])
                db.commit()
            result=m.audit(ledger=ledger,now=T0+12000,days=1)
            self.assertTrue(result["read_only"])
            self.assertEqual(result["all_24_items"],24)
            self.assertEqual(result["valid_as_issued_rows"],3)
            self.assertEqual(result["overall"]["issued_proposals"],2)
            self.assertEqual(result["overall"]["issued_abstentions_or_no_supported_window"],1)
            self.assertEqual(result["overall"][
                "same_observed_state_absolute_departure_shift_gt_15min"],1)
            self.assertEqual(result["per_item"][k2][
                "issued_abstentions_or_no_supported_window"],1)
            with sqlite3.connect(ledger) as db:
                self.assertEqual(db.execute(
                    "SELECT COUNT(*) FROM v128_issued").fetchone()[0],3)


if __name__=="__main__":
    unittest.main()
