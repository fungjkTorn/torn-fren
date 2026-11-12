"""V122 tests: no model tuning, score binarity, matched value vs leave-now."""
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

from research import v122_nessie_selector_discrimination_audit as m

T0=1700000000


class DiscriminationAuditTests(unittest.TestCase):
    def test_binary_score_profile(self):
        profile=m.score_profile({
            "availability_score":np.array([0.,1.,1.,0.,1.])})
        self.assertEqual(profile["observed_score_values"],[0.,1.])
        self.assertEqual(profile["intermediate_probability_like_scores"],0)
        self.assertEqual(profile["known_positive"],3)

    def test_ambiguous_and_fractional_scores_are_explicit(self):
        profile=m.score_profile({
            "availability_score":np.array([0.,.5,1.])})
        self.assertEqual(profile["intermediate_probability_like_scores"],1)
        self.assertEqual(m.score_profile(None)["sampled_points"],0)
        with self.assertRaises(ValueError):
            m.score_profile({"availability_score":np.array([1.2])})

    def test_matched_scoring_does_not_reward_uncertain_arrivals(self):
        def item(i,dep1,dep0,h1,h0):
            return {"issue_epoch":i,"decisions":{
                "nearpeak_0.03":{"departure":dep1,"stocked":h1},
                "now":{"departure":dep0,"stocked":h0},
            }}
        cases=[
            item(T0,T0,T0,True,True),
            item(T0+3600,T0+4200,T0+3600,True,False),
            item(T0+7200,T0+7800,T0+7200,None,True),
            item(T0+10800,None,T0+10800,None,True),
        ]
        s=m.summarize(cases)
        self.assertEqual(s["starts"],4)
        self.assertEqual(s["identical_departure"],1)
        self.assertEqual(s["different_departure"],2)
        self.assertEqual(s["matched_scorable"],2)
        self.assertEqual(s["nearpeak_only"],1)
        self.assertEqual(s["unknown_in_pair"],1)
        self.assertEqual(s["not_both_departing"],1)

    def test_matured_cohort_and_cli(self):
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
                    stock_as_of INTEGER, status TEXT, valid_until INTEGER,
                    departure INTEGER,arrival INTEGER,
                    actual_player_departure INTEGER,
                    model_family TEXT,model_config TEXT
                )""")
                for q in (mature,immature):
                    db.execute("""INSERT INTO v42_candidate_decisions
                        (item_key,computed_at,stock_as_of,status,valid_until,
                         departure,arrival,actual_player_departure,
                         model_family,model_config)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",(
                        m.ITEM_KEY,q,q,"RESEARCH_PROPOSAL_ONLY",q+300,
                        q+1000,q+7360,0,"recent_phase_template","test"))
                db.commit()
            with sqlite3.connect(stock) as db:
                db.execute("CREATE TABLE sanity(x INTEGER)")
                db.commit()
            choice_calls=[]
            def choose(issue,model):
                choice_calls.append(issue)
                return ({
                    "champion":issue+3000,
                    "nearpeak_0.03":issue+300,
                    "nearpeak_0.08":issue+300,
                    "nearpeak_0.15":issue+300,
                    "floor_0.55":issue,
                    "now":issue,
                },3,2)
            def curve(model,issue):
                return {"availability_score":np.array([0.,1.,1.])}
            def scorer(conn,country,item,arrival,asof):
                if arrival==mature:
                    return ("POLL_STATE_PROXY_MISS",False,{})
                return ("POLL_STATE_PROXY_SUCCESS",True,{})
            report=m.audit(
                ledger=ledger,stock=stock,now=frozen,
                hours=24,model=object(),choose=choose,
                curve_at=curve,scorer=scorer)
            self.assertEqual(report["mature_eight_hour_starts"],1)
            self.assertEqual(report["pending_unmatured_starts"],1)
            self.assertEqual(choice_calls,[mature])
            self.assertEqual(report["score_curve_points"]["score_intermediate"],0)
            self.assertEqual(report["overall"]["different_departure"],1)
            self.assertEqual(report["three_nearpeak_variants_identical_starts"],1)
            self.assertEqual(len(report["all_different_departure_examples"]),1)
            original=m.audit
            def fixture(**kwargs):
                kwargs["now"]=frozen
                return original(
                    ledger=ledger,stock=stock,model=object(),
                    choose=choose,curve_at=curve,scorer=scorer,**kwargs)
            with (patch.object(m,"audit",side_effect=fixture),
                  patch.object(m,"approved_collector_source",return_value=True)):
                for use_json in (True,False):
                    argv=["v122","--hours","24"]
                    if use_json:argv.append("--json")
                    out=io.StringIO()
                    with (patch.object(sys,"argv",argv),
                          contextlib.redirect_stdout(out)):
                        m.main()
                    if use_json:
                        data=json.loads(out.getvalue())
                        self.assertEqual(
                            data["status"],
                            "V122_NESSIE_SELECTOR_DISCRIMINATION_VS_IMMEDIATE")
                    else:
                        self.assertIn("SELECTOR DISCRIMINATION",out.getvalue())


if __name__=="__main__":
    unittest.main()
