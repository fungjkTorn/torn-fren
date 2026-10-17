"""Dual-view clock/offline regressions; no VM, gameplay or database access."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from web import app as web
from research.v140_existing_experimental_beta_board import build_board
from tests.test_v140_existing_experimental_beta_board import KEYS, panel, old, candidate

NOW = 1791800000
HTML = Path(__file__).resolve().parents[1] / 'web/static/index.html'


class HistoryPredictionIsolationTests(unittest.TestCase):
    def history(self, result=None, error=None):
        baseline = {'estimate_timestamp': NOW + 1000}
        with ExitStack() as stack:
            stack.enter_context(patch.dict('os.environ', {'TORN_FREN_V38_REVISION_CACHE': '0'}))
            for name, value in {
                'get_item_history_since': [{'timestamp': NOW, 'quantity': 80}],
                'get_latest_item_snapshot': {'cost': 100},
                '_get_analysis_nonblocking': ({'prediction': baseline, 'events': [],
                    'collector_last_success_timestamp': NOW}, False),
                'profitability_for_item': ({'net_profit': 10}, {}),
                'get_recent_active_forecasts': [],
            }.items():
                stack.enter_context(patch.object(web, name, return_value=value))
            stack.enter_context(patch.object(web, '_get_prediction_nonblocking',
                return_value=(result, False), side_effect=error))
            stack.enter_context(patch.object(web.time, 'time', return_value=NOW))
            response = web.api_history('can', 'Crocus', 1440)
        self.assertEqual(response['rows'][0]['quantity'], 80)
        analysis = response['analysis']
        self.assertEqual(analysis['baseline_prediction'], baseline)
        self.assertEqual(analysis['profitability']['net_profit'], 10)
        self.assertEqual(analysis['prediction_v2_checked_at'], NOW)
        return analysis

    def test_no_target_never_resurrects_baseline(self):
        for result in (None, {}, {'status': 'ok', 'display_prediction': None},
                       {'status': 'error'}, {'status': 'warming'}):
            with self.subTest(result=result):
                self.assertIsNone(self.history(result)['prediction'])

    def test_model_exception_keeps_graph_but_withdraws_departure(self):
        result = self.history(error=RuntimeError('model unavailable'))
        self.assertIsNone(result['prediction'])
        self.assertTrue(result['prediction_v2_stale'])
        self.assertIn('model unavailable', result['prediction_v2_error'])

    def test_valid_v2_target_is_preserved(self):
        prediction = {'estimate_timestamp': NOW + 2000, 'prediction_number': 2}
        result = self.history({'display_prediction': prediction})
        self.assertEqual(result['prediction']['prediction_number'], 2)
        self.assertFalse(result['prediction_v2_stale'])


class BoardClockTests(unittest.TestCase):
    def test_reused_panel_transitions_without_reissuing_or_mutating(self):
        p = panel({k: candidate(k, dep=NOW + 301) for k in KEYS})
        original = copy.deepcopy(p)
        for now, expected in ((NOW, 'RESEARCH_FUTURE_WATCH_RECHECK_REQUIRED'),
                              (NOW + 1, 'RESEARCH_NEAR_TERM_NOT_CERTIFIED'),
                              (NOW + 280, 'RESEARCH_SNAPSHOT_EXPIRED')):
            result = build_board({'latest': [old(k) for k in KEYS]}, p,
                                 now=now, roster_keys=KEYS)
            self.assertEqual(result['v128_status_counts'], {expected: 24})
            self.assertTrue(all(r['primary_is_incumbent_not_v128'] for r in result['rows']))
            if 'EXPIRED' in expected:
                self.assertTrue(all(r['v128_research_challenger']['departure_epoch'] is None
                                    for r in result['rows']))
        self.assertEqual(p, original)

    def test_future_issue_and_passed_departure_labels_fail_closed(self):
        for issue, dep, expected in ((NOW + 1, NOW + 50, 'FUTURE_ISSUANCE_REJECTED'),
                                    (NOW - 20, NOW - 1, 'PROPOSED_DEPARTURE_ALREADY_PASSED')):
            p = panel({k: candidate(k, issue=issue, dep=dep) for k in KEYS})
            p['selected_issued_epoch'] = issue
            result = build_board({}, p, now=NOW, roster_keys=KEYS)
            self.assertEqual(result['v128_status_counts'], {expected: 24})
            self.assertTrue(all(r['v128_research_challenger']['departure_epoch'] is None
                                for r in result['rows']))


@unittest.skipUnless(shutil.which('node'), 'Node required for browser execution')
class BrowserFreshnessTests(unittest.TestCase):
    def run_browser(self, body):
        source = HTML.read_text()
        helpers = source[source.index('    function departureGuidanceBlock('):
                         source.index('    function setReliabilityBadge(')]
        script = '''
const flightDeadlineEl={}, flightCountdownEl={}, flightStatusEl={}, flightMetaEl={};
const flightSection={classList:{remove(){},add(){}}};
const PI_PILOT_FLIGHT_MINUTES={can:27}, COUNTRY_NAMES={can:'Canada'};
let country='can', predictionRefreshFailed=false;
let currentAnalysis={prediction_v2_stale:false, prediction_v2_checked_at:NOW,
 collector_last_success_timestamp:NOW,
 prediction:{estimate_timestamp:NOW+1600,prediction_number:1}};
Date.now=()=>NOW*1000;
function rollPredictionTargetClientSide(){return false;}
function departureWindowForPrediction(){return {earliestLeave:NOW-30,latestLeave:NOW+60,
 earliestArrival:NOW+1590,latestArrival:NOW+1680};}
function formatFlightMinutes(x){return String(x);}
function formatDurationSeconds(x){return String(x);}
function formatCompactDuration(x){return String(x);}
function formatClock(x){return String(x);}
''' .replace('NOW', str(NOW))
        result = subprocess.run(['node', '-e', script + helpers + body],
                                capture_output=True, text=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_actual_ticker_withdraws_after_failed_refresh_and_recovers(self):
        output = self.run_browser('''
updateFlightTicker(); const fresh=flightDeadlineEl.textContent;
predictionRefreshFailed=true; updateFlightTicker();
const offline={label:flightDeadlineEl.textContent,countdown:flightCountdownEl.textContent};
predictionRefreshFailed=false; updateFlightTicker();
console.log(JSON.stringify({fresh,offline,recovered:flightDeadlineEl.textContent}));
''')
        self.assertEqual(output['fresh'], 'MODELED DEPARTURE WINDOW')
        self.assertEqual(output['offline'], {'label': 'RECHECK REQUIRED', 'countdown': '--:--:--'})
        self.assertEqual(output['recovered'], output['fresh'])

    def test_missing_future_stale_and_exact_expiry_boundaries(self):
        output = self.run_browser('''
const now=Date.now()/1000;
const variants=[{}, {prediction_v2_stale:true}, {prediction_v2_checked_at:now-300},
 {prediction_v2_checked_at:now+1}, {collector_last_success_timestamp:now-181},
 {collector_last_success_timestamp:null}, {collector_last_success_timestamp:now+1},
 {collector_last_success_timestamp:now-180}, {prediction_v2_checked_at:now-299}];
console.log(JSON.stringify(variants.map(v=>departureGuidanceBlock(
 {...currentAnalysis,...v},now,false)===null)));
''')
        self.assertEqual(output, [True, False, False, False, False, False, False, True, True])

    def test_clock_advance_blocks_frozen_page_even_without_network_events(self):
        output = self.run_browser('''
Date.now=()=>(''' + str(NOW) + '''+301)*1000;
updateFlightTicker();
console.log(JSON.stringify({label:flightDeadlineEl.textContent,kept:!!currentAnalysis.prediction}));
''')
        self.assertEqual(output, {'label': 'RECHECK REQUIRED', 'kept': True})


if __name__ == '__main__':
    unittest.main()
