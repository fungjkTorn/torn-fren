import unittest
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from research.supported_target_retention import WAIT, STEP, MODES
from research.supported_target_replay import schedule, score_records, collect_item


def tick(q, native, points, age=0):
    return dict(issued=q, native=native, points=points, age=age)


class ReplayTests(unittest.TestCase):
    def test_collection_finishes_all_causal_inference_before_exporting_labels(self):
        calls=[];queries=tuple(range(0,WAIT+2*STEP,STEP))
        class Mirror:
            def __init__(self,*a): pass
            def __enter__(self): return self
            def advance(self,q): calls.append(q)
            def __exit__(self,*a): pass
        class Evidence:
            def score(self,arrival):
                self_check.assertEqual(tuple(calls),queries)
                return 'UNKNOWN','FIXTURE_UNKNOWN',None
        self_check=self
        def child(args,**kwargs):
            q=int(args[-1])
            return SimpleNamespace(stdout=json.dumps(dict(issued=q,native=q,points=[[q,.9]])))
        source=([],list(queries),lambda a,b:False,Evidence(),WAIT+STEP+9600+190)
        with tempfile.TemporaryDirectory() as td, \
             patch('research.japan_xanax.renewal_shadow.source_data',return_value=source), \
             patch('research.causal_replay_slice.CausalReplaySlice',Mirror), \
             patch('research.supported_target_replay.subprocess.run',side_effect=child):
            report=collect_item('unused',td,'chi:Peony',(0,),25)
            self.assertEqual(report['worker_errors'],0)
            work=Path(td)/'chi-Peony'
            bands=[json.loads(s) for s in (work/'as-issued-bands.jsonl').read_text().splitlines()]
            labels=[json.loads(s) for s in (work/'arrival-evaluation.jsonl').read_text().splitlines()]
            self.assertEqual(len(bands),len(queries));self.assertEqual(len(labels),len(queries))
            self.assertTrue(all(l['outcome']=='UNKNOWN' and l['training_input'] is False for l in labels))
            self.assertTrue(all('outcome' not in b for b in bands))

    def test_current_support_can_resolve_repeated_postponement(self):
        ticks = [tick(0, 600, ((300, .8), (600, .8), (900, .8)))]
        for q in range(STEP, WAIT+STEP+1, STEP):
            ticks.append(tick(q, q+600, tuple((q+d, .8) for d in (0, 300, 600, 900))))
        results = {r['mode']:r for r in schedule(ticks, (0,))}
        self.assertIsNone(results['native']['departure'])
        self.assertEqual(results['retain_original_band']['departure'], 615)
        self.assertEqual(results['retain_original_band55']['departure'], 615)
        self.assertEqual(results['leave_now_control']['departure'], 15)

    def test_missing_tick_fails_instead_of_bridging_unsupported_target(self):
        with self.assertRaisesRegex(ValueError, 'Missing'):
            schedule([tick(0, 600, ((600, .8),)), tick(600, 900, ((900, .8),))], (0,))

    def test_cohort_deadlines_and_retained_targets_are_independent(self):
        ticks = [tick(q, q+600, tuple((q+d, .8) for d in (0, 300, 600, 900)))
                 for q in range(0, WAIT+2*STEP+1, STEP)]
        records = schedule(ticks, (0, 300))
        self.assertEqual(len(records), 2*len(MODES))
        retained = [r for r in records if r['mode'] == 'retain_original_band']
        self.assertEqual([r['departure'] for r in retained], [615, 915])
        self.assertTrue(all(r['departure'] is None for r in records if r['mode'] == 'native'))

    def test_truth_has_no_effect_on_scheduling_and_unknown_is_preserved(self):
        ticks = [tick(q, q, ((q, .9),)) for q in range(0, WAIT+STEP+1, STEP)]
        decisions = schedule(ticks, (0,))
        class E:
            def __init__(self, label): self.label = label
            def score(self, t): return self.label, None, None
        success = score_records(decisions, E('SUCCESS'), 9600)
        unknown = score_records(decisions, E('UNKNOWN'), 9600)
        self.assertEqual([r['departure'] for r in success], [r['departure'] for r in unknown])
        self.assertEqual({r['outcome'] for r in unknown}, {'UNKNOWN'})
        with self.assertRaisesRegex(ValueError, 'Immature'):
            score_records(decisions, E('PENDING'), 9600)

    def test_incomplete_horizon_does_not_become_abstention(self):
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            schedule([tick(0, 600, ((600, .8),))], (0,))


if __name__ == '__main__': unittest.main()
