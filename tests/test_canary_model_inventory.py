import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from deploy.scripts import canary_model_inventory as m


class InventoryTests(unittest.TestCase):
    def test_missing_inputs_are_never_created(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'absent'
            r=m.inventory(home=p,cache=p/'cache.db')
            self.assertEqual(len(r),5);self.assertFalse(p.exists())
            self.assertTrue(all(x['release_approved'] is False for x in r))

    def test_artifact_pin_validation_and_no_weights_in_output(self):
        import hashlib
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'lion.json';data=dict(schema='torn-fren-v50-research-selector-v1',key='sou:Lion Plushie',target='lion',research_only=True,approved_for_live=False,train_asof=50,model={'private_weights':[1,2]})
            blob=json.dumps(data).encode();p.write_bytes(blob+b'\n');digest=hashlib.sha256(blob).hexdigest()
            with patch.dict(m.PINS,lion=digest):
                r=m.selector(p,'lion',now=100)
                self.assertEqual(r['status'],'PINNED_ARTIFACT_FOUND')
                self.assertNotIn('private_weights',json.dumps(r))
                self.assertEqual(m.selector(p,'lion',now=40)['status'],'ARTIFACT_CONTRACT_MISMATCH')
            self.assertEqual(p.read_bytes(),blob+b'\n')

    def test_cache_metadata_only_and_no_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'cache.db'
            with sqlite3.connect(p) as c:
                c.execute('CREATE TABLE expert_resolutions(item_key,anchor_ts,resolved_at,expert_id)')
                c.execute("INSERT INTO expert_resolutions VALUES('arg:Monkey Plushie',10,20,0)")
            before=p.read_bytes();r=m.cache_inventory(p)
            self.assertEqual(r[0]['rows'],1);self.assertEqual(r[1]['status'],'EXPERT_CACHE_EMPTY')
            self.assertEqual(p.read_bytes(),before)


if __name__=='__main__':unittest.main()
