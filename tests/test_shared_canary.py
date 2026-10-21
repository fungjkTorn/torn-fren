import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from deploy.scripts import shared_canary as m
import test_continuous_departure_replay as fixtures
from research.build_travel_event_snapshot import prepare
T=fixtures.T


class CanaryTests(unittest.TestCase):
    def make(self,root):
        db=fixtures.ContinuousTests().fixture(root)
        assignments=json.loads((m.ROOT/m.PROFILE).read_text())
        snapshot=prepare(db,model_sha='a'*40,now=T,assignments=assignments)
        state=root/'state';state.mkdir();(state/'shared.json').write_text(json.dumps(snapshot))
        html=(m.ROOT/'tests/fixtures/experimental_owner_20261012.html').read_bytes()
        def fetch(path):
            if path=='/experimental':return html
            if path=='/':return b'<html><head></head><body>Original V2</body></html>'
            if path=='/api/catalog':return b'{"countries":[]}'
            if path=='/champion_graph.js':return b'/* original graph helper */'
            if path.startswith('/api/history?'):return b'{"rows":[{"quantity":200}],"analysis":{"prediction_v2":{"original":true}}}'
            raise AssertionError(path)
        return m.Canary(state,'a'*40,fetch=fetch),db

    def test_all_views_same_board_identity_and_legacy_history_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            app,db=self.make(Path(td));before=db.read_bytes()
            for path in ('/','/experimental','/travel-decisions'):
                status,kind,body=app.route(path,T+10);self.assertEqual(status,200);self.assertIn('text/html',kind)
            root=app.route('/',T)[2].decode();self.assertIn('PRIVATE CANARY',root)
            self.assertIn('/shared_canary_graph_boot.js',root)
            board=json.loads(app.route('/api/travel-decisions',T+10)[2])
            self.assertEqual(len(board['rows']),24)
            experimental=json.loads(app.route('/api/experimental/v41/predictions',T+10)[2])
            by_key={r['item_key']:r for r in experimental['latest']}
            for row in board['rows']:
                self.assertEqual(by_key[row['item_key']]['departure'],row['departure_epoch'])
                self.assertEqual(by_key[row['item_key']]['arrival'],row['arrival_epoch'])
            history=json.loads(app.route('/api/history?country=mex&item=Jaguar+Plushie&minutes=1440',T+10)[2])
            self.assertTrue(history['analysis']['prediction_v2']['original'])
            self.assertEqual(history['rows'][0]['quantity'],200)
            self.assertEqual(history['analysis']['shared_departure_preview']['row']['item_key'],'mex:Jaguar Plushie')
            self.assertEqual(db.read_bytes(),before)
            self.assertFalse(app.health(T+10)[1]['accuracy_verified'])

    def test_stale_mixed_source_and_missing_feed_do_not_reactivate_incumbents(self):
        with tempfile.TemporaryDirectory() as td:
            app,_=self.make(Path(td));status,health=app.health(T+200)
            self.assertEqual(status,503)
            stale=json.loads(app.route('/api/travel-decisions',T+200)[2])
            self.assertTrue(all(r['departure_epoch'] is None for r in stale['rows']))
            snapshot=json.loads((app.state/'shared.json').read_text());snapshot['model_sha']='b'*40
            (app.state/'shared.json').write_text(json.dumps(snapshot))
            with self.assertRaises(ValueError):app.board(T)
            self.assertEqual(app.health(T)[0],503)
            self.assertIsNone(json.loads(app.route('/api/history?country=mex&item=Jaguar+Plushie',T)[2])['analysis']['shared_departure_preview']['row'])

    def test_proxy_surface_and_ports_are_bounded(self):
        with tempfile.TemporaryDirectory() as td:
            app,_=self.make(Path(td))
            for target in ('http://example.com/api/catalog','/api/history?country=mex&item=x&minutes=10081',
                    '/api/travel-decisions?country=mex','/api/travel-decisions?flight_seconds=10&country=mex',
                    '/api/catalog?x=1&x=2'):
                with self.assertRaises(ValueError):app.route(target,T)
            self.assertEqual(app.route('/admin',T)[0],404)
            for port in (80,8000,8001,8765):
                with self.assertRaises(ValueError):m.validate_port(port)
            m.validate_port(8770)

    def test_publisher_is_a_bounded_subprocess_with_pinned_paths(self):
        with patch.object(m.subprocess,'run') as run:
            run.return_value.returncode=0
            elapsed=m.run_publisher(Path('/source.db'),Path('/state'),'a'*40)
            call=run.call_args
            self.assertEqual(call.kwargs['timeout'],25)
            self.assertEqual(call.kwargs['env']['TORNFREN_REPLAY_PINNED_RESEARCH'],str(m.ROOT/'research'))
            self.assertIn('research.build_travel_event_snapshot',call.args[0])
            self.assertGreaterEqual(elapsed,0)
