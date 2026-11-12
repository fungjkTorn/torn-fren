"""V119 policies: check causal triple-convergence, no-lookahead, CLI reports."""
import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import v119_stable_commitment_vs_fresh_replay as m

T0=1700000000
RED="uni:Red Fox Plushie"
NES="uni:Nessie Plushie"


def rec(issue,depart,*,item=RED,family="global_regime_analog",
        status="RESEARCH_PROPOSAL_ONLY"):
    return {
        "item_key":item,"computed_at":issue,
        "model_family":family,"model_config":"test",
        "stock_as_of":issue,"status":status,
        "departure":depart,
        "arrival":None if depart is None else depart+6360,
        "valid_until":issue+300,"actual_player_departure":0,
    }


class CommitmentTests(unittest.TestCase):
    def test_three_stable_future_proposals_commit_without_future_truth(self):
        rows=[rec(T0,T0+4200),
              rec(T0+300,T0+4200),
              rec(T0+600,T0+4200),
              rec(T0+900,T0+12000)]
        epochs=[r["computed_at"] for r in rows]
        p=m.frozen_policy(rows[0],rows,epochs,asof=T0+30000)
        self.assertEqual(p["status"],"STABLE_3_COMMITMENT")
        self.assertEqual(p["departure"],T0+4200)
        self.assertEqual(p["committed_issue"],T0+600)
        self.assertEqual(p["ticks_seen"],3)
        self.assertEqual(p["basis"],"three_as_issued")

    def test_receding_one_for_one_target_never_confirms(self):
        rows=[rec(T0+300*i,T0+3600+300*i) for i in range(97)]
        p=m.frozen_policy(rows[0],rows,
                          [r["computed_at"] for r in rows],
                          asof=T0+30000)
        self.assertEqual(p["status"],
                         "NO_CONFIRMED_DEPARTURE_WITHIN_8H")
        self.assertIsNone(p["departure"])

    def test_two_similar_followed_by_different_target_reset(self):
        rows=[
            rec(T0,T0+3600),
            rec(T0+300,T0+3600),
            rec(T0+600,T0+7200),
            rec(T0+900,T0+7200),
            rec(T0+1200,T0+7200)
        ]
        p=m.frozen_policy(rows[0],rows,
                          [r["computed_at"] for r in rows],
                          asof=T0+30000)
        self.assertEqual(p["committed_issue"],T0+1200)
        self.assertEqual(p["departure"],T0+7200)

    def test_invalid_tick_interrupts_confirmation(self):
        rows=[
            rec(T0,T0+3600),
            rec(T0+300,T0+3600,status="INSUFFICIENT_HISTORY"),
            rec(T0+600,T0+3600),
            rec(T0+900,T0+3600),
            rec(T0+1200,T0+3600)
        ]
        p=m.frozen_policy(rows[0],rows,
                          [r["computed_at"] for r in rows],
                          asof=T0+30000)
        self.assertEqual(p["committed_issue"],T0+1200)

    def test_one_ready_offer_preempts_3stable_confirmation(self):
        rows=[
            rec(T0,T0+3600),
            rec(T0+300,T0+400),
            rec(T0+600,T0+3600),
            rec(T0+900,T0+3600),
            rec(T0+1200,T0+3600)
        ]
        p=m.frozen_policy(rows[0],rows,
                          [r["computed_at"] for r in rows],
                          asof=T0+30000)
        self.assertEqual(p["basis"],"fresh")
        self.assertEqual(p["departure"],T0+400)

    def test_pending_commitment_not_counted_as_success(self):
        seen=[]
        def observed(*args):
            seen.append(args)
            return "POLL_STATE_PROXY_SUCCESS",True,{}
        self.assertEqual(
            m._proxy(observed,None,"uni","Nessie Plushie",
                     T0+10000,T0+5000),
            (None,"PENDING_ARRIVAL"))
        self.assertFalse(seen)
        self.assertEqual(m._proxy(observed,None,"uni","Nessie Plushie",
                                  None,T0+5000),
                         (None,"NO_TRIP"))

    def test_identical_departure_unknown_outcomes_remain_same(self):
        def episode():
            return {"start":T0,"results":{
                "fresh_5m":{"departure":T0,"proxy_hit":None},
                "depart_now":{"departure":T0,"proxy_hit":None},
            }}
        out=m.paired([episode()],"fresh_5m","depart_now")
        self.assertEqual(out["same_departure"],1)
        self.assertEqual(out["one_or_both_unknown"],1)
        self.assertEqual(out["paired_scorable"],0)
        self.assertEqual(out["paired_net_a_only_minus_b_only"],0)

    def test_mismatched_same_timestamp_proxy_raises(self):
        r={"start":T0,"results":{
            "fresh_5m":{"departure":T0,"proxy_hit":True},
            "depart_now":{"departure":T0,"proxy_hit":False},
        }}
        with self.assertRaisesRegex(AssertionError,"inconsistent"):
            m.paired([r],"fresh_5m","depart_now")

    def test_end_to_end_readonly_audit_and_both_output_formats(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger=Path(tmp)/"sidecar.sqlite"
            stock=Path(tmp)/"collector.sqlite"
            with sqlite3.connect(ledger) as con:
                con.execute("""CREATE TABLE v42_candidate_decisions(
                    id INTEGER PRIMARY KEY,item_key TEXT,computed_at INTEGER,
                    model_family TEXT,model_config TEXT,stock_as_of INTEGER,
                    status TEXT,departure INTEGER,arrival INTEGER,
                    valid_until INTEGER,actual_player_departure INTEGER
                )""")
                samples=[
                    rec(T0+300,T0+4200),
                    rec(T0+600,T0+4200),
                    rec(T0+900,T0+4200),
                    rec(T0+1200,T0+18000),
                ]
                con.executemany("""INSERT INTO v42_candidate_decisions(
                    item_key,computed_at,model_family,model_config,stock_as_of,
                    status,departure,arrival,valid_until,
                    actual_player_departure)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    [tuple(row[k] for k in (
                        "item_key","computed_at","model_family","model_config",
                        "stock_as_of","status","departure","arrival",
                        "valid_until","actual_player_departure"
                    )) for row in samples])
                con.commit()
            with sqlite3.connect(stock) as con:
                con.execute("CREATE TABLE sanity(id INTEGER)")
                con.commit()
            def score(con,country,item,arrival,asof):
                # deterministic independent only of arrival time, not
                # of selection policy or later observations
                return ("POLL_STATE_PROXY_SUCCESS",True,{})
            report=m.audit(
                ledger=ledger,stock=stock,now=T0+30000,hours=12,
                keys=(RED,),scorer=score)
            self.assertEqual(report["hourly_starts"],1)
            self.assertEqual(report["overall"]["strategies"][
                "fresh_or_3stable"]["scheduled"],1)
            self.assertEqual(report["overall"]["strategies"][
                "fresh_5m"]["scheduled"],0)
            self.assertEqual(report["overall"]["strategies"][
                "fresh_or_3stable"]["proxy_hit"],1)
            self.assertEqual(report["overall"]["strategies"][
                "depart_now"]["proxy_hit"],1)
            self.assertTrue(report["commitment_not_currently_valid_under_5m_snapshot"])
            self.assertTrue(report["comparison_no_future_stock_used_for_choice"])
            real=m.audit
            def fixture(**opts):
                opts["now"]=T0+30000
                return real(ledger=ledger,stock=stock,
                            scorer=score,**opts)
            with (patch.object(m,"audit",side_effect=fixture),
                  patch.object(m,"approved_collector_source",return_value=True)):
                for as_json in (False,True):
                    argv=["v119","--hours","12","--items","redfox"]
                    if as_json:argv.append("--json")
                    output=io.StringIO()
                    with (patch.object(sys,"argv",argv),
                          contextlib.redirect_stdout(output)):
                        m.main()
                    if as_json:
                        out=json.loads(output.getvalue())
                        self.assertEqual(out["status"],
                            "V119_FIXED_ASOF_STABLE_COMMITMENT_VS_FRESH_REPLAY")
                    else:
                        self.assertIn("FROZEN 5M REPLAN",output.getvalue())


if __name__=="__main__":
    unittest.main()
