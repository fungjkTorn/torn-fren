import unittest
from research.full_roster_capture_review import review

ROSTER=tuple('country:item%d'%i for i in range(24))
MODES=tuple('model%d'%i for i in range(9))


def batch(q):
    return [dict(item_key=k,mode=m,issued=q,published=q+10,departure=q+15,
        executable_before_next_recheck=True,status='PROPOSAL') for k in ROSTER for m in MODES]


class CaptureReviewTests(unittest.TestCase):
    def test_216_rows_prove_footprint_not_model_success(self):
        rows=batch(3600)
        rows[0].update(status='SPECIALIST_ERROR_TimeoutExpired',departure=None,executable_before_next_recheck=False)
        result=review(rows,[(3600,'ALL24_SPECIALIST_SHADOW_RECORDED')],roster=ROSTER,modes=MODES)
        self.assertTrue(result['complete_footprints'])
        self.assertEqual(result['complete24_row_batches'],1)
        model=result['models'][ROSTER[0]+'|'+MODES[0]]
        self.assertEqual(model['eligible_hours'],0)
        self.assertEqual(model['statuses'],{'SPECIALIST_ERROR_TimeoutExpired':1})

    def test_skipped_whole_hours_remain_in_capture_denominator(self):
        result=review(batch(3600)+batch(10800),[(100,'ALL24_SHADOW_DEFERRED_CPU_PRESSURE'),
            (3600,'ALL24_SPECIALIST_SHADOW_RECORDED'),(7200,'ALL24_SHADOW_DEFERRED_CPU_PRESSURE'),
            (10800,'ALL24_SPECIALIST_SHADOW_RECORDED')],roster=ROSTER,modes=MODES)
        self.assertEqual(result['active_window_observed_hours'],3)
        self.assertEqual(result['active_hours_without_any_capture'],[2])
        model=result['models'][ROSTER[0]+'|'+MODES[0]]
        self.assertEqual(model['eligible_hour_fraction_in_observed_active_window'],2/3)
        self.assertEqual(result['complete24_row_batches'],2)

    def test_repeated_targets_are_not_counted_as_distinct_departures(self):
        rows=batch(3600)+batch(3900)
        for r in rows:r['departure']=4000
        result=review(rows,[(3600,'ALL24_SPECIALIST_SHADOW_RECORDED')],roster=ROSTER,modes=MODES)
        model=result['models'][ROSTER[0]+'|'+MODES[0]]
        self.assertEqual(model['eligible_rows'],2)
        self.assertEqual(model['distinct_eligible_departures'],1)

    def test_missing_row_duplicate_and_wrong_model_not_silently_complete(self):
        for rows in (batch(3600)[:-1],batch(3600)[:-1]+[batch(3600)[0]]):
            result=review(rows,[],roster=ROSTER,modes=MODES)
            self.assertFalse(result['complete_footprints'])
            self.assertEqual(len(result['incomplete_row_batches']),1)
        rows=batch(3600);rows[0]['mode']='unrecorded-model'
        with self.assertRaisesRegex(ValueError,'Unrecognized'):
            review(rows,[],roster=ROSTER,modes=MODES)

    def test_no_data_is_not_zero_percent_accuracy_or_complete(self):
        result=review([],[(100,'ALL24_SHADOW_DEFERRED_CPU_PRESSURE')],roster=ROSTER,modes=MODES)
        self.assertFalse(result['complete_footprints'])
        self.assertEqual(result['recorded_items'],0)
        self.assertEqual(len(result['missing_items']),24)
        self.assertIsNone(result['models'][ROSTER[0]+'|'+MODES[0]]['eligible_hour_fraction_in_observed_active_window'])


if __name__=='__main__':unittest.main()
