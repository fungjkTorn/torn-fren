import os
import tempfile
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from web.shared_experimental_overlay import overlay_response
from test_travel_read_model import departure_snapshot,T


class OverlayTests(unittest.TestCase):
    def test_disabled_hook_preserves_incumbent_response_and_avoids_io(self):
        response={'latest':[{'item_key':'mex:Jaguar Plushie','actionable':True}]}
        with patch.dict(os.environ,{'TORN_FREN_SHARED_EXPERIMENTAL_PREVIEW':'0'}),patch('web.shared_experimental_overlay.cache.read',side_effect=AssertionError('unexpected IO')):
            self.assertIs(overlay_response(response,now=T),response)

    def test_shared_hook_uses_same_board_and_preserves_query_filter(self):
        data=departure_snapshot(T)
        data['item_departure_recommendations']['mex:Jaguar Plushie']['execution_policy']='publication_delay_30s_v1'
        response={'latest':[{'item_key':'mex:Jaguar Plushie','departure':T-100,'success_probability':1}], 'experimental':True}
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'shared.json';path.write_text(json.dumps(data))
            with patch.dict(os.environ,{'TORN_FREN_SHARED_EXPERIMENTAL_PREVIEW':'1','TORN_FREN_TRAVEL_EVENT_SNAPSHOT':str(path)}):
                actual=overlay_response(response,now=T+10,key='mex:Jaguar Plushie')
                self.assertEqual(actual['latest'][0]['departure'],T+10)
                self.assertNotIn('success_probability',actual['latest'][0])
                self.assertEqual(overlay_response(response,now=T+10,key='chi:Panda Plushie')['latest'],[])
                path.write_text('{broken')
                failed=overlay_response(response,now=T+10)
                self.assertFalse(failed['latest'][0]['actionable'])
                self.assertIsNone(failed['latest'][0]['departure'])
                self.assertEqual(response['latest'][0]['departure'],T-100)
