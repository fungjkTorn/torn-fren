import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from research.japan_xanax import handoff_shadow as m


class HandoffShadowTests(unittest.TestCase):
    def test_fresh_process_with_vm_legacy_stage_uses_pinned_checkout(self):
        from test_v160_prospective_v151_shadow import collector_fixture
        from test_renewal_shadow import T
        with tempfile.TemporaryDirectory() as td:
            directory=Path(td);stage=directory/'legacy';stage.mkdir()
            for entry in (m.ROOT/'research').iterdir():
                if entry.name not in ('continuous_departure_replay.py','__pycache__'):
                    (stage/entry.name).symlink_to(entry,target_is_directory=entry.is_dir())
            source=collector_fixture(directory,issued=T);before=source.read_bytes()
            env=dict(os.environ,TORNFREN_REPLAY_WORK=str(m.ROOT),TORNFREN_REPLAY_PINNED_RESEARCH=str(stage),PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1')
            script='''
import sys
from pathlib import Path
from research.japan_xanax.handoff_shadow import issued_plans,ROOT,MODES
plans,cutoff=issued_plans(sys.argv[1],int(sys.argv[2]))
import research
import research.continuous_departure_replay as replay
assert set(plans)==set(MODES)
assert Path(replay.__file__).resolve()==ROOT/'research/continuous_departure_replay.py'
assert list(research.__path__)==[str(ROOT/'research')]
print('PINNED_STARTUP_OK')
'''
            result=subprocess.run([sys.executable,'-B','-c',script,str(source),str(T)],cwd=m.ROOT,env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('PINNED_STARTUP_OK',result.stdout);self.assertEqual(source.read_bytes(),before)
            # Existing source pin can also be recovered without edits by
            # explicitly setting the correct checkout paths before any imports.
            env['TORNFREN_REPLAY_PINNED_RESEARCH']=str(m.ROOT/'research')
            legacy_order='from research.quantity_rate_cycles import QuantityRateCycles\n'+script
            result=subprocess.run([sys.executable,'-B','-c',legacy_order,str(source),str(T)],cwd=m.ROOT,env=env,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('PINNED_STARTUP_OK',result.stdout);self.assertEqual(source.read_bytes(),before)

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
