import unittest
from research.japan_xanax.forecast_gap_audit import prerequisite
from research.japan_xanax.renewal_shadow import History


class GapTests(unittest.TestCase):
    def history(self):
        from test_renewal_shadow import rows
        h=History(lambda a,b:False)
        for row in rows():h.add(row)
        return h

    def test_reasons_track_model_prerequisites(self):
        from test_renewal_shadow import T
        h=self.history()
        self.assertEqual(prerequisite(h,T,181)[0],'STALE_OR_MISSING_HEARTBEAT')
        self.assertEqual(prerequisite(h,T,0)[0],'READY')
        h.phase_start=None
        self.assertEqual(prerequisite(h,T,0)[0],'UNKNOWN_PHYSICAL_PHASE')
        h.phase_start=T-3000
        reason,info=prerequisite(h,T,0)
        self.assertEqual(reason,'FEWER_THAN_4_PHASE_SURVIVORS');self.assertEqual(info['survivors'],0)
        self.assertIsNone(h.plans(T,poll_age=0)['sequence_blocks_peak']['departure'])

    def test_censored_initial_history_and_collection_gap_stay_unavailable(self):
        from test_renewal_shadow import T
        h=History(lambda a,b:False);h.add((T,0,'a'))
        self.assertEqual(prerequisite(h,T,0)[0],'FEWER_THAN_16_CYCLES')
        h=self.history();h.crosses=lambda a,b:True
        self.assertEqual(prerequisite(h,T,0)[0],'ACTIVE_COLLECTION_GAP')
        with self.assertRaises(ValueError):prerequisite(h,T-86400,0)


if __name__=='__main__':unittest.main()
