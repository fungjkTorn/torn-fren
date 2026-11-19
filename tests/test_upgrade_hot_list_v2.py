import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('upgrade',Path('deploy/scripts/upgrade_hot_list_v2.py'))
up=importlib.util.module_from_spec(spec);spec.loader.exec_module(up)

class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);self.root=root/'live';self.backups=root/'backups'
        target={name:Path(name).read_bytes() for name in up.EXPECTED}
        self.old=dict(target)
        self.old[up.MODULE]=b'# original Hot List module\n'
        self.old[up.CORE]=b'const HOT_EXCLUSIONS=new Set(["uni:Xanax"]);\n'
        bridge=target[up.BRIDGE].decode();a=bridge.index(up.START);b=bridge.index(up.END,a)
        self.old[up.BRIDGE]=(bridge[:a]+'            if path=="/api/beanstalk-hot-list":\n                payload=await run_in_threadpool(public_hot_list)\n'+bridge[b:]).encode()
        for name,raw in self.old.items():
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        blobs={name:hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest() for name,raw in target.items()}
        for patcher in [patch.object(up,'ROOT',self.root),patch.object(up,'BACKUPS',self.backups),patch.object(up,'EXPECTED',{n:up.sha(r) for n,r in self.old.items()}),patch.object(up,'BLOBS',blobs),patch.object(up,'fetch',side_effect=lambda url:target[url.removeprefix(up.BASE)]),patch.object(up.os,'geteuid',return_value=0),patch.object(up,'restart'),patch.object(up,'verify',return_value={'v2_picks':8})]:
            patcher.start();self.addCleanup(patcher.stop)

    def test_preflight_does_not_write(self):
        self.assertEqual('PREFLIGHT_PASSED',up.install()['status'])
        self.assertFalse(self.backups.exists())
        for n,r in self.old.items():self.assertEqual(r,(self.root/n).read_bytes())

    def test_apply_preserves_other_bridge_source_and_manual_rollback(self):
        result=up.install(True);self.assertEqual('DEPLOYED',result['status'])
        actual=(self.root/up.BRIDGE).read_text();old=self.old[up.BRIDGE].decode()
        self.assertEqual(old[:old.index(up.START)],actual[:actual.index(up.START)])
        self.assertEqual(old[old.index(up.END):],actual[actual.index(up.END):])
        self.assertEqual('ROLLBACK_COMPLETE',up.rollback(result['backup_directory'])['status'])
        for n,r in self.old.items():self.assertEqual(r,(self.root/n).read_bytes())

    def test_failed_verification_restores_all_three_files(self):
        up.verify.side_effect=RuntimeError('fixture outage')
        result=up.install(True);self.assertEqual('ROLLED_BACK',result['status'])
        for n,r in self.old.items():self.assertEqual(r,(self.root/n).read_bytes())

    def test_changed_source_stops_before_backup_or_write(self):
        (self.root/up.MODULE).write_text('# newer edit')
        with self.assertRaisesRegex(RuntimeError,'changed since audit'):up.install(True)
        self.assertFalse(self.backups.exists())

    def test_bad_download_stops_before_writes(self):
        up.fetch.side_effect=lambda url:b'# incorrect download'
        with self.assertRaisesRegex(RuntimeError,'Git blob'):up.install(True)
        self.assertFalse(self.backups.exists())

    def test_rollback_refuses_newer_changes(self):
        result=up.install(True);(self.root/up.MODULE).write_text('# concurrent update')
        with self.assertRaisesRegex(RuntimeError,'Newer file'):up.rollback(result['backup_directory'])

if __name__=='__main__':unittest.main()
