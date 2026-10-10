"""V54 must resume exact frozen snapshots and never duplicate/lose evidence."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

from research import v54_pair_resume_export as m


NOW=1800000000

class V54OfflineResumeTests(unittest.TestCase):
    def fixtures(self,tmp):
        db=Path(tmp)/"frozen.db"
        db.write_bytes(b"frozen immutable bytes"+b"_"*5100)
        cache=Path(tmp)/"progress.db"
        output=Path(tmp)/"examples.jsonl"
        ctx=SimpleNamespace(con=Mock())
        return db,cache,output,ctx

    def test_partial_resume_does_not_repeat_existing_anchors(self):
        with tempfile.TemporaryDirectory() as td:
            db,cache,output,ctx=self.fixtures(td)
            anchors=[100000+i*1800 for i in range(5)]
            seen=[]
            def process(context,target,s,cutoff):
                seen.append(s)
                return {
                    "key":"sou:Lion Plushie","decision_ts":s,
                    "resolved_at":s+600,"research_only":True,
                    "feature_as_of":s,"a_success":0,"b_success":1,
                    "source":"SOURCE_PINNED_CAUSAL_ANALOG_EXPERTS",
                    "normalization":"per_decision_cutoff","features":{},
                }
            with patch.object(m,"eligible_anchors",return_value=anchors):
                one=m.run(db,cache,output,"lion",NOW,last_starts=30,
                          max_new=2,builder=lambda *a,**k:ctx,
                          processor=process)
                two=m.run(db,cache,output,"lion",NOW,last_starts=30,
                          max_new=2,builder=lambda *a,**k:ctx,
                          processor=process)
                three=m.run(db,cache,output,"lion",NOW,last_starts=30,
                            max_new=2,builder=lambda *a,**k:ctx,
                            processor=process)
                four=m.run(db,cache,output,"lion",NOW,last_starts=30,
                            max_new=2,builder=lambda *a,**k:ctx,
                            processor=process)
            self.assertEqual(one["processed_anchors"],2)
            self.assertEqual(two["processed_anchors"],4)
            self.assertEqual(three["processed_anchors"],5)
            self.assertEqual(three["status"],"OFFLINE_EXPORT_COMPLETE")
            self.assertEqual(four["batch_decisions"],0)
            self.assertEqual(seen,anchors)
            exported=[json.loads(x) for x in output.read_text().splitlines()]
            self.assertEqual([x["decision_ts"] for x in exported],anchors)
            with sqlite3.connect(cache) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM v54_history").fetchone()[0],5)

    def test_no_schedule_outcome_is_remembered_and_not_training_label(self):
        with tempfile.TemporaryDirectory() as td:
            db,cache,output,ctx=self.fixtures(td)
            with patch.object(m,"eligible_anchors",return_value=[100000]):
                a=m.run(db,cache,output,"lion",NOW,last_starts=20,
                        builder=lambda *a,**k:ctx,processor=lambda *a:None)
                b=m.run(db,cache,output,"lion",NOW,last_starts=20,
                        builder=lambda *a,**k:ctx,
                        processor=Mock(side_effect=AssertionError("double replay")))
            self.assertEqual(a["status"],"OFFLINE_EXPORT_COMPLETE")
            self.assertEqual(a["resolved_examples_exported"],0)
            self.assertEqual(b["batch_decisions"],0)
            self.assertEqual(output.read_text(),"")
            with sqlite3.connect(cache) as conn:
                self.assertEqual(conn.execute(
                    "SELECT status FROM v54_history").fetchone()[0],"ABSTAINED")

    def test_snapshot_mutation_invalidates_resumability(self):
        with tempfile.TemporaryDirectory() as td:
            db,cache,output,ctx=self.fixtures(td)
            with patch.object(m,"eligible_anchors",return_value=[100000]):
                m.run(db,cache,output,"lion",NOW,last_starts=20,
                      builder=lambda *a,**k:ctx,processor=lambda *a:None)
                db.write_bytes(b"changed immutable data"+b"-"*5100)
                with self.assertRaisesRegex(ValueError,"SOURCE_OR_CUTOFF_CHANGED"):
                    m.run(db,cache,output,"lion",NOW,last_starts=20,
                          builder=lambda *a,**k:ctx,processor=lambda *a:None)

    def test_target_or_train_cutoff_change_refuses_to_mix(self):
        with tempfile.TemporaryDirectory() as td:
            db,cache,output,ctx=self.fixtures(td)
            with patch.object(m,"eligible_anchors",return_value=[100000]):
                m.run(db,cache,output,"lion",NOW,last_starts=20,
                      builder=lambda *a,**k:ctx,processor=lambda *a:None)
                with self.assertRaisesRegex(ValueError,"SOURCE_OR_CUTOFF_CHANGED"):
                    m.run(db,cache,output,"panda",NOW,last_starts=20,
                          builder=lambda *a,**k:ctx,processor=lambda *a:None)
                with self.assertRaisesRegex(ValueError,"SOURCE_OR_CUTOFF_CHANGED"):
                    m.run(db,cache,output,"lion",NOW+3600,last_starts=20,
                          builder=lambda *a,**k:ctx,processor=lambda *a:None)

    def test_reject_mismatched_or_unresolved_export_record(self):
        with tempfile.TemporaryDirectory() as td:
            db,cache,output,ctx=self.fixtures(td)
            with patch.object(m,"eligible_anchors",return_value=[100000]):
                with self.assertRaisesRegex(ValueError,"noncausal"):
                    m.run(db,cache,output,"lion",NOW,last_starts=20,
                          builder=lambda *a,**k:ctx,
                          processor=lambda *a:{
                              "key":"sou:Lion Plushie",
                              "decision_ts":100000,
                              "resolved_at":NOW+500,
                              "research_only":True
                          })
            with sqlite3.connect(cache) as conn:
                self.assertEqual(conn.execute(
                    "SELECT COUNT(*) FROM v54_history").fetchone()[0],0)

    def test_no_effect_on_a_stock_history_database(self):
        with tempfile.TemporaryDirectory() as td:
            db,cache,output,ctx=self.fixtures(td)
            old=db.read_bytes()
            with patch.object(m,"eligible_anchors",return_value=[100000]):
                m.run(db,cache,output,"lion",NOW,last_starts=20,
                      builder=lambda *a,**k:ctx,processor=lambda *a:None)
            self.assertEqual(db.read_bytes(),old)


if __name__=="__main__":
    unittest.main()
