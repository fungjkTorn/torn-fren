import unittest
from research.supported_target_retention import WAIT, STEP, MODES
from research.supported_target_replay import schedule, score_records


def tick(q, native, points, age=0):
    return dict(issued=q, native=native, points=points, age=age)


class ReplayTests(unittest.TestCase):
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
