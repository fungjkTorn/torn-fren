import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from research.build_travel_event_snapshot import prepare,publish
import test_continuous_departure_replay as fixtures
T=fixtures.T


class PublisherTests(unittest.TestCase):
    def test_tolerance_profile_is_explicit_and_old_profile_remains_strict(self):
        from services.travel_read_model import build_board
        root=Path(__file__).resolve().parents[1]
        profile=json.loads((root/'deploy/research_runner/flowers_plushies_tolerance30_candidate_20261016.json').read_text())
        old=json.loads((root/'deploy/research_runner/flowers_plushies_candidate_assignments_20261016.json').read_text())
        self.assertTrue(all('execution_policy' not in c for c in old.values()))
        with tempfile.TemporaryDirectory() as td:
            db=fixtures.ContinuousTests().fixture(Path(td));before=db.read_bytes()
            snapshot=prepare(db,model_sha='a'*40,now=T,assignments=profile)
            board=build_board(snapshot,now=T+10)
            for row in board['rows']:
                expected=profile[row['item_key']]['execution_policy']
                self.assertEqual(row['decision']['execution_policy'],expected)
                if row['decision']['model_departure_epoch']==T and expected=='publication_delay_30s_v1':
                    self.assertEqual(row['departure_epoch'],T+10)
                    self.assertEqual(row['arrival_epoch'],T+10+row['decision']['player_flight_seconds'])
            self.assertEqual(db.read_bytes(),before)
        for config in ({'execution_policy':'publication_delay_30s_v1'},
                       {'departure_policy':'disabled','execution_policy':'publication_delay_30s_v1'},
                       {'departure_policy':'zero_path_analog70','execution_policy':'unsafe_delay'}):
            with self.assertRaises(ValueError):prepare('unused',model_sha='a'*40,
                assignments={'mex:Jaguar Plushie':dict(event_history='true_zero_all',flight_adapter='median',**config)})

    def test_staged_item_profile_keeps_weak_items_and_medication_nonactionable(self):
        from services.travel_read_model import build_board
        profile=Path(__file__).resolve().parents[1]/'deploy/research_runner/flowers_plushies_candidate_assignments_20261016.json'
        assignments=json.loads(profile.read_text())
        self.assertEqual(set(assignments),set(fixtures.m.model.exact_roster()))
        self.assertEqual(sum(c['departure_policy']!='disabled' for c in assignments.values()),14)
        with tempfile.TemporaryDirectory() as td:
            db=fixtures.ContinuousTests().fixture(Path(td))
            result=prepare(db,model_sha='a'*40,now=T,assignments=assignments)
            board=build_board(result,now=T)
            self.assertEqual(board['item_count'],24)
            for row in board['rows']:
                self.assertEqual(row['decision']['depletion_stock_quantity'],0)
                if assignments[row['item_key']]['departure_policy']=='disabled':
                    self.assertIsNone(row['departure_epoch'])
                    self.assertEqual(row['decision']['reason'],'ITEM_NOT_ENABLED_FOR_DEPARTURE_PREVIEW')

    def test_explicit_path_model_is_generated_from_past_only_and_consumed(self):
        from services.travel_read_model import build_board
        from research.causal_stock_paths import CausalStockPaths
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);db=fixtures.ContinuousTests().fixture(root);before=db.read_bytes()
            original=CausalStockPaths.plans
            observed=[]
            def capture(instance,issued,tracker,*,poll_age):
                plans=original(instance,issued,tracker,poll_age=poll_age)
                observed.append(plans['analog70'])
                self.assertTrue(all(instance.starts+instance.MAX_WAIT+instance.flight+190<=issued))
                return plans
            with patch.object(CausalStockPaths,'plans',capture):
                result=prepare(db,model_sha='a'*40,now=T,assignments={
                    'mex:Jaguar Plushie':{'event_history':'true_zero_all',
                        'flight_adapter':'median','departure_policy':'zero_path_analog70'}})
            record=result['item_departure_recommendations']['mex:Jaguar Plushie']
            self.assertEqual(record['departure_epoch'],observed[0]['departure_epoch'])
            self.assertEqual(record['depletion_stock_quantity'],0)
            row=next(r for r in build_board(result,now=T)['rows'] if r['item_key']=='mex:Jaguar Plushie')
            self.assertEqual(row['policy'],'zero_path_analog70')
            self.assertEqual(row['departure_epoch'],record['departure_epoch'])
            self.assertEqual(row['event_model_name'],'true_zero_anchored_cycles_v1')
            self.assertEqual(db.read_bytes(),before)
            output=root/'selected.json';publish(result,output,source=db)
            self.assertEqual(json.loads(output.read_text()),result)

    def test_unintegrated_candidate_and_legacy_anchor_not_silently_substituted(self):
        for policy,history in (('zero_path_tree_stable_peak','true_zero_all'),
                               ('zero_path_regime70','true_zero_all'),
                               ('zero_path_analog70','all_history')):
            with self.assertRaises(ValueError):prepare('unused',model_sha='a'*40,
                assignments={'mex:Jaguar Plushie':{'event_history':history,
                    'flight_adapter':'median','departure_policy':policy}},
                allow_legacy_availability_baselines=True)

    def test_consistent_readonly_per_item_models_and_atomic_consumer_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);db=fixtures.ContinuousTests().fixture(root);before=db.read_bytes()
            snapshot=prepare(db,model_sha='a'*40,now=T,assignments={
                'mex:Jaguar Plushie':{'event_history':'phase_analogs_18','flight_adapter':'current_quarter'},
                'can:Wolverine Plushie':{'event_history':'recent_8','flight_adapter':'midpoint'},
                'chi:Peony':{'event_history':'true_zero_all','flight_adapter':'current_quarter'}},
                allow_legacy_availability_baselines=True)
            self.assertEqual(len(snapshot['items']),24)
            self.assertEqual(snapshot['items']['chi:Peony']['depletion_stock_quantity'],0)
            self.assertEqual(snapshot['items']['chi:Peony']['cycle_window'],'true_zero_all')
            self.assertEqual(snapshot['items']['arg:Monkey Plushie']['depletion_stock_quantity'],0)
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
        with self.assertRaises(ValueError):prepare('unused',model_sha='a'*40,assignments={'jap:Xanax':{'event_history':'all_history','flight_adapter':'median'}})
        with self.assertRaises(ValueError):prepare('unused',model_sha='a'*40,assignments={'invented:Item':{}})
        with self.assertRaises(ValueError):prepare('unused',model_sha='a'*40,assignments={'jap:Xanax':{'event_history':'automatic_winner','flight_adapter':'median'}})


if __name__=='__main__': unittest.main()
