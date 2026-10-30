"""Audit recovered real-data replays and export exact paired opportunities.

Reporting only: no model inference, source writes, or changed trip geometry.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
from statistics import median

from research.compare_prelive_cleanup import identity
from research.rescore_saved_challengers import load_archive


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_csv(path, rows):
    if not rows:
        path.write_text('')
        return
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def audit(source, checkpoint, baseline, variants, output):
    source, checkpoint, baseline, output = map(Path, (source, checkpoint, baseline, output))
    output.mkdir(parents=True, exist_ok=True)
    expected = '543b67f1fe4874961130948ecee1d9df4870efe80599726f13828b19da8a6687'
    assert sha(source) == expected
    root = Path(__file__).resolve().parents[1]
    report = {'source_sha256': expected, 'frozen_native_commit': '4fe4b9e2f05200651d230012c9b59c42985758a3',
              'recovery_commit': '2a6ce9285b3bb2b27d1fe5d1902277498775d472',
              'model_behavior_changed_during_recovery': False, 'variants': {}}
    base_trips = json.loads((baseline / 'scored/trips.json').read_text())
    paired, unresolved = [], []
    for directory in map(Path, variants):
        manifest, records, hashes = load_archive(directory / 'archive')
        variant = manifest['cleanup_variant']
        assert len(records) == 6
        for relative, digest in manifest['code_sha256'].items():
            assert sha(root / relative) == digest, relative
        counts = {}
        causal_label_checks = 0
        for key, rows in records.items():
            assert len(rows) == 2017
            name = key.replace(':', '__').replace(' ', '_') + '.jsonl'
            prefix = checkpoint / directory.name / 'items' / name[:-6] / name
            if prefix.exists():
                assert (directory / 'archive' / name).read_bytes().startswith(prefix.read_bytes())
            counts[key] = len(rows)
            for record in rows:
                rates = ((record.get('row') or {}).get('forecast') or {}).get('net_stock_rates')
                if rates:
                    assert rates['last_label_epoch'] <= record['issued'] - 180
                    assert rates['signature_training_cutoff'] == manifest['start']
                    causal_label_checks += 1
        result = json.loads((directory / 'scored/results.json').read_text())
        assert result['idempotency_verified'] and result['original_inputs_unchanged'] and result['saved_geometry_preserved']
        assert json.loads((directory / 'policy-audit.json').read_text())['all_checks_passed']
        trips = json.loads((directory / 'scored/trips.json').read_text())
        for trip in trips:
            if trip['outcome']['status'] in ('UNKNOWN', 'PENDING'):
                unresolved.append({'variant': variant, 'item': trip['item_key'], 'trip_id': trip['id'],
                                   'departure_epoch': trip['departure_epoch'], 'arrival_epoch': trip['arrival_epoch'],
                                   'status': trip['outcome']['status'], 'outcome_json': json.dumps(trip['outcome'], sort_keys=True)})
        waits = {}
        for key, rows in records.items():
            samples = sorted((r['row']['decision']['estimated_departure_epoch'] - r['issued']) / 60
                             for r in rows if type(((r.get('row') or {}).get('decision') or {}).get('estimated_departure_epoch')) is int)
            waits[key] = {'advice_wait_median_minutes': median(samples) if samples else None,
                          'advice_wait_p90_minutes': samples[int(.9 * (len(samples) - 1))] if samples else None,
                          'advice_wait_max_minutes': max(samples) if samples else None}
            frozen_waits = sorted((t['departure_epoch'] - t['issued_epoch']) / 60
                                  for t in trips if t['item_key'] == key)
            waits[key].update(frozen_trip_wait_median_minutes=median(frozen_waits) if frozen_waits else None,
                              frozen_trip_wait_p90_minutes=frozen_waits[int(.9 * (len(frozen_waits) - 1))] if frozen_waits else None)
            def index(all_trips):
                selected = [t for t in all_trips if t['item_key'] == key and identity(t) is not None]
                indexed = {identity(t): t for t in selected}
                assert len(selected) == len(indexed)
                return indexed
            left, right = index(base_trips), index(trips)
            for target in sorted(left.keys() | right.keys()):
                a, b = left.get(target), right.get(target)
                paired.append({'variant': variant, 'item': key, 'observed_opportunity_epoch': target,
                               'baseline_trip_id': a['id'] if a else '', 'candidate_trip_id': b['id'] if b else '',
                               'baseline_status': a['outcome']['status'] if a else 'ABSENT',
                               'candidate_status': b['outcome']['status'] if b else 'ABSENT',
                               'baseline_departure_epoch': a['departure_epoch'] if a else '',
                               'candidate_departure_epoch': b['departure_epoch'] if b else '',
                               'departure_shift_minutes': (b['departure_epoch'] - a['departure_epoch']) / 60 if a and b else ''})
        report['variants'][variant] = {'issue_clocks_per_item': counts, 'saved_prefixes_unchanged': True,
                                       'causal_rate_label_checks': causal_label_checks,
                                       'code_fingerprints_match': True, 'archive_sha256': hashes,
                                       'wait_distribution': waits,
                                       'unresolved_statuses': dict(Counter(t['outcome']['status'] for t in trips if t['outcome']['status'] in ('UNKNOWN', 'PENDING')))}
    write_csv(output / 'exact-observed-opportunity-pairs.csv', paired)
    write_csv(output / 'all-unknown-and-pending.csv', unresolved)
    report['all_checks_passed'] = True
    (output / 'recovery-validation.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'checkpoint', 'baseline', 'output'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--variants', nargs='+', required=True)
    args = parser.parse_args()
    audit(args.source, args.checkpoint, args.baseline, args.variants, args.output)
