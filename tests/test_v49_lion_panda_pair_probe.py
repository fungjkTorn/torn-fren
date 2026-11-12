"""V49 Lion/Panda original source pair and feature contract regression."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

import numpy as np

from research import v49_lion_panda_pair_probe as m


HERE=Path(__file__).resolve().parents[1]/"research"/"plushie_champions"
NOW=1800000000
FEATURES={
 "g2":600,"g6":600,"g18":600,"rL":600,
 "B_prob":.7,"A_prob":.4,"B_rob":.6,"A_rob":.2
}


def source_configs(filename):
    tree=ast.parse((HERE/filename).read_text())
    out={}
    for node in tree.body:
        if isinstance(node,ast.Assign) and len(node.targets)==1:
            name=node.targets[0]
            if isinstance(name,ast.Name) and name.id in ("EXPERT_A","EXPERT_B"):
                out[name.id]=ast.literal_eval(node.value)
    return out


class V49PairProbeTests(unittest.TestCase):
    def test_exact_source_pinned_expert_configs(self):
        for target,filename in [
            ("lion","lion_pair_selector_ml.py"),
            ("panda","panda_pair_selector_ml.py"),
        ]:
            with self.subTest(target=target):
                frozen=source_configs(filename)
                live=m.TARGETS[target]
                self.assertEqual(live["expert_a"],
                    (frozen["EXPERT_A"]["k"],
                     frozen["EXPERT_A"]["global_regime_weight"]))
                self.assertEqual(live["expert_b"],
                    (frozen["EXPERT_B"]["k"],
                     frozen["EXPERT_B"]["global_regime_weight"]))

    def test_original_panda_selector_feature_order_and_values(self):
        with patch.object(m,"selector_feature_dict",
                          return_value=dict(FEATURES)):
            d=m.original_features(None,"chi","Panda Plushie",NOW,
                                  None,None,"panda")
        self.assertEqual(list(d)[-5:],
            ["g2_g6","g6_g18raw","rL_g18raw","prob_gap","rob_gap"])
        self.assertAlmostEqual(d["prob_gap"],.3)
        self.assertAlmostEqual(d["rob_gap"],.4)
        self.assertEqual(d["g2_g6"],1.0)

    def test_lion_uses_no_extra_panda_features(self):
        with patch.object(m,"selector_feature_dict",
                          return_value=dict(FEATURES)):
            d=m.original_features(None,"sou","Lion Plushie",NOW,
                                  None,None,"lion")
        self.assertEqual(d,FEATURES)

    def test_no_selector_weights_means_no_promoted_recommendation(self):
        con=Mock()
        ctx=SimpleNamespace(grid=np.array([NOW],float),con=con)
        pairs=[]
        class Planner:
            def __init__(self,context,country,item,*,k,global_weight,cutoff):
                pairs.append((k,global_weight,cutoff))
            def plan(self,q):
                return (float(NOW+900),.66,.63)
        with patch.object(m,"selector_feature_dict",
                          return_value=dict(FEATURES)):
            res=m.infer("fake","lion",NOW,
                        source_checker=lambda db,now:{"status":"FRESH"},
                        context_builder=lambda *a,**kw:ctx,
                        planner_class=Planner)
        self.assertEqual(res["status"],"SELECTOR_WEIGHTS_MISSING_NOT_PUBLISHED")
        self.assertFalse(res["published_to_website"])
        self.assertEqual(res["quantity_threshold"],30)
        self.assertEqual(res["grace_seconds"],10)
        self.assertEqual(res["replan_step_seconds"],300)
        self.assertEqual(pairs,[(14,.35,NOW),(18,.5,NOW)])
        con.close.assert_called_once()

    def test_stale_source_rejected_without_loading_db(self):
        build=Mock(side_effect=AssertionError("context must not load"))
        result=m.infer("fake","panda",NOW,
              source_checker=lambda db,now:{"status":"COLLECTOR_STALE"},
              context_builder=build)
        self.assertEqual(result["status"],"COLLECTOR_STALE")
        build.assert_not_called()

    def test_nonfinite_features_cannot_publish(self):
        con=Mock()
        ctx=SimpleNamespace(grid=np.array([NOW],float),con=con)
        class Planner:
            def __init__(self,*a,**k):pass
            def plan(self,q):return (float(NOW+600),.5,.5)
        with patch.object(m,"selector_feature_dict",
                          return_value={**FEATURES,"bad":float("nan")}):
            res=m.infer("fake","panda",NOW,
                        source_checker=lambda *a:{"status":"FRESH"},
                        context_builder=lambda *a,**kw:ctx,
                        planner_class=Planner)
        self.assertEqual(res["status"],"NONFINITE_FEATURES_REJECTED")
        con.close.assert_called_once()


if __name__=="__main__":
    unittest.main()
