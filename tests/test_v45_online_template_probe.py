"""Source-pinned online template replay smoke checks."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch

from research import v45_online_template_probe as p


class OnlineTemplateProbeTests(unittest.TestCase):
    def test_exact_experts_and_windows(self):
        self.assertEqual(len(p.EXPERTS),24)
        self.assertEqual(p.EXPERTS[0],((1,),7200,3600))
        self.assertEqual(p.EXPERTS[-1],((1,2,7),14400,7200))
        self.assertEqual(p.TARGETS["monkey"],("arg","Monkey Plushie",2))
        self.assertEqual(p.TARGETS["chamois"],("swi","Chamois Plushie",3))

    def test_past_replanning_retains_valid_schedule(self):
        def plan(q):
            return (1600.0,.6,{}) if q==1000.0 else None
        tl=SimpleNamespace(success=Mock(return_value=True))
        r=p.simulate_one(plan,tl,1000,6660)
        self.assertEqual(r["departure"],1600)
        self.assertEqual(r["resolved_at"],8270)
        self.assertEqual(r["success"],1)
        tl.success.assert_called_once_with(8260,10)

    def test_no_schedule_is_not_a_failure(self):
        tl=SimpleNamespace(success=Mock())
        r=p.simulate_one(lambda q:None,tl,0,6960)
        self.assertEqual(r["status"],"NO_RESOLVED_EXPERT_DECISION")
        self.assertIsNone(r["success"])
        tl.success.assert_not_called()

    def test_anchor_must_be_fully_resolved(self):
        now=1800000000
        tl=SimpleNamespace(ts=[now-10*p.DAY,now-600],
                           vals=lambda x:([1.],None,None))
        with patch.object(p,"gap_overlap",return_value=False):
            s=p.latest_fully_resolved_start(tl,[],[],"arg",now)
        self.assertIsNotNone(s)
        self.assertLessEqual(s+p.MAX_WAIT+p.TRAVEL_SECONDS["arg"]+p.GRACE,now)
        self.assertEqual(s%1800,0)

    def test_reject_unsupported_before_reading_source(self):
        with patch.object(p,"inspect_live_source") as source:
            with self.assertRaises(ValueError):
                p.probe("/no/db","japan",0,1800000000)
            source.assert_not_called()

    def test_stale_collector_abstains(self):
        with patch.object(p,"inspect_live_source",return_value={"status":"STALE"}):
            with patch.object(p,"connect") as con:
                r=p.probe("/no/db","monkey",0,1800000000)
                self.assertEqual(r["status"],"STALE")
                con.assert_not_called()

if __name__=="__main__":
    unittest.main()
