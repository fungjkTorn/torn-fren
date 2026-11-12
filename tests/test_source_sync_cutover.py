import importlib.util,json,tempfile,unittest,zipfile,hashlib
from pathlib import Path
from unittest.mock import patch
from deploy.scripts import source_sync_cutover as m
class CutoverTests(unittest.TestCase):
 def test_dropin_preserves_arguments_without_shell_execution(self):
  with tempfile.TemporaryDirectory() as td,patch.object(m,'SYSTEMD',Path(td)):
   args=['/venv/python','-m','module','--state','/shared/state','literal%value','a b']
   m.write_drop('example.service','/release',args)
   text=m.drop_path('example.service').read_text();self.assertIn('literal%%value',text);self.assertIn("'a b'",text);self.assertIn('ExecStart=\nExecStart=',text)
 def test_rollback_restores_previous_dropins_and_timer_state(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);backup=root/'backup';backup.mkdir();systemd=root/'systemd';unit='test.service';drop=systemd/(unit+'.d')/m.DROP;drop.parent.mkdir(parents=True);drop.write_text('new')
   (backup/(unit+'.conf')).write_text('original')
   plan={'units':{unit:{'old_work':'/old','old_args':['/python','old.py']}},'worker_units':[],'long_units':[unit],'timers':{'on.timer':True,'off.timer':False}}
   (backup/'plan.json').write_text(json.dumps(plan));calls=[]
   with patch.object(m,'SYSTEMD',systemd),patch.object(m,'system',side_effect=lambda *a:calls.append(a)),patch.object(m,'wait_idle'),patch.object(m,'properties',return_value={'WorkingDirectory':'/old','ExecStart':'{ argv[]=/python old.py ; ignore_errors=no ; pid=5; }'}):
    result=m.restore(backup)
   self.assertEqual(drop.read_text(),'original');self.assertIn(('stop','on.timer'),calls);self.assertIn(('start','on.timer'),calls);self.assertNotIn(('start','off.timer'),calls);self.assertFalse(result['databases_restored_or_deleted'])
 def test_extract_separates_private_source_and_shared_data(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);bundle=root/'bundle.zip';files={'web/app.py':b'web','services/final_pair_live.py':b'private'};manifest={p:hashlib.sha256(v).hexdigest() for p,v in files.items()}
   with zipfile.ZipFile(bundle,'w') as z:
    for p,b in files.items():z.writestr('release/'+p,b)
    z.writestr('manifest.json',json.dumps(manifest));z.writestr('baseline.json','{}')
   with patch.object(m,'WEBROOT',root/'original'):m.extract(bundle,root/'public',root/'private')
   self.assertFalse((root/'public/services/final_pair_live.py').exists());self.assertEqual((root/'private/services/final_pair_live.py').read_bytes(),b'private');self.assertTrue((root/'public/data').is_symlink());self.assertEqual((root/'public/data').readlink(),root/'original/data')
 def test_path_traversal_is_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);bundle=root/'bad.zip'
   with zipfile.ZipFile(bundle,'w') as z:z.writestr('manifest.json',json.dumps({'../outside.py':'bad'}));z.writestr('baseline.json','{}')
   with self.assertRaises(ValueError):m.extract(bundle,root/'public',root/'private')
   self.assertFalse((root/'outside.py').exists())
if __name__=='__main__':unittest.main()
