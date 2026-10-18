"""Read-only trace of recorded target replacement, publication and expiry."""
import argparse
import bisect
import json
import re
import sqlite3
import time
from collections import Counter,defaultdict
from contextlib import closing
from pathlib import Path


def source_epoch(record):
    if 'source_cutoff' in record:return record['source_cutoff']
    age=record.get('poll_age_seconds')
    return record['issued']-age if type(age) is int and age>=0 else None


def trace(records,*,asof,issue_end=None):
    groups=defaultdict(list)
    for r in records:
        if r['published']>asof:continue
        groups[(r['item_key'],r['mode'])].append(r)
    result={}
    for (item,mode),values in sorted(groups.items()):
        values=sorted(values,key=lambda r:r['published']);counts=Counter();examples=defaultdict(list);targets=set()
        if len({r['published'] for r in values})!=len(values):raise ValueError('Duplicate publication clock')
        departures=[]
        for i,r in enumerate(values):
            if issue_end is not None and r['issued']>issue_end:continue
            issued=r['issued'];dep=r['departure'];published=r['published'];counts['recorded_issues']+=1
            if dep is None:counts['no_forecast']+=1;continue
            targets.add(dep);counts['forecast_issues']+=1
            counts['near_target' if dep<issued+300 else 'distant_target']+=1
            stop=values[i+1]['published'] if i+1<len(values) else asof+1
            source_cutoff=source_epoch(r)
            # Advice can only execute after it was actually published, before
            # replacement/forecast expiry and before source-health expiry.
            if source_cutoff is not None and published<=dep<min(stop,issued+300) and dep<=min(asof,source_cutoff+180):
                departures.append(dep);counts['eligible_departure_records']+=1
            current=r;fate='AWAITING_RECORDED_RECONFIRMATION';changed=None
            for nxt in values[i+1:]:
                if nxt['published']>dep:break
                if nxt['published']>=current['issued']+300:
                    counts['publication_gap_before_target']+=1
                if nxt['departure']!=dep:
                    changed=nxt
                    fate='WITHDRAWN' if nxt['departure'] is None else 'POSTPONED' if nxt['departure']>dep else 'ADVANCED'
                    break
                current=nxt
            if changed is None and dep<=asof:
                source=source_epoch(current)
                if dep>=current['issued']+300:fate='EXPIRED_WITHOUT_RECONFIRMATION'
                elif source is None:fate='SOURCE_HEALTH_UNRECORDED'
                elif dep>source+180:fate='SOURCE_EXPIRED_AT_TARGET'
                elif dep<current['published']:fate='TARGET_ALREADY_PASSED_AT_PUBLICATION'
                else:fate='TARGET_REACHED_WITH_VALID_RECORDED_ADVICE'
            counts[fate]+=1
            if len(examples[fate])<3:
                examples[fate].append(dict(issued=issued,published=published,target=dep,
                    changed_at=changed['published'] if changed else None,
                    replacement=changed['departure'] if changed else None,
                    replacement_status=changed.get('status') if changed else None))
        result.setdefault(item,{})[mode]=dict(counts=dict(counts),distinct_proposed_targets=len(targets),
            distinct_eligible_departures=len(set(departures)),eligible_departure_examples=sorted(set(departures))[:10],examples=dict(examples))
    return dict(asof=asof,items=result,read_only=True,actual_flights=False,
        limitation='Target-fate counts are per proposed issue, highly correlated. Eligible departures use actual publication, exclusive 300sec forecast validity and inclusive 180sec source expiry. No arrival outcomes inferred.')


def read_journal(path,*,expected_sha,asof=None):
    if not re.fullmatch('[0-9a-f]{40}',expected_sha):raise ValueError('Exact journal model pin required')
    with closing(sqlite3.connect(Path(path).resolve(strict=True).as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        if db.execute("SELECT value FROM metadata WHERE key='model_sha'").fetchone()!=(expected_sha,):raise ValueError('Journal model pin mismatch')
        rows=db.execute('SELECT issued,item_key,mode,record FROM plans ORDER BY issued,item_key,mode LIMIT 100001').fetchall()
    if len(rows)>100000:raise ValueError('Record cap exceeded')
    records=[]
    for issued,item,mode,raw in rows:
        r=json.loads(raw)
        if (issued,item,mode,expected_sha)!=(r['issued'],r['item_key'],r['mode'],r['model_sha']):raise ValueError('Record identity mismatch')
        records.append(r)
    return dict(trace(records,asof=int(time.time()) if asof is None else asof),model_sha=expected_sha,records=len(records))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--journal',required=True);p.add_argument('--expected-sha',required=True)
    a=p.parse_args();print(json.dumps(read_journal(a.journal,expected_sha=a.expected_sha),indent=2,sort_keys=True))


if __name__=='__main__':main()
