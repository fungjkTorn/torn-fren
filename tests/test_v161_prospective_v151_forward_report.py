"""V161 forward report only scores before-the-fact frozen V160 issuance."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.plushie_champions.common import TRAVEL_SECONDS
from research.v160_prospective_v151_shadow import capture_once
from research.v161_prospective_v151_forward_report import score
from test_v160_prospective_v151_shadow import T,model,collector_fixture


class ForwardEvidenceTests(unittest.TestCase):
    def make_ledger(self, root):
        source=collector_fixture(root)
        dest=root/"v160_v151_prospective24.db"
        with patch("research.v160_prospective_v151_shadow.stable_earliest_departure",
                   side_effect=model):
            capture_once(source=source,destination=dest,
                         canonical=False,record=True,issued_epoch=T,
                         now_fn=lambda:T,mono_fn=lambda:10,scenarios=8)
        return source,dest

    def test_24_strictly_prospective_head_to_head_plus_now(self):
        with tempfile.TemporaryDirectory() as tmp:
            source,ledger=self.make_ledger(Path(tmp))
            def scorer(con,country,item,arrival,asof):
                base=T+TRAVEL_SECONDS[country]
                return ("BRACKET",arrival==base+600,{})
            result=score(
                collector=source,ledger=ledger,now=T+86400,
                days=2,scorer=scorer)
            self.assertEqual(result["issued_item_hours"],24)
            self.assertEqual(result["recorded_five_minute_item_rows"],24)
            self.assertEqual(result["paired_minus_independent_matched_net"],24)
            self.assertEqual(result["totals"]["paired_matched_independent"],24)
            self.assertEqual(result["totals"]["paired_only_hit"],24)
            self.assertEqual(result["totals"]["independent_only_hit"],0)
            self.assertEqual(result["totals"]["paired_complete_hit"],24)
            self.assertEqual(result["totals"]["independent_miss"],24)
            self.assertEqual(result["totals"]["leave_now_miss"],24)
            self.assertEqual(result["totals"]["paired_complete_future_unreconfirmed"],24)
            self.assertFalse(result["historically_reconstructed_issues"])
            self.assertFalse(result["specialist_predictions_scored"])
            self.assertFalse(result["actual_player_flights_verified"])
            self.assertTrue(result["only_mature_observations_used_for_scoring"])
            from research.v128_full24_earliest_shadow import exact_roster
            roster=exact_roster()
            self.assertEqual(set(result["items"]),set(roster))
            for key,metadata in roster.items():
                row=result["items"][key]
                self.assertEqual(row["incumbent_model_family"],
                                 metadata["incumbent_model_family"])
                self.assertEqual(row["incumbent_source_verified"],
                                 metadata["incumbent_source_verified"])
                self.assertEqual(row["forward_evidence_status"],
                                 "MATURE_POLL_PROXY_COMPARISONS_ONLY")
                self.assertEqual(row["incumbent_forward_evidence_status"],
                                 "NO_MATCHED_REAL_V75_FORECAST")
                self.assertFalse(row["model_promotion_authorized"])

    def test_pending_and_unknown_are_not_falsely_counted_as_misses(self):
        with tempfile.TemporaryDirectory() as tmp:
            source,ledger=self.make_ledger(Path(tmp))
            def scorer(con,country,item,arrival,asof):
                return ("PENDING",None,{})
            result=score(
                collector=source,ledger=ledger,now=T+86400,
                days=2,scorer=scorer)
            self.assertEqual(result["totals"]["independent_pending"],24)
            self.assertEqual(result["totals"]["paired_complete_pending"],24)
            self.assertEqual(result["totals"]["leave_now_pending"],24)
            self.assertEqual(result["totals"]["independent_unknown"],0)
            self.assertEqual(result["totals"]["paired_complete_unknown"],0)
            self.assertEqual(result["totals"]["paired_matched_independent"],0)
            self.assertEqual(result["totals"]["paired_only_hit"],0)
            self.assertEqual(result["totals"]["paired_complete_miss"],0)
            self.assertEqual(
                result["items"]["arg:Monkey Plushie"]["forward_evidence_status"],
                "NO_MATURE_MATCHED_MODEL_COMPARISONS")

    def test_mature_unobservable_stock_is_unknown_not_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            source,ledger=self.make_ledger(Path(tmp))
            result=score(
                collector=source,ledger=ledger,now=T+86400,days=2,
                scorer=lambda *args:("NO_POLL_BRACKET",None,{}))
            self.assertEqual(result["totals"]["independent_unknown"],24)
            self.assertEqual(result["totals"]["paired_complete_unknown"],24)
            self.assertEqual(result["totals"]["leave_now_unknown"],24)
            self.assertEqual(result["totals"]["independent_pending"],0)
            self.assertEqual(result["totals"]["paired_complete_pending"],0)
            self.assertEqual(result["totals"]["paired_matched_independent"],0)

    def test_watch_not_yet_due_is_pending_reconfirmation_not_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            source,ledger=self.make_ledger(Path(tmp))
            report=score(
                collector=source,ledger=ledger,now=T+300,days=2,
                scorer=lambda *args:("PENDING",None,{}))
            self.assertEqual(report["totals"]["paired_complete_future_reconfirmation_pending"],24)
            self.assertEqual(report["totals"]["paired_complete_future_unreconfirmed"],0)
            self.assertEqual(report["totals"]["paired_complete_future_reconfirmed"],0)
            self.assertEqual(report["totals"]["paired_complete_pending"],24)

    def test_true_v75_near_issue_specialist_is_scored_only_if_prior_and_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source,ledger=self.make_ledger(root)
            v75=root/"v75_private_predictions.db"
            from research.v128_full24_earliest_shadow import exact_roster
            items=sorted(exact_roster())
            with sqlite3.connect(v75) as db:
                db.execute(
                    "CREATE TABLE v42_candidate_decisions("
                    "item_key TEXT,computed_at INTEGER,stock_as_of INTEGER,"
                    "status TEXT,valid_until INTEGER,departure INTEGER,"
                    "arrival INTEGER,actual_player_departure INTEGER)")
                for key in items:
                    country=key.split(":",1)[0]
                    flight=TRAVEL_SECONDS[country]
                    db.execute("INSERT INTO v42_candidate_decisions VALUES(?,?,?,?,?,?,?,?)",
                        (key,T-60,T-80,"RESEARCH_PROPOSAL_ONLY",T+240,
                         T+900,T+900+flight,0))
            def scorer(con,country,item,arrival,asof):
                base=T+TRAVEL_SECONDS[country]
                return ("BRACKET",arrival in (base+600,base+900),{})
            report=score(collector=source,ledger=ledger,v75=v75,
                         now=T+86400,days=2,scorer=scorer)
            self.assertEqual(report["totals"]["v75_near_issued_proposals"],24)
            self.assertEqual(report["totals"]["paired_complete_matched_v75"],24)
            self.assertEqual(report["v75_matched_pair_net_paired_minus_v75"],0)
            self.assertTrue(report["specialist_predictions_scored"])
            self.assertIn("<=180s prior",report["v75_alignment"])
            with sqlite3.connect(v75) as db:
                db.execute("UPDATE v42_candidate_decisions SET computed_at=?",
                           (T+50,))
            future=score(collector=source,ledger=ledger,v75=v75,
                         now=T+86400,days=2,scorer=scorer)
            self.assertEqual(
                future["totals"].get("v75_near_issued_proposals",0),0)
            self.assertFalse(future["specialist_predictions_scored"])

    def test_absent_v75_is_reported_not_invented(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source,ledger=self.make_ledger(root)
            report=score(collector=source,ledger=ledger,
                         v75=root/"absent_v75.db",
                         now=T+86400,days=2,
                         scorer=lambda *args:("PENDING",None,{}))
            self.assertEqual(report["v75_private_specialist_source_status"],
                             "ABSENT")
            self.assertEqual(report["totals"].get("v75_near_issued_proposals",0),0)
            self.assertFalse(report["specialist_predictions_scored"])

    def test_written_decision_mutation_fails_integrity_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            source,ledger=self.make_ledger(Path(tmp))
            with sqlite3.connect(ledger) as con:
                item,raw=con.execute(
                    "SELECT item_key,payload_json FROM v160_issued LIMIT 1"
                ).fetchone()
                value=json.loads(raw)
                value["models"]["paired_complete"]["arrival_epoch"]+=10
                con.execute("UPDATE v160_issued SET payload_json=? WHERE item_key=?",
                            (json.dumps(value),item))
            with self.assertRaisesRegex(ValueError,"travel time or wait"):
                score(collector=source,ledger=ledger,now=T+86400,days=2,
                      scorer=lambda *args:("KNOWN",True,{}))

    def test_unissued_items_and_missing_ledger_cannot_be_reconstructed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=collector_fixture(root)
            with self.assertRaises(FileNotFoundError):
                score(collector=source,
                      ledger=root/"v160_v151_prospective24.db",
                      now=T+86400,days=2)

    def test_report_uses_first_issued_utc_hour_not_all_five_minute_ticks(self):
        with tempfile.TemporaryDirectory() as tmp:
            source,ledger=self.make_ledger(Path(tmp))
            with sqlite3.connect(ledger) as con:
                originals=con.execute(
                    "SELECT item_key,payload_json FROM v160_issued").fetchall()
                for item,raw in originals:
                    value=json.loads(raw)
                    value["issued_epoch"]=T+300
                    for variant in value["models"].values():
                        if variant["departure_epoch"] is not None:
                            variant["departure_epoch"]+=300
                            variant["arrival_epoch"]+=300
                    con.execute("INSERT INTO v160_issued VALUES(?,?,?,?)",
                                (item,T+300,value["policy_id"],
                                 json.dumps(value)))
            res=score(collector=source,ledger=ledger,now=T+86400,
                      days=2,scorer=lambda *args:("PENDING",None,{}))
            self.assertEqual(res["recorded_five_minute_item_rows"],48)
            self.assertEqual(res["issued_item_hours"],24)


if __name__=="__main__":
    unittest.main()
