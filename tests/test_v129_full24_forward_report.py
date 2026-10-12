"""V129 strict matched first-item-UTC-hour as-issued 24-item report."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research import v129_full24_forward_report as m
from research import v128_full24_earliest_shadow as source

T0=1790000000


def record(key,issued,wait=0,abstain=False):
    country=key.split(":",1)[0]
    travel=source.TRAVEL_SECONDS[country]
    dep=None if abstain else issued+wait
    return {
        "item_key":key,"issued_epoch":issued,
        "policy_id":source.GENERATION,
        "travel_seconds":travel,
        "min_stock_at_arrival":30,
        "research_only":True,
        "published_to_website":False,
        "earliest_departure":dep,
        "earliest_arrival":None if dep is None else dep+travel,
        "departure_state":(
            "ABSTAIN" if abstain else "RESEARCH_NOW" if wait==0
            else "RESEARCH_FUTURE_WATCH_UNCONFIRMED" if wait>300
            else "RESEARCH_READY_WITHIN_5M"),
        "baseline_leave_now_departure":issued,
        "baseline_leave_now_arrival":issued+travel,
        "source_status":(
            "INSUFFICIENT_COMPLETED_CYCLES" if abstain
            else "ISSUED_EMPIRICAL_TWO_PHASE_CURVE"),
        "decision_status":(
            "ABSTAIN_INSUFFICIENT_COMPLETED_CYCLES" if abstain
            else "EARLIEST_NOW" if wait==0
            else "EARLIEST_WAIT_SUPPORTED")
    }


class Full24ForwardReportTests(unittest.TestCase):
    def test_reconfirm_requires_actual_predeparture_fresh_issue(self):
        key="jap:Xanax"
        planned=record(key,T0,1200)
        a=record(key,T0+900,300)
        self.assertEqual(m.reconfirm(planned,[planned,a]),
                         "RECONFIRMED_FRESH_NEAR_DEPARTURE")
        self.assertEqual(m.reconfirm(planned,[planned]),
                         "FUTURE_WATCH_NOT_RECONFIRMED")
        self.assertEqual(m.reconfirm(record(key,T0,0),[]),
                         "RESEARCH_NOW_OR_FRESH_5M")
        withdrawn=record(key,T0+900,abstain=True)
        self.assertEqual(m.reconfirm(planned,[planned,withdrawn]),
                         "RECONFIRMED_MODEL_ABSTAINED")

    def test_hourly_never_counts_twelve_duplicate_ticks(self):
        a=record("uni:Red Fox Plushie",T0,1200)
        # Bucket using actual UTC hour (not relative-to-T0).
        issue=(T0//3600)*3600
        data=[record("uni:Red Fox Plushie",issue+300*k)
              for k in range(12)]
        hourly=m.choose_hourly_starts(data)
        self.assertEqual(len(hourly),1)
        self.assertEqual(hourly[0]["issued_epoch"],issue)

    def test_unknown_or_abstain_not_counted_as_failure(self):
        r=[
            {**record("uni:Nessie Plushie",T0,0),
             "model_hit":None,"now_hit":True,
             "model_evidence":"PROVIDER_SWITCH",
             "reconfirmation":"RESEARCH_NOW_OR_FRESH_5M"},
            {**record("uni:Nessie Plushie",T0+3600,abstain=True),
             "model_hit":None,"now_hit":True,
             "model_evidence":"NO_DEPARTURE",
             "reconfirmation":"ABSTAIN_NOT_EXECUTABLE"},
            {**record("uni:Nessie Plushie",T0+7200,600),
             "model_hit":True,"now_hit":False,
             "model_evidence":"POLL_STATE_PROXY_SUCCESS",
             "reconfirmation":"FUTURE_WATCH_NOT_RECONFIRMED"},
        ]
        stats=m.one_item_summary(r)
        self.assertEqual(stats["first_issue_UTC_item_hours"],3)
        self.assertEqual(stats["abstained_hours"],1)
        self.assertEqual(stats["proposed_departure_hours"],2)
        self.assertEqual(stats["model_proxy_unknown"],1)
        self.assertEqual(stats["model_proxy_miss"],0)
        self.assertEqual(stats["matched_pair"]["model_only_hit"],1)
        self.assertTrue(stats["no_actual_gameplay_trips_proven"])

    def test_validation_rejects_false_model_identity_or_travel(self):
        ok=record("mex:Dahlia",T0,0)
        tampered=dict(ok,travel_seconds=1234)
        valid,invalid=m._parse([
            ("mex:Dahlia",T0,json.dumps(ok)),
            ("mex:Dahlia",T0+3600,json.dumps(tampered)),
        ],source.exact_roster())
        self.assertEqual(len(valid),1)
        self.assertEqual(invalid["INVALID_RECORDED_FORECAST"],1)

    def test_report_matures_and_compares_two_issued_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger=Path(tmp)/"shadow.db"
            stock=Path(tmp)/"collector.db"
            issued=(T0//3600)*3600
            k1="uni:Nessie Plushie"
            k2="mex:Jaguar Plushie"
            rows=[
                record(k1,issued,1200),
                record(k1,issued+300,1200),
                record(k1,issued+900,300),
                record(k2,issued,0),
                record(k2,issued+300,0),
                record(k1,issued+3600,abstain=True),
            ]
            with sqlite3.connect(ledger) as conn:
                conn.execute("""CREATE TABLE v128_issued(
                    item_key TEXT, issued_epoch INTEGER,
                    policy_id TEXT, payload_json TEXT)""")
                conn.executemany("""INSERT INTO v128_issued(
                    item_key,issued_epoch,policy_id,payload_json
                ) VALUES (?,?,?,?)""",[
                    (r["item_key"],r["issued_epoch"],
                     source.GENERATION,json.dumps(r)) for r in rows
                ])
                conn.commit()
            with sqlite3.connect(stock) as conn:
                conn.execute("CREATE TABLE sanity(x)")
            queries=[]
            def score(db,country,item,arrival,asof):
                queries.append((country,item,arrival,asof))
                if item=="Nessie Plushie":
                    return ("POLL_STATE_PROXY_SUCCESS",True,{})
                if item=="Jaguar Plushie":
                    return ("POLL_STATE_PROXY_MISS",False,{})
                return ("NO_POLL_BRACKET",None,{})
            out=m.audit(
                ledger=ledger,stock=stock,roster=source.ROSTER,
                now=issued+4500,days=1,scorer=score)
            self.assertEqual(out["roster"],24)
            self.assertEqual(out["raw_five_minute_issue_rows"],6)
            self.assertEqual(out["first_item_UTC_hourly_cohorts"],3)
            self.assertEqual(
                out["per_item"][k1]["recheck_status_counts"]["RECONFIRMED_FRESH_NEAR_DEPARTURE"],
                1)
            self.assertEqual(out["per_item"][k1]["abstained_hours"],1)
            self.assertEqual(out["per_item"][k2]["matched_pair"]["both_miss"],1)
            self.assertEqual(out["overall"]["model_proxy_success"],1)
            self.assertEqual(out["overall"]["model_proxy_miss"],1)
            self.assertEqual(len(out["per_item"]),24)
            self.assertTrue(all(q[3]==issued+4500 for q in queries))


if __name__=="__main__":
    unittest.main()
