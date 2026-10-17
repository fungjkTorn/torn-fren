import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research.japan_xanax import handoff_shadow as m


class HandoffShadowTests(unittest.TestCase):
    def test_real_plan_builder_restores_only_zero_handoff_candidate(self):
        from test_renewal_shadow import rows,T
        data=(rows()+[(T-90,0,'a'),(T-60,0,'b')],[T],lambda a,b:False,None,T)
        with patch.object(m,'source_data',return_value=data):plans,cutoff=m.issued_plans('unused',T)
        self.assertEqual(cutoff,T);self.assertIsNone(plans['sequence_blocks_peak']['departure'])
        self.assertIsNotNone(plans['zero_handoff180']['departure'])
        self.assertTrue(plans['zero_handoff180']['borrowed_zero_phase'])

    def test_pairs_recorded_atomically_with_publication_floor_and_no_writes_to_source(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'source.db';source.write_bytes(b'untouched');journal=Path(td)/'new.sqlite'
            plans={k:dict(departure=1000,status='SHADOW') for k in m.MODES}
            with patch.object(m,'issued_plans',return_value=(plans,990)),patch.object(m.time,'time',side_effect=[1000,1002]),patch.object(m.time,'monotonic',side_effect=[0,0,0,1,61]),patch.object(m.time,'sleep'),patch('builtins.print'):
                m.record(source,journal,model_sha='a'*40,duration=60)
            with sqlite3.connect(journal) as db:
                values=[json.loads(r[0]) for r in db.execute('SELECT record FROM plans')]
            self.assertEqual({r['mode'] for r in values},set(m.MODES));self.assertEqual(len(values),4)
            for r in values:
                self.assertEqual(r['departure'],1015);self.assertEqual(r['arrival'],1015+m.FLIGHT)
                self.assertEqual(r['poll_age_seconds'],10);self.assertFalse(r['website_publication'])
            self.assertEqual(source.read_bytes(),b'untouched')
            with self.assertRaises(ValueError):m.record(source,journal,model_sha='a'*40,duration=60)

    def test_delayed_or_stale_publication_saves_no_partial_comparison(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'source.db';source.write_bytes(b'untouched');journal=Path(td)/'new.sqlite'
            plans={k:dict(departure=None,status='ABSTAIN') for k in m.MODES}
            with patch.object(m,'issued_plans',return_value=(plans,820)),patch.object(m.time,'time',side_effect=[1000,1002]),patch.object(m.time,'monotonic',side_effect=[0,0,0,1,61]),patch.object(m.time,'sleep'),patch('builtins.print'):
                m.record(source,journal,model_sha='a'*40,duration=60)
            with sqlite3.connect(journal) as db:self.assertEqual(db.execute('SELECT count(*) FROM plans').fetchone()[0],0)

    def test_incomplete_recorded_followup_is_pending_not_a_failed_or_abstained_start(self):
        class Evidence:
            cutoff=100000
            def score(self,arrival):return ('SUCCESS','TEST',None)
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'source.db';source.write_bytes(b'untouched');journal=Path(td)/'new.sqlite'
            plans={k:dict(departure=None,status='ABSTAIN') for k in m.MODES}
            with patch.object(m,'issued_plans',return_value=(plans,990)),patch.object(m.time,'time',side_effect=[1000,1002]),patch.object(m.time,'monotonic',side_effect=[0,0,0,1,61]),patch.object(m.time,'sleep'),patch('builtins.print'):
                m.record(source,journal,model_sha='a'*40,duration=60)
            data=([],[],None,Evidence(),100000)
            with patch.object(m,'source_data',return_value=data),patch('research.japan_xanax.renewal_shadow.source_data',return_value=data):
                result=m.score(source,journal,model_sha='a'*40)
            for r in result['replanned_five_minute_starts'].values():
                self.assertEqual(r.get('PENDING',0),1);self.assertEqual(r.get('ABSTAIN',0),0)
            self.assertEqual(source.read_bytes(),b'untouched')


if __name__=='__main__':unittest.main()
