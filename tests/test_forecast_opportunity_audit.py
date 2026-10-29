import unittest
from research.forecast_opportunity_audit import ProviderContinuousTargetIndex,first_forecasts
from services.first_release_evidence import TargetIndex,grade


def row(issued,ordinal,status='FAILURE'):
    return {'issued':issued,'outcome':{'status':status},'row':{
        'asof_epoch':issued,'decision':{'selected_restock_event_index':ordinal,
        'estimated_departure_epoch':issued+100}}}


class OpportunityAuditTests(unittest.TestCase):
    def test_benign_switch_preserves_future_and_current_identity(self):
        history=[(1,0,'a'),(5,0,'b'),(10,100,'b'),(20,90,'a'),(30,0,'a')]
        index=ProviderContinuousTargetIndex(history,[])
        self.assertEqual(10,index.target(row(2,1)['row'])['epoch'])
        self.assertEqual(10,index.target(row(25,0)['row'])['epoch'])
        self.assertEqual(10,TargetIndex(history,[]).target(row(2,1)['row'])['epoch'])

    def test_conflicting_switch_and_gap_still_prevent_identity(self):
        conflict=[(1,0,'a'),(5,100,'b'),(10,0,'b'),(15,100,'b')]
        self.assertIsNone(ProviderContinuousTargetIndex(conflict,[]).target(row(2,1)['row']))
        clean=[(1,0,'a'),(5,0,'b'),(10,100,'b')]
        self.assertIsNone(ProviderContinuousTargetIndex(clean,[(3,6)]).target(row(2,1)['row']))

    def test_first_forecast_is_selected_by_clock_not_file_order_or_outcome(self):
        history=[(1,0,'a'),(5,0,'b'),(10,100,'b')]
        first=row(2,1,'FAILURE');later=row(6,1,'SUCCESS')
        groups,unmatched=first_forecasts([later,first],ProviderContinuousTargetIndex(history,[]))
        self.assertIs(first,groups[10][0]);self.assertEqual([],unmatched)
        self.assertEqual('FAILURE',groups[10][0]['outcome']['status'])

    def test_arrival_provider_switch_remains_unknown(self):
        # Identity continuity is not permission to call a mixed-provider
        # landing bracket a known stock success.
        self.assertEqual('UNKNOWN',grade(100,[(50,100,'a'),(110,90,'b')],
            [90,120],[],cutoff=400)['status'])


if __name__=='__main__':unittest.main()
