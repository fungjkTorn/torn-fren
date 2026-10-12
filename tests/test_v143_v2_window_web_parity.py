"""Research-branch V2 graph/server departure guard parity, not a VM deploy."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path
from web.app import _latest_safe_leave_timestamp, _roll_prediction_to_now

ROOT=Path(__file__).resolve().parents[1]
HTML=ROOT/"web/static/index.html"
NOW=1791800000

def prediction(**updates):
    p=dict(prediction_number=1,estimate_timestamp=NOW+7200,
           window_end_timestamp=NOW+7800,
           recommended_arrival_timestamp=NOW+8100,
           target_depletion_timestamp=NOW+10000,
           expected_stock_lifetime_seconds=3600,travel_seconds=1620,
           usable_for_departure=True)
    p.update(updates)
    return p

class OriginalV2DepartureParityTests(unittest.TestCase):
    def test_server_valid_feasible_window(self):
        self.assertEqual(_latest_safe_leave_timestamp(prediction()),NOW+8080)
    def test_negative_window_not_rewritten_into_point(self):
        self.assertIsNone(_latest_safe_leave_timestamp(
            prediction(target_depletion_timestamp=NOW+8000)))
        self.assertIsNone(_latest_safe_leave_timestamp(
            prediction(target_depletion_timestamp=NOW+8400)))
    def test_unknown_depletion_fails_closed(self):
        self.assertIsNone(_latest_safe_leave_timestamp(
            prediction(target_depletion_timestamp=None)))
    def test_roll_to_next_reachable_cycle_without_inventing_p1(self):
        p1=prediction(target_depletion_timestamp=NOW+8000)
        p2=prediction(prediction_number=2,estimate_timestamp=NOW+17200,
                      window_end_timestamp=NOW+17800,
                      recommended_arrival_timestamp=NOW+18100,
                      target_depletion_timestamp=NOW+20000)
        frozen=dict(predictions=[p1,p2],display_prediction=p1)
        new=_roll_prediction_to_now(frozen,now=NOW)
        self.assertEqual(new["active_prediction_number"],2)
        self.assertFalse(new["predictions"][0]["usable_for_departure"])
        self.assertTrue(new["predictions"][1]["usable_for_departure"])
        self.assertIs(frozen["display_prediction"],p1)

    @unittest.skipUnless(shutil.which("node"),"Node unavailable on this runner")
    def test_browser_and_python_same_window_rejection_and_latest_leave(self):
        source=HTML.read_text()
        start=source.index("    function departureWindowForPrediction(prediction, flightSeconds) {")
        end=source.index("    function rollPredictionTargetClientSide()",start)
        helper=source[start:end]
        fixtures=[
            prediction(),
            prediction(target_depletion_timestamp=NOW+8000),
            prediction(target_depletion_timestamp=NOW+8400),
            prediction(target_depletion_timestamp=None),
        ]
        script=(helper+"\n"+
            "const fixtures="+json.dumps(fixtures)+";\n"+
            "console.log(JSON.stringify(fixtures.map(p => {"+
            "const x=departureWindowForPrediction(p,p.travel_seconds);"+
            "return x ? x.latestLeave : null;"+
            "})));")
        r=subprocess.run(["node","-e",script],capture_output=True,text=True,
                         check=False,timeout=8)
        self.assertEqual(r.returncode,0,r.stderr)
        results=json.loads(r.stdout)
        self.assertEqual(results,[
            _latest_safe_leave_timestamp(p) for p in fixtures])
        self.assertEqual(results,[NOW+8080,None,None,None])

if __name__=="__main__":
    unittest.main()
