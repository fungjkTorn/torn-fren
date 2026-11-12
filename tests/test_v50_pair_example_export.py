"""V50 source-examples exporter requires both experts to fully resolve."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from research import v50_pair_example_export as m
from research.v50_pair_selector_artifact import FEATURES

NOW=1800000000

class ExampleExportTests(unittest.TestCase):
    def test_reject_unresolved_expert_without_guessing_loss(self):
        class Planner:
            def __init__(self,*a,**kw):pass
            def plan(self,q):return (q+300,.6,.6)
        ctx=SimpleNamespace(timelines={("sou","Lion Plushie"):
                                        SimpleNamespace()})
        feats={k:1.0 for k in FEATURES["lion"]}
        outcomes=[
            {"status":"RESOLVED_EXPERT_DECISION","success":1,
             "resolved_at":NOW-100},
            {"status":"NO_RESOLVED_EXPERT_DECISION",
             "success":None,"resolved_at":None},
        ]
        with patch.object(m,"AnalogPlanner",Planner), \
             patch.object(m,"original_features",return_value=feats), \
             patch.object(m,"simulate_one",side_effect=outcomes):
            self.assertIsNone(m.resolved_example(ctx,"lion",NOW-100000,NOW))

    def test_both_outcomes_resolved_before_cutoff(self):
        class Planner:
            def __init__(self,*a,**kw):pass
            def plan(self,q):return (q+600,.5,.5)
        ctx=SimpleNamespace(timelines={("sou","Lion Plushie"):
                                        SimpleNamespace()})
        feats={k:1.0 for k in FEATURES["lion"]}
        outcomes=[
            {"status":"RESOLVED_EXPERT_DECISION","success":1,
             "resolved_at":NOW-100},
            {"status":"RESOLVED_EXPERT_DECISION","success":0,
             "resolved_at":NOW-20},
        ]
        with patch.object(m,"AnalogPlanner",Planner), \
             patch.object(m,"original_features",return_value=feats), \
             patch.object(m,"simulate_one",side_effect=outcomes):
            row=m.resolved_example(ctx,"lion",NOW-100000,NOW)
        self.assertEqual(row["resolved_at"],NOW-20)
        self.assertEqual(row["feature_as_of"],NOW-100000)
        self.assertEqual(row["a_success"],1)
        self.assertEqual(row["b_success"],0)
        self.assertEqual(row["normalization"],"per_decision_cutoff")

    def test_late_resolved_label_is_not_trained(self):
        class Planner:
            def __init__(self,*a,**kw):pass
            def plan(self,q):return (q+300,.5,.5)
        ctx=SimpleNamespace(timelines={("sou","Lion Plushie"):
                                        SimpleNamespace()})
        feats={k:1.0 for k in FEATURES["lion"]}
        outcomes=[
            {"status":"RESOLVED_EXPERT_DECISION","success":1,
             "resolved_at":NOW-100},
            {"status":"RESOLVED_EXPERT_DECISION","success":0,
             "resolved_at":NOW+1},
        ]
        with patch.object(m,"AnalogPlanner",Planner), \
             patch.object(m,"original_features",return_value=feats), \
             patch.object(m,"simulate_one",side_effect=outcomes):
            self.assertIsNone(m.resolved_example(ctx,"lion",NOW-100000,NOW))

if __name__=="__main__":
    unittest.main()
