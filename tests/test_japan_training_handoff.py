import unittest
from research.japan_xanax.training_handoff import SingleZeroHandoff


class TrainingHandoffTests(unittest.TestCase):
    def tracker(self,rows,healthy=lambda a,b:True,crosses=lambda a,b:False):
        h=SingleZeroHandoff(crosses,healthy)
        for row in rows:h.add(row)
        return h

    def test_preserves_one_actual_zero_anchor_and_complete_observed_tuple(self):
        rows=[(0,100,'a'),(10,0,'a'),(50,0,'b'),(100,100,'b'),(130,20,'b'),(150,0,'b')]
        h=self.tracker(rows)
        self.assertEqual(tuple(h.cycles[0]),(10,100,150,30,100))
        self.assertEqual(h.bridged_cycle_ends,[150])
        self.assertEqual(h.low,150)

    def test_second_switch_disqualifies_cycle_even_when_both_zero(self):
        h=self.tracker([(0,100,'a'),(10,0,'a'),(40,0,'b'),(70,0,'c'),(100,100,'c'),(150,0,'c')])
        self.assertEqual(h.cycles,[])
        self.assertEqual(h.counts['agreeing_zero_handoff_preserved'],1)

    def test_no_initial_zero_anchor_can_be_invented(self):
        h=self.tracker([(10,0,'a'),(40,0,'b'),(100,100,'b'),(150,0,'b')])
        self.assertEqual(h.cycles,[])
        self.assertEqual(h.bridged_cycle_ends,[])

    def test_long_handoff_unhealthy_polls_and_gaps_are_rejected(self):
        cases=[([(0,100,'a'),(10,0,'a'),(71,0,'b'),(100,100,'b'),(150,0,'b')],lambda a,b:True,lambda a,b:False),
               ([(0,100,'a'),(10,0,'a'),(50,0,'b'),(100,100,'b'),(150,0,'b')],lambda a,b:False,lambda a,b:False),
               ([(0,100,'a'),(10,0,'a'),(50,0,'b'),(100,100,'b'),(150,0,'b')],lambda a,b:True,lambda a,b:a<30<=b)]
        for rows,healthy,crosses in cases:
            h=self.tracker(rows,healthy,crosses);self.assertEqual(h.cycles,[])

    def test_positive_switch_and_topup_do_not_join_training(self):
        for tail in [[(110,90,'c'),(150,0,'c')],[(110,200,'b'),(150,0,'b')]]:
            h=self.tracker([(0,100,'a'),(10,0,'a'),(50,0,'b'),(100,100,'b')]+tail)
            self.assertEqual(h.cycles,[])


if __name__=='__main__':unittest.main()
