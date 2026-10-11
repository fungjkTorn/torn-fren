"""V103 compare curves directly against untouched champion planner decisions."""
import types
import unittest

import numpy as np

from research.plushie_champions.common import AnalogPlanner,TemplatePlanner,MAX_WAIT,STEP
from research.v103_champion_score_curves import (
    analog_scores,template_scores,analog_champion_from_curve,
    template_champion_from_curve,earliest_from_curve
)

Q=1800000


class FakeTimeline:
    def success_many(self, times):
        times=np.asarray(times,float)
        return ((times%7200>=1800)&(times%7200<4800)).astype(float)


class ChampionCurveTests(unittest.TestCase):
    def analog(self):
        m=object.__new__(AnalogPlanner)
        grid=np.arange(Q-7200,Q+1800,STEP,dtype=float)
        m.ctx=types.SimpleNamespace(
            grid=grid,active=np.ones((1,len(grid)),float))
        m.k=4
        m.target_i=0
        m.maxfuture=1800
        m.Z=np.column_stack([
            np.sin(grid/900),np.cos(grid/1800),grid/1e6])
        m.weights=np.ones(3)
        m.path_ok=np.ones(len(grid),bool)
        m.delays=np.arange(0,MAX_WAIT+1,STEP,float)
        m.travel=1020
        m.tl=FakeTimeline()
        m.cache={}
        return m

    def template(self):
        m=object.__new__(TemplatePlanner)
        m.lags=(1,2)
        m.minfit=.6
        m.travel=1020
        m.shift_range=3600
        m.cache={}
        m._best_ref=lambda q,d:(.85,0,.75) if d==1 else (.7,300,.7)
        m._state=lambda t:bool(1800<=(int(t)%7200)<4800)
        return m

    def test_analog_original_champion_choice_is_unchanged(self):
        model=self.analog()
        scores=analog_scores(model,Q)
        chosen=model.plan(Q)
        rebuilt=analog_champion_from_curve(Q,scores)
        self.assertEqual(chosen[0],rebuilt[0])
        self.assertAlmostEqual(chosen[1],rebuilt[1],12)
        self.assertAlmostEqual(chosen[2],rebuilt[2],12)
        self.assertEqual(len(scores["delay_seconds"]),MAX_WAIT//STEP+1)

    def test_template_original_champion_choice_is_unchanged(self):
        model=self.template()
        scores=template_scores(model,Q)
        chosen=model.plan(Q)
        rebuilt=template_champion_from_curve(Q,scores)
        self.assertEqual(chosen[0],rebuilt[0])
        self.assertAlmostEqual(chosen[1],rebuilt[1],12)
        self.assertTrue(scores["eligible_reference_patterns"])

    def test_earliest_can_precede_champion_peak_without_rescoring(self):
        model=self.analog()
        curves=analog_scores(model,Q)
        champ=analog_champion_from_curve(Q,curves)
        earliest=earliest_from_curve(Q,curves,floor=.3)
        self.assertIsNotNone(earliest)
        self.assertLessEqual(earliest[0],champ[0])
        self.assertGreaterEqual(earliest[1],.3)

    def test_model_score_threshold_can_abstain(self):
        c={"delay_seconds":np.array([0,300,600]),
           "availability_score":np.array([.2,.3,.4])}
        self.assertIsNone(earliest_from_curve(Q,c,floor=.65))

    def test_contiguous_requirement_skips_isolated_first_peak(self):
        c={"delay_seconds":np.array([0,300,600,900,1200]),
           "availability_score":np.array([.8,.1,.65,.7,.8])}
        z=earliest_from_curve(Q,c,floor=.6,min_consecutive_points=2)
        self.assertEqual(z[0],Q+600)

    def test_gap_between_arrivals_is_not_a_contiguous_window(self):
        c={"delay_seconds":np.array([0,600,900]),
           "availability_score":np.array([.7,.7,.7])}
        z=earliest_from_curve(Q,c,floor=.65,min_consecutive_points=2)
        self.assertEqual(z[0],Q+600)

    def test_template_no_matching_patterns_abstains_for_earliest(self):
        m=self.template()
        m._best_ref=lambda q,d:(.1,0,.1)
        curve=template_scores(m,Q)
        self.assertEqual(len(curve["delay_seconds"]),0)
        self.assertIsNone(earliest_from_curve(Q,curve,floor=.45))
        self.assertEqual(template_champion_from_curve(Q,curve),(Q,.5))

    def test_template_uses_only_past_reference_timestamps(self):
        m=self.template()
        seen=[]
        def history(t):
            self.assertLess(t,Q)
            seen.append(t)
            return True
        m._state=history
        z=template_scores(m,Q)
        self.assertEqual(len(z["delay_seconds"]),MAX_WAIT//STEP+1)
        self.assertGreater(len(seen),1)

    def test_invalid_thresholds_rejected(self):
        model=self.analog()
        curve=analog_scores(model,Q)
        for floor in (float("nan"),-1,2,True):
            with self.assertRaises(ValueError):
                earliest_from_curve(Q,curve,floor=floor)


if __name__=="__main__":
    unittest.main()
