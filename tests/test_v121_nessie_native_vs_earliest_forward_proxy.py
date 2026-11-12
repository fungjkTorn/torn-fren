"""V121 causal Nessie midpoint vs V106 nearpeak proxy replay contract."""
import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from research import v121_nessie_native_vs_earliest_forward_proxy as m

T0=1700000000
N=m.ITEM_KEY


class FixtureModel:
    def __init__(self,origin):
        self.origin=origin

    def plan(self,q):
        return max(q,self.origin+600),.98


class ScoreCurveReplay(unittest.TestCase):
    def test_reuse_original_v106_early_risk_budget_and_champion(self):
        def curve(p,q):
            return {
                "delay_seconds":np.array([0,300,600,900],dtype=int),
                "availability_score":np.array([.94,.95,.99,.98],dtype=float),
            }
        start=T0+3600
        dep,ticks,queries=m.choose_all(
            start,FixtureModel(start),curve_fn=curve)
        self.assertEqual(dep["champion"],start+600)
        self.assertEqual(dep["nearpeak_0.15"],start)
        self.assertEqual(dep["floor_0.55"],start)
        self.assertEqual(dep["now"],start)
        self.assertLessEqual(queries,ticks)

    def test_proxy_is_called_after_selection_and_pending_is_not_hit(self):
        seen=[]
        def score(*args):
            seen.append(args)
            return ("POLL_STATE_PROXY_SUCCESS",True,{})
        start=T0
        plans={"champion":start+1200,"nearpeak_0.15":start,
               "now":start,"floor_0.55":None}
        out=m.evidence_only_after_selection(
            None,country="uni",item="Nessie Plushie",
            asof=start+6360+300,departures=plans,scorer=score)
        self.assertEqual(out["now"]["stocked"],True)
        self.assertEqual(out["champion"]["proxy_status"],"PENDING_ARRIVAL")
        self.assertEqual(out["floor_0.55"]["proxy_status"],"NO_DEPARTURE")
        self.assertEqual(len(seen),1)

    def test_unknown_matched_pair_remains_unknown(self):
        r={"start":T0,"results":{
            "champion":{"departure":T0+600,"stocked":None},
            "now":{"departure":T0,"stocked":False},
        }}
        pair=m.paired([r],"champion","now")
        self.assertEqual(pair["both_scorable"],0)
        self.assertEqual(pair["unknown_stock_in_pair"],1)
        self.assertEqual(pair["left_minus_right_known_discordant"],0)

    def test_same_departure_conflicting_stock_fails(self):
        r={"start":T0,"results":{
            "champion":{"departure":T0,"stocked":True},
            "now":{"departure":T0,"stocked":False},
        }}
        with self.assertRaisesRegex(AssertionError,"contradictory"):
            m.paired([r],"champion","now")

    def test_summary_explicit_zero_values_and_unscorable(self):
        r=[{
            "start":T0,
            "results":{
                "champion":{"departure":None,"stocked":None,
                            "proxy_status":"NO_DEPARTURE"},
                "now":{"departure":T0,"stocked":None,
                       "proxy_status":"PENDING_ARRIVAL"}
            }
        }]
        a=m.summarize(r,"champion")
        self.assertEqual(a["departures"],0)
        self.assertEqual(a["scorable_hits"],0)
        self.assertIsNone(a["proxy_hit_rate_when_scorable"])
        self.assertEqual(m.summarize(r,"now")["arrivals_pending"],1)

    def test_complete_asof_censoring_sql_and_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger=Path(tmp)/"private.sqlite"
            stock=Path(tmp)/"collector.sqlite"
            frozen=T0+100000
            mature=frozen-50000
            immature=frozen-2000
            with sqlite3.connect(ledger) as db:
                db.execute("""CREATE TABLE v42_candidate_decisions (
                    id INTEGER PRIMARY KEY,
                    item_key TEXT, computed_at INTEGER,
                    stock_as_of INTEGER,status TEXT,valid_until INTEGER,
                    departure INTEGER,arrival INTEGER,
                    actual_player_departure INTEGER,
                    model_family TEXT,model_config TEXT
                )""")
                db.executemany("""INSERT INTO v42_candidate_decisions
                    (item_key,computed_at,stock_as_of,status,valid_until,
                    departure,arrival,actual_player_departure,model_family,
                    model_config) VALUES (?,?,?,?,?,?,?,?,?,?)""",[
                    (N,mature,mature,"RESEARCH_PROPOSAL_ONLY",
                     mature+300,mature+7200,mature+7200+6360,0,
                     "recent_phase_template","test"),
                    (N,immature,immature,"RESEARCH_PROPOSAL_ONLY",
                     immature+300,immature+7200,immature+7200+6360,0,
                     "recent_phase_template","test"),
                    ("uni:Red Fox Plushie",mature,mature,
                     "RESEARCH_PROPOSAL_ONLY",mature+300,
                     mature+7200,mature+7200+6360,0,
                     "global_regime_analog","test"),
                ])
                db.commit()
            with sqlite3.connect(stock) as db:
                db.execute("CREATE TABLE sanity(x INTEGER)")
            called=[]
            def choice(start,model):
                called.append(start)
                return ({
                    "champion":start+1200,
                    "nearpeak_0.03":start+600,
                    "nearpeak_0.08":start+300,
                    "nearpeak_0.15":start,
                    "floor_0.55":None,
                    "now":start,
                },3,3)
            def scorer(*args):
                return "POLL_STATE_PROXY_SUCCESS",True,{}
            r=m.audit(
                ledger=ledger,stock=stock,now=frozen,hours=24,
                model=object(),choose=choice,scorer=scorer)
            self.assertEqual(r["frozen_v75_hourly_start_cohort"],2)
            self.assertEqual(r["complete_eight_hour_replay_starts"],1)
            self.assertEqual(r["starts_pending_complete_eight_hour_horizon"],1)
            self.assertEqual(called,[mature])
            self.assertEqual(r["policy_outcomes"]["champion"]["scorable_hits"],1)
            self.assertEqual(r["policy_outcomes"]["floor_0.55"]["no_departure"],1)
            self.assertTrue(r["recomputed_not_frozen_original_v75_predictions"])
            self.assertFalse(r["stock_source_provider_country_age_verified"])
            original=m.audit
            def fixture(**kwargs):
                kwargs["now"]=frozen
                return original(
                    ledger=ledger,stock=stock,
                    model=object(),choose=choice,scorer=scorer,
                    **kwargs)
            with (patch.object(m,"audit",side_effect=fixture),
                  patch.object(m,"approved_collector_source",return_value=True)):
                for jsonmode in (True,False):
                    argv=["v121","--hours","24","--max-starts","25"]
                    if jsonmode:argv.append("--json")
                    out=io.StringIO()
                    with (patch.object(sys,"argv",argv),
                          contextlib.redirect_stdout(out)):
                        m.main()
                    if jsonmode:
                        rep=json.loads(out.getvalue())
                        self.assertEqual(
                            rep["status"],
                            "V121_NESSIE_NATIVE_EARLIEST_SCORE_FORWARD_PROXY_REPLAY")
                    else:
                        self.assertIn(
                            "NESSIE NATIVE MIDPOINT VS EARLIEST",
                            out.getvalue())


if __name__=="__main__":
    unittest.main()
