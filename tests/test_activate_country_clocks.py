import hashlib
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from deploy.scripts import activate_country_clocks as m
from deploy.scripts.prepare_country_clock_patch import prepare
from test_prepare_country_clock_patch import SOURCE


class ActivateClockTests(unittest.TestCase):
    def fixture(self,root):
        collector=root/'collector';(collector/'services').mkdir(parents=True)
        history=collector/'services/history_service.py';history.write_text(SOURCE);history.chmod(0o664)
        exporter=root/'installed_exporter.py';exporter.write_text('OLD_EXPORTER=True\n');exporter.chmod(0o644)
        payload=root/'payload';(payload/'services').mkdir(parents=True);(payload/'deploy/research_runner').mkdir(parents=True)
        helper=payload/'services/country_freshness.py';helper.write_text('CLOCK_HELPER=True\n')
        newexporter=payload/'deploy/research_runner/export_snapshot.py';newexporter.write_text('NEW_EXPORTER=True\n')
        diff,manifest=prepare(history,helper,newexporter)
        manifest['installed_exporter_base_sha256']=m.digest(exporter.read_bytes())
        for label,path in [('history',history),('installed_exporter',exporter)]:
            s=path.stat();manifest[label+'_file_metadata']=dict(uid=s.st_uid,gid=s.st_gid,mode=oct(s.st_mode&0o777))
        folder=payload/m.PAYLOAD;folder.mkdir(parents=True)
        (folder/'collector.patch').write_text(diff);(folder/'manifest.json').write_text(json.dumps(manifest))
        return collector,exporter,payload,history

    def test_default_plan_preserves_actual_bytes_and_file_permissions(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);collector,exporter,payload,history=self.fixture(root)
            before=(history.read_bytes(),exporter.read_bytes(),history.stat().st_mode,exporter.stat().st_mode)
            files,summary=m.plan(collector,exporter,payload)
            self.assertEqual(before,(history.read_bytes(),exporter.read_bytes(),history.stat().st_mode,exporter.stat().st_mode))
            self.assertFalse((collector/'services/country_freshness.py').exists())
            self.assertFalse(summary['production_modified']);self.assertEqual(len(files),3)
            with patch('sys.argv',['activate_country_clocks','--collector-root',str(collector),'--exporter',str(exporter),'--payload-root',str(payload)]),patch.object(m,'apply') as apply,redirect_stdout(io.StringIO()):m.main()
            apply.assert_not_called()

    def test_success_only_installs_reviewed_files_and_calls_two_named_services(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);collector,exporter,payload,history=self.fixture(root)
            files,summary=m.plan(collector,exporter,payload);calls=[]
            source=root/'stock.db';source.write_bytes(b'untouched-stock-history');snapshot=root/'snapshot.db';snapshot.write_bytes(b'untouched-snapshot')
            result=m.apply(files,summary,backup_root=root/'backups',source=source,snapshot=snapshot,
                run_service=lambda action,unit:calls.append((action,unit)),
                collector_check=lambda *a:dict(japan_new_receipts=2,latest_successful_poll=1000),
                snapshot_check=lambda *a:dict(country_clock_rows=22,snapshot_cutoff=1000))
            self.assertEqual(calls,[('restart',m.POLLER),('start',m.SNAPSHOT)])
            self.assertEqual(history.stat().st_mode&0o777,0o664);self.assertEqual(exporter.stat().st_mode&0o777,0o644)
            self.assertEqual(source.read_bytes(),b'untouched-stock-history');self.assertEqual(snapshot.read_bytes(),b'untouched-snapshot')
            self.assertEqual(result['kind'],'COUNTRY_CLOCK_ACTIVATED')
            self.assertTrue((Path(result['backup_directory'])/'index.json').exists())

    def test_verification_failure_restores_code_and_keeps_collected_clock_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);collector,exporter,payload,history=self.fixture(root)
            original=(history.read_bytes(),exporter.read_bytes());files,summary=m.plan(collector,exporter,payload);calls=[];clock_rows=[]
            def collector_check(*a):clock_rows.append('new append-only row');return dict(japan_new_receipts=2)
            def failed_snapshot(*a):raise RuntimeError('test verification failure')
            with self.assertRaisesRegex(RuntimeError,'original code restored'):
                m.apply(files,summary,backup_root=root/'backups',source='unused',snapshot='unused',
                    run_service=lambda action,unit:calls.append((action,unit)),collector_check=collector_check,snapshot_check=failed_snapshot)
            self.assertEqual(original,(history.read_bytes(),exporter.read_bytes()))
            self.assertFalse((collector/'services/country_freshness.py').exists())
            self.assertEqual(calls,[('restart',m.POLLER),('start',m.SNAPSHOT),('restart',m.POLLER)])
            self.assertEqual(clock_rows,['new append-only row'])

    def test_concurrent_code_change_blocks_apply_before_backups_or_service_calls(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);collector,exporter,payload,history=self.fixture(root)
            files,summary=m.plan(collector,exporter,payload);history.write_text(SOURCE+'\nCHANGED=True\n');calls=[]
            with self.assertRaises(ValueError):
                m.apply(files,summary,backup_root=root/'backups',source='unused',snapshot='unused',run_service=lambda *a:calls.append(a))
            self.assertFalse((root/'backups').exists());self.assertEqual(calls,[])


if __name__=='__main__':unittest.main()
