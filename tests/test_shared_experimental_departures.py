import copy
import unittest
from services.experimental_shared_departures import rows_for_experimental
from services.travel_read_model import build_board
from test_travel_read_model import departure_snapshot,T


class ExperimentalRowsTests(unittest.TestCase):
    def test_selected_geometry_deadline_provenance_and_expiry(self):
        data=departure_snapshot(T)
        data['item_departure_recommendations']['mex:Jaguar Plushie']['execution_policy']='publication_delay_30s_v1'
        board=build_board(data,now=T+10);before=copy.deepcopy(board)
        row=rows_for_experimental(board,now=T+10)[0]
        self.assertEqual(row['departure'],T+10)
        self.assertEqual(row['arrival'],T+10+1020)
        self.assertEqual(row['valid_until'],T+30)
        self.assertEqual(row['status_label'],'Reconfirm before leaving')
        self.assertFalse(row['prediction_accuracy_verified'])
        self.assertEqual(board,before)
        expired=rows_for_experimental(board,now=T+31)[0]
        self.assertFalse(expired['actionable']);self.assertIsNone(expired['arrival'])

    def test_future_forecast_does_not_become_a_leave_now_instruction(self):
        row=rows_for_experimental(build_board(departure_snapshot(),now=T),now=T)[0]
        self.assertEqual(row['status_label'],'Leave in 20m')
        self.assertLess(row['valid_until'],row['departure'])
