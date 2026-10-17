import unittest
from research.japan_xanax.zero_handoff import ZeroAnchor,poll_continuity
from research.japan_xanax.renewal_shadow import History


class HandoffTests(unittest.TestCase):
    def test_zero_agreement_preserves_observed_zero_not_training_history(self):
        h=History(lambda a,b:False);z=ZeroAnchor(h.crosses,60)
        for row in [(0,100,'a'),(10,0,'a'),(40,0,'b')]:z.add(row);h.add(row)
        self.assertIsNone(h.phase_start);view,borrowed=z.phase_view(h)
        self.assertTrue(borrowed);self.assertEqual(view.phase_start,10)
        self.assertIs(view.cycles,h.cycles);self.assertIsNone(h.phase_start)

    def test_initial_zero_other_threshold_and_cross_provider_transition_never_create_anchor(self):
        for rows in [[(0,0,'a'),(10,0,'b')],[(0,100,'a'),(10,20,'a'),(20,0,'b')]]:
            z=ZeroAnchor(lambda a,b:False,60)
            for row in rows:z.add(row)
            self.assertIsNone(z.anchor)

    def test_old_gapped_or_disagreeing_handoff_cancels_borrowing(self):
        for last in [(100,0,'b'),(40,1,'b')]:
            z=ZeroAnchor(lambda a,b:False,60)
            for row in [(0,100,'a'),(10,0,'a'),last]:z.add(row)
            self.assertIsNone(z.anchor)
        z=ZeroAnchor(lambda a,b:a>=10,60)
        for row in [(0,100,'a'),(10,0,'a'),(40,0,'b')]:z.add(row)
        self.assertIsNone(z.anchor)

    def test_poll_guard_uses_only_past_polls_and_rejects_hidden_gaps(self):
        healthy=poll_continuity([0,30,60,90,120,150,180,210,240,270,300,600])
        self.assertTrue(healthy(10,300));self.assertFalse(healthy(10,600))
        self.assertFalse(poll_continuity([300])(0,100))
        z=ZeroAnchor(lambda a,b:False,86400,poll_continuity(list(range(0,1001,30))))
        for row in [(0,100,'a'),(10,0,'a'),(900,0,'b')]:z.add(row)
        self.assertEqual(z.anchor,10)


if __name__=='__main__':unittest.main()
