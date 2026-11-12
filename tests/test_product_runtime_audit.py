import json
import unittest
from urllib.error import URLError
from research.product_runtime_audit import audit, MAX_BYTES


class RuntimeAuditTests(unittest.TestCase):
    def test_counts_missing_duplicates_and_no_raw_payload_or_accuracy_claim(self):
        payload={'latest':[{'item_key':'jap:Xanax','status':'STALE','private':'do-not-copy'}]*2}
        report=audit(fetch=lambda p: (200,json.dumps(payload).encode()) if 'experimental/v41' in p else (404,b''))
        r=report['routes']['/api/experimental/v41/predictions']
        self.assertEqual(r['unique_item_count'],1)
        self.assertEqual(len(r['missing_configured_items']),23)
        self.assertEqual(r['duplicate_item_keys'],['jap:Xanax'])
        self.assertEqual(report['additional_item_identities_required'],4)
        self.assertNotIn('do-not-copy',json.dumps(report))
        self.assertFalse(report['accuracy_verified'])

    def test_network_bad_json_and_size_errors_are_bounded(self):
        def fetch(p):
            if p=='/': raise URLError('connection refused')
            if p=='/experimental': return 200,b'x'*(MAX_BYTES+1)
            return 200,b'not-json'
        r=audit(fetch=fetch)['routes']
        self.assertEqual(r['/']['error'],'UNREACHABLE')
        self.assertEqual(r['/experimental']['error'],'RESPONSE_TOO_LARGE')
        self.assertEqual(r['/api/travel-decisions']['error'],'INVALID_JSON')


if __name__=='__main__': unittest.main()
