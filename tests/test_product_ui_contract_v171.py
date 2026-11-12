import unittest

from services.product_ui_contract_v171 import build_item_ui, attach_board_ui


class ProductUiContractV171Tests(unittest.TestCase):
    def row(self, **overrides):
        base={
            'item_key':'sou:Xanax','item_name':'Xanax','country':'sou',
            'country_name':'South Africa','category':'Medication',
            'observed_quantity':2500,'last_quantity_change_epoch':900,
            'departure_epoch':1300,'arrival_epoch':1300+11820,
            'departure_deadline_epoch':1500,'model_name':'V19 dyn1',
            'event_model_name':'event','policy':'champion',
            'departure_source':'explicit_recommendation','graph_url':'/?country=sou&item=Xanax',
            'decision':{'player_flight_seconds':11820,'selected_restock_event_index':1,
                        'valid_until_epoch':1600,'forecast_events':[]},
            'evidence':{'successes':94,'resolved_arrivals':100,'historical_fraction':.94,
                        'applies_to_selected_trip':True,'label':'Historical replay'},
            'event_timeline':[{'index':1,'predicted_restock_epoch':13120,
                               'restock_early_epoch':13000,'restock_late_epoch':13240,
                               'predicted_stock_below_30_epoch':15000,
                               'flight_reachable':True}],
        }
        base.update(overrides)
        return base

    def test_leave_soon_contract(self):
        ui=build_item_ui(self.row(),now=1000,source_poll_age_seconds=20)
        self.assertEqual('LEAVE_SOON',ui['decision']['status'])
        self.assertEqual('Leave soon',ui['decision']['label'])
        self.assertEqual(300,ui['decision']['leave_in_seconds'])
        self.assertEqual(11820,ui['decision']['flight_seconds'])
        self.assertTrue(ui['live']['fresh'])
        self.assertFalse(ui['evidence']['arrival_probability_calibrated'])

    def test_stale_beats_departure(self):
        ui=build_item_ui(self.row(),now=1000,source_poll_age_seconds=181)
        self.assertEqual('STALE',ui['decision']['status'])
        self.assertEqual('Refresh data',ui['copy']['primary_action'])

    def test_no_trip_is_explicit(self):
        row=self.row(departure_epoch=None,arrival_epoch=None,departure_deadline_epoch=None)
        ui=build_item_ui(row,now=1000,source_poll_age_seconds=10)
        self.assertEqual('NO_SUPPORTED_TRIP',ui['decision']['status'])
        self.assertEqual('No supported trip',ui['decision']['label'])

    def test_board_attachment_is_additive(self):
        board={'rows':[self.row()],'source_poll_age_seconds':20}
        out=attach_board_ui(board,now=1000)
        self.assertIn('departure_epoch',out['rows'][0])
        self.assertIn('ui',out['rows'][0])
        self.assertEqual(3,len(out['navigation']))
        self.assertEqual(1,out['ui_contract_version'])


if __name__=='__main__':
    unittest.main()
