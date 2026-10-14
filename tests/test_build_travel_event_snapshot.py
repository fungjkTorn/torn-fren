import json
import tempfile
import unittest
from pathlib import Path
from research.build_travel_event_snapshot import prepare,publish
import test_continuous_departure_replay as fixtures
T=fixtures.T


class PublisherTests(unittest.TestCase):
    def test_consistent_readonly_per_item_models_and_atomic_consumer_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);db=fixtures.ContinuousTests().fixture(root);before=db.read_bytes()
            snapshot=prepare(db,model_sha='a'*40,now=T,assignments={
                'mex:Jaguar Plushie':{'event_history':'phase_analogs_18','flight_adapter':'current_quarter'},
                'can:Wolverine Plushie':{'event_history':'recent_8','flight_adapter':'midpoint'}})
            self.assertEqual(len(snapshot['items']),24)
            self.assertEqual(snapshot['items']['mex:Jaguar Plushie']['model_name'],'causal_item_phase_analogs_v1')
            self.assertEqual(snapshot['items']['can:Wolverine Plushie']['cycle_window'],8)
            self.assertEqual(snapshot['item_policies']['mex:Jaguar Plushie'],'current_quarter')
            output=root/'events.json';publish(snapshot,output,source=db)
            self.assertEqual(json.loads(output.read_text()),snapshot)
            self.assertEqual(db.read_bytes(),before)
            with self.assertRaises(ValueError):prepare(db,model_sha='a'*40,now=T+181)
            with self.assertRaises(ValueError):publish(snapshot,db,source=db)

    def test_unverified_assignments_and_source_revision_rejected(self):
        with self.assertRaises(ValueError):prepare('unused',model_sha='latest')
        with self.assertRaises(ValueError):prepare('unused',model_sha='a'*40,assignments={'invented:Item':{}})
        with self.assertRaises(ValueError):prepare('unused',model_sha='a'*40,assignments={'jap:Xanax':{'event_history':'automatic_winner','flight_adapter':'median'}})


if __name__=='__main__': unittest.main()
