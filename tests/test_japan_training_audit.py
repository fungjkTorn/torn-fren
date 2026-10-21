import unittest
from unittest.mock import patch
from research.japan_xanax import training_audit as m
from research.japan_xanax.training_audit import HalfPhases,summarize
from research.japan_xanax.renewal_shadow import History


class TrainingAuditTests(unittest.TestCase):
    def test_latest_snapshot_window_is_bounded_and_keeps_future_rows_out(self):
        cutoff=1792291234
        rows=[(cutoff+100,0,'a')]
        with patch.object(m,'source_data',return_value=(rows,[cutoff-20],lambda a,b:False,None,cutoff)):
            r=m.run('unused',model_sha='a'*40,latest=True)
        self.assertEqual(sum(r['prerequisite_counts'].values()),288)
        self.assertLessEqual(r['issue_end'],cutoff)
        self.assertEqual(r['whole_cycle_ends_in_window'],[])
        self.assertEqual(r['window'],'latest_snapshot_day')

    def test_half_phase_from_left_censored_zero_is_not_a_whole_cycle(self):
        h=History(lambda a,b:False);p=HalfPhases(lambda a,b:False)
        for row in [(0,0,'a'),(50,100,'a'),(80,20,'a'),(100,0,'a')]:h.add(row);p.add(row)
        self.assertEqual(h.cycles,[])
        self.assertEqual(p.low,[])
        self.assertEqual(p.high,[dict(start=50,end=100,duration=50,available=30,batch=100,provider='a')])

    def test_zero_half_survives_as_training_when_later_high_phase_is_interrupted(self):
        p=HalfPhases(lambda a,b:False)
        for row in [(0,100,'a'),(10,0,'a'),(60,100,'a'),(70,90,'b'),(90,0,'b')]:p.add(row)
        self.assertEqual(len(p.low),1);self.assertEqual(p.low[0]['duration'],50)
        self.assertEqual(p.high,[])
        self.assertEqual(p.resets['PROVIDER_SWITCH'],1)

    def test_gap_and_positive_topup_cannot_fabricate_a_half_phase(self):
        for rows,crosses in [([(0,100,'a'),(10,0,'a'),(60,100,'a')],lambda a,b:a<30<=b),
                             ([(0,0,'a'),(10,100,'a'),(20,200,'a'),(60,0,'a')],lambda a,b:False)]:
            p=HalfPhases(crosses)
            for row in rows:p.add(row)
            self.assertEqual(p.low,[]);self.assertEqual(p.high,[])

    def test_threshold_loss_does_not_end_positive_phase(self):
        p=HalfPhases(lambda a,b:False)
        for row in [(0,0,'a'),(10,100,'a'),(20,29,'a'),(30,1,'a'),(50,0,'a')]:p.add(row)
        self.assertEqual(p.high[0]['end'],50);self.assertEqual(p.high[0]['available'],10)
        self.assertEqual(p.high[0]['duration'],40)

    def test_summary_does_not_read_future_completion(self):
        rows=[dict(end=100,duration=10),dict(end=200,duration=20)]
        s=summarize(rows,150)
        self.assertEqual(s['total_completed'],1);self.assertEqual(s['newest_end'],100)
        self.assertEqual(s['duration_p10_p50_p90_seconds'],[10.,10.,10.])


if __name__=='__main__':unittest.main()
