"""V100: as-of departure reconfirmation cannot use future data."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research import v100_future_watch_reconfirmation_audit as m
from research.v38_prediction_store import open_writer
from research.plushie_champions.common import TRAVEL_SECONDS

NOW=1791650000
START=NOW-7200
D=NOW-3600


def fake(issue, departure, status="RESEARCH_PROPOSAL_ONLY", country="mex"):
    return {
        "item_key":country+":Fixture",
        "computed_at":issue,"stock_as_of":issue-10,
        "status":status,
        "valid_until":issue+300,
        "departure":departure,
        "arrival":departure+TRAVEL_SECONDS[country] if departure is not None else None,
        "actual_player_departure":0,
    }


class V100Tests(unittest.TestCase):
    def test_exact_and_near_departure_reconfirmation(self):
        o=fake(START,D)
        for late,expected,difference in [
            (fake(D-120,D),"EXACT_DEPARTURE_RECONFIRMED",0),
            (fake(D-120,D+160),"NEARBY_DEPARTURE_RECONFIRMED",160),
            (fake(D-120,D+700),"DIFFERENT_DEPARTURE_AT_RECHECK",700),
            (fake(D-120,None,"NO_RECOMMENDATION"),
             "RECHECK_ABSTAINED_OR_INVALID",None),
            (fake(D-500,D),"NO_RECENT_RECHECK",None),
        ]:
            result,delta=m.late_state(o,[o,late],[START,late["computed_at"]],NOW)
            self.assertEqual(result,expected)
            self.assertEqual(delta,difference)

    def test_future_original_is_not_misrepresented_as_confirmed(self):
        o=fake(NOW-200,NOW+600)
        result,_=m.late_state(o,[o],[NOW-200],NOW)
        self.assertEqual(result,"TARGET_DEPARTURE_NOT_REACHED")

    def test_same_snapshot_does_not_self_reconfirm(self):
        o=fake(START,D)
        state,_=m.late_state(o,[o],[START],NOW)
        self.assertEqual(state,"NO_LATER_RECHECK")

    def test_no_future_information_even_with_later_target(self):
        o=fake(START,D)
        after=fake(D+60,D+80)
        result,_=m.late_state(o,[o,after],[START,D+60],NOW)
        self.assertEqual(result,"NO_LATER_RECHECK")

    def test_recheck_invalid_or_expired_does_not_confirm(self):
        o=fake(START,D)
        late=fake(D-100,D)
        late["stock_as_of"]=D-100-400
        result,_=m.late_state(o,[o,late],[START,D-100],NOW)
        self.assertEqual(result,"RECHECK_ABSTAINED_OR_INVALID")

    def test_full_report_is_restricted_to_original_future_watches(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path=Path(temp.name)/"sidecar.db"
        with open_writer(path) as con:
            def issue(key,t,depart,status="RESEARCH_PROPOSAL_ONLY"):
                country=key.split(":")[0]
                con.execute(
                    """INSERT INTO v42_candidate_decisions(
                    item_key,computed_at,model_family,model_config,
                    stock_as_of,status,departure,arrival,
                    valid_until,actual_player_departure)
                    VALUES(?,?,'fixture','fixture',?,?,?,?,?,0)""",
                    (key,t,t-10,status,depart,
                     depart+TRAVEL_SECONDS[country] if depart is not None else None,
                     t+300))
            issue("mex:Jaguar Plushie",START,D)
            issue("mex:Jaguar Plushie",D-120,D)
            issue("can:Crocus",START,D)
            issue("can:Crocus",D-180,D+160)
            issue("cay:Banana Orchid",NOW-100,NOW+800)
            issue("arg:Ceibo Flower",START,D)
            issue("arg:Ceibo Flower",D-120,None,"NO_RECOMMENDATION")
            con.commit()
        result=m.audit(sidecar=path,days=1,asof=NOW)
        self.assertFalse(result["optional_stock_proxy"])
        self.assertEqual(result["future_watch_targets_reconfirmed"],2)
        self.assertEqual(result["categories"]["EXACT_DEPARTURE_RECONFIRMED"],1)
        self.assertEqual(result["categories"]["NEARBY_DEPARTURE_RECONFIRMED"],1)
        self.assertEqual(result["categories"]["RECHECK_ABSTAINED_OR_INVALID"],1)
        self.assertGreater(result["categories"]["TARGET_DEPARTURE_NOT_REACHED"],0)
        self.assertEqual(result["original_future_watch_targets"],5)
        self.assertEqual(result["future_watch_departures_reached"],4)
        self.assertTrue(result["sidecar_written"] is False)
        # Optional stock was disabled and nonexistent source must not be opened.
        self.assertEqual(result["stock_proxy_by_reconfirmation_status"],{})

    def test_recommended_departure_90_seconds_earlier_is_past(self):
        original=fake(START,D)
        update=fake(D-120,D-90)
        label,diff=m.late_state(original,[original,update],[START,D-120],NOW)
        self.assertEqual(label,"RECHECK_DEPARTURE_ALREADY_PASSED")
        self.assertEqual(diff,-90)

    def test_with_stock_proxy_option_counts_tuple_status_correctly(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            sidecar=Path(tmp)/"sidecar.db"
            stock=Path(tmp)/"collector.db"
            with open_writer(sidecar) as db:
                for issued in (START,D-120):
                    db.execute(
                        """INSERT INTO v42_candidate_decisions(
                         item_key,computed_at,model_family,model_config,
                         stock_as_of,status,departure,arrival,
                         valid_until,actual_player_departure)
                         VALUES(?,?,'fixture','fixture',?,
                         'RESEARCH_PROPOSAL_ONLY',?,?,?,0)""",
                         ("mex:Jaguar Plushie",issued,issued-10,
                          D,D+TRAVEL_SECONDS["mex"],issued+300))
                db.commit()
            sqlite3.connect(stock).close()
            with patch.object(m,"observation",
                              return_value=("POLL_STATE_PROXY_SUCCESS",True,{})):
                out=m.audit(sidecar=sidecar,source=stock,asof=NOW,
                            with_stock_proxy=True)
            self.assertEqual(
                out["stock_proxy_by_reconfirmation_status"][
                    "EXACT_DEPARTURE_RECONFIRMED"]["HIT"],1)
            self.assertTrue(out["optional_stock_proxy"])
            self.assertFalse(out["collector_written"])

    def test_missing_private_ledger_does_not_create_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing=Path(tmp)/"missing.db"
            with self.assertRaises((ValueError,OSError)):
                m.audit(sidecar=missing,asof=NOW)
            self.assertFalse(missing.exists())


if __name__=="__main__":
    unittest.main()
