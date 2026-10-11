"""V101 tests: as-of historical issue, actionable-window conversion."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research import v101_watch_to_actionable_audit as m
from research.v38_prediction_store import open_writer
from research.plushie_champions.common import TRAVEL_SECONDS

NOW=1791650000
ISSUED=NOW-7200
DEP=NOW-1800


def sample(item, issued, departure, status="RESEARCH_PROPOSAL_ONLY"):
    country=item.split(":",1)[0]
    return {
        "item_key":item,"computed_at":issued,"stock_as_of":issued-20,
        "status":status,"departure":departure,
        "arrival":None if departure is None else
                  departure+TRAVEL_SECONDS[country],
        "valid_until":issued+300,"actual_player_departure":0,
    }


class WatchConversionTests(unittest.TestCase):
    def test_a_short_earlier_replan_is_actionable_not_failed(self):
        old=sample("mex:Jaguar Plushie",ISSUED,DEP)
        new=sample("mex:Jaguar Plushie",DEP-180,DEP-120)
        matches=m.converted(old,[old,new],
                             [ISSUED,DEP-180])
        self.assertEqual(len(matches),1)
        self.assertEqual(matches[0][2],DEP-120)
        self.assertEqual(matches[0][3],DEP-180)
        self.assertEqual(matches[0][0],120)

    def test_later_replan_soon_enough_is_actionable(self):
        old=sample("mex:Jaguar Plushie",ISSUED,DEP)
        new=sample("mex:Jaguar Plushie",DEP-100,DEP+180)
        found=m.converted(old,[old,new],[ISSUED,DEP-100])
        self.assertEqual(found[0][2],DEP+180)

    def test_shift_10min_earlier_counts_only_broad_window(self):
        old=sample("can:Crocus",ISSUED,DEP)
        new=sample("can:Crocus",DEP-660,DEP-600)
        self.assertEqual(m.converted(old,[old,new],[ISSUED,DEP-660],
                          max_shift=300),[])
        self.assertEqual(len(m.converted(old,[old,new],
                         [ISSUED,DEP-660],max_shift=900)),1)

    def test_non_actionable_long_term_repeat_does_not_convert(self):
        old=sample("mex:Jaguar Plushie",ISSUED,DEP)
        new=sample("mex:Jaguar Plushie",DEP-120,DEP+1200)
        self.assertEqual(m.converted(old,[old,new],[ISSUED,DEP-120]),[])

    def test_do_not_look_at_updates_issued_after_original_departure(self):
        old=sample("mex:Jaguar Plushie",ISSUED,DEP)
        new=sample("mex:Jaguar Plushie",DEP+60,DEP+90)
        self.assertEqual(m.converted(old,[old,new],[ISSUED,DEP+60]),[])

    def test_invalid_or_abstaining_snapshot_does_not_convert(self):
        old=sample("mex:Jaguar Plushie",ISSUED,DEP)
        invalid=sample("mex:Jaguar Plushie",DEP-120,None,"EXPERT_ABSTAINED")
        self.assertEqual(m.converted(
            old,[old,invalid],[ISSUED,DEP-120]),[])

    def test_full_read_only_report_shows_rescue_of_earlier_leave(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"sidecar.db"
            with open_writer(path) as con:
                def insert(row):
                    con.execute(
                        """INSERT INTO v42_candidate_decisions(
                          item_key,computed_at,model_family,model_config,
                          stock_as_of,status,departure,arrival,valid_until,
                          actual_player_departure)
                          VALUES(?,?,'test','test',?,?,?,?,?,0)""",
                        (row["item_key"],row["computed_at"],
                         row["stock_as_of"],row["status"],
                         row["departure"],row["arrival"],
                         row["valid_until"]))
                insert(sample("mex:Jaguar Plushie",ISSUED,DEP))
                insert(sample("mex:Jaguar Plushie",DEP-180,DEP-120))
                insert(sample("can:Crocus",ISSUED,DEP))
                insert(sample("can:Crocus",DEP-660,DEP-600))
                insert(sample("cay:Banana Orchid",ISSUED,NOW+600))
                insert(sample("arg:Ceibo Flower",ISSUED,DEP))
                insert(sample("arg:Ceibo Flower",DEP-180,None,"NO_RECOMMENDATION"))
                con.commit()
            r=m.audit(sidecar=path,asof=NOW,days=1)
            p=r["overall"]
            self.assertEqual(p["original_future_targets"],4)
            self.assertEqual(p["reached"],3)
            self.assertEqual(p["unreached"],1)
            self.assertEqual(p["converted_within_5m"],1)
            self.assertEqual(p["converted_within_15m"],2)
            self.assertEqual(p["best_earlier"],2)
            self.assertEqual(p["not_converted_within_15m"],1)
            self.assertEqual(r["distinct_later_actionable_candidate_instances_selected"],2)
            self.assertFalse(r["stock_data_read"])
            self.assertFalse(r["sidecar_written"])
            self.assertFalse(r["live_system_modified"])

    def test_nonexistent_sidecar_not_created(self):
        with tempfile.TemporaryDirectory() as d:
            missing=Path(d)/"private.db"
            with self.assertRaises((OSError,ValueError)):
                m.audit(sidecar=missing,asof=NOW)
            self.assertFalse(missing.exists())


if __name__=="__main__":
    unittest.main()
