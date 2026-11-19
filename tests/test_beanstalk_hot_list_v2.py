import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_beanstalk_hot_list import catalog, row, NOW, PRICES
from web import beanstalk_hot_list as hot
from web.first_release_bridge import install_first_release

class HotListV2Tests(unittest.TestCase):
    def test_two_best_xanax_distinct_and_legacy_unchanged(self):
        new=hot.build_hot_list(catalog(),{},now=NOW,version=2)
        self.assertEqual(8,len(new['picks']))
        self.assertEqual(['jap:Xanax','can:Xanax'],[p['item_key'] for p in new['picks'][:2]])
        self.assertEqual(2,new['category_quotas']['xanax'])
        self.assertEqual(8,len({p['item_key'] for p in new['picks']}))
        self.assertNotIn('uni:Xanax',[p['item_key'] for p in new['picks']])
        old=hot.build_hot_list(catalog(),{},now=NOW)
        self.assertEqual(7,len(old['picks']))
        self.assertEqual('torn-fren-beanstalk-hot-list-v1',old['schema'])
        self.assertNotIn('valid_until',old)

    def test_no_padding_when_two_eligible_xanax_unavailable(self):
        prices={k:v for k,v in PRICES.items() if k not in ('can:Xanax','sou:Xanax')}
        new=hot.build_hot_list(catalog(prices),{},now=NOW,version=2)
        self.assertEqual('INSUFFICIENT_ELIGIBLE_ITEMS',new['status'])
        self.assertEqual([],new['picks'])

    def test_market_clock_and_departure_expiry_are_separate(self):
        c=catalog();c['profitability']['market_price_fetched_at']=NOW-290
        r=row('jap:Xanax');r['decision']['estimated_departure_deadline_epoch']=NOW+100
        r['source_heartbeat_epoch']=NOW-160
        new=hot.build_hot_list(c,{'rows':[r]},now=NOW,version=2)
        self.assertEqual(hot._iso(NOW+10),new['valid_until'])
        p=new['picks'][0]
        self.assertEqual(hot._iso(NOW+20),p['departure_valid_until'])
        self.assertEqual(hot._iso(NOW-160),p['source_checked_at'])
        self.assertIsNone(new['foreign_price_checked_at'])
        c['profitability']['market_price_fetched_at']=NOW-301
        with self.assertRaises(ValueError):hot.build_hot_list(c,{},now=NOW,version=2)
        unknown=hot.build_hot_list(catalog(),{},now=NOW,version=2)
        self.assertIsNone(unknown['market_price_checked_at'])
        self.assertTrue(all(p['departure_valid_until'] is None for p in unknown['picks']))

    def test_versioned_http_contract(self):
        app=FastAPI();install_first_release(app)
        with TestClient(app) as client:
            with patch('web.beanstalk_hot_list.public_hot_list',side_effect=lambda version:hot.build_hot_list(catalog(),{},now=NOW,version=version)):
                self.assertEqual(7,len(client.get('/api/beanstalk-hot-list').json()['picks']))
                r=client.get('/api/beanstalk-hot-list?version=2')
                self.assertEqual(8,len(r.json()['picks']))
                self.assertEqual('*',r.headers['access-control-allow-origin'])
                self.assertEqual(400,client.get('/api/beanstalk-hot-list?version=3').status_code)

    def test_guarded_installer_upgrades_only_exact_known_handler(self):
        path=Path('deploy/scripts/publish_beanstalk_hot_list.py')
        spec=importlib.util.spec_from_file_location('publisher_v2',path)
        publisher=importlib.util.module_from_spec(spec);spec.loader.exec_module(publisher)
        current=Path('web/first_release_bridge.py').read_text()
        old=current.replace(publisher.INSERT,publisher.LEGACY_INSERT)
        self.assertNotEqual(old,current)
        self.assertEqual(current,publisher.patch_bridge(old))
        self.assertEqual(current,publisher.patch_bridge(current))
        with self.assertRaises(RuntimeError):publisher.patch_bridge(old.replace('payload=await run_in_threadpool(public_hot_list)','payload=await unrelated()'))

if __name__=='__main__':unittest.main()
