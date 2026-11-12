"""Bounded read-only health for the precomputed live beta; never fit models."""
from collections import Counter
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import time


def read_live_beta_health(now, *, snapshot=None, ledger=None, expected_items=None):
    snapshot=Path(snapshot or os.environ.get('TORN_FREN_FIRST_RELEASE_SNAPSHOT','/var/lib/torn-fren-live-beta/latest.json'))
    ledger=Path(ledger or snapshot.with_name('forecasts.sqlite'))
    expected_items=int(os.environ.get('TORN_FREN_EXPECTED_LIVE_ITEMS','10')) if expected_items is None else expected_items
    result={'status':'unavailable','expected_items':expected_items,'snapshot_available':False,
            'model_sha':None,'publisher_sha':None,'ledger_status':'unavailable'}
    try:
        with snapshot.open('rb') as f:
            raw=f.read(8*1024*1024+1)
        if len(raw)>8*1024*1024:raise ValueError('snapshot exceeds size limit')
        data=json.loads(raw)
        if data.get('schema_version')!=1 or not isinstance(data.get('items'),dict):
            raise ValueError('invalid snapshot schema')
        for name in ('asof_epoch','published_epoch','valid_until_epoch','source_heartbeat_epoch'):
            if type(data.get(name)) is not int:raise ValueError('invalid snapshot clock')
        if data['published_epoch']>now+15 or data['asof_epoch']>data['published_epoch']:
            raise ValueError('future snapshot clock')
        rows=data['items'];states=Counter();countries={};advice=0
        for key,row in rows.items():
            d=row.get('decision') or {};states[d.get('status','UNKNOWN')]+=1
            if type(d.get('estimated_departure_epoch')) is int:advice+=1
            country=key.split(':',1)[0];receipt=row.get('country_clock')
            if not receipt:countries[country]='unverified'
            else:
                received=receipt.get('received_epoch');updated=receipt.get('reported_update_epoch')
                countries[country]='fresh' if receipt.get('clock_status')=='REPORTED' and type(received) is int and type(updated) is int and 0<=now-received<=180 and 0<=now-updated<=180 else 'stale'
        reasons=[]
        if len(rows)!=expected_items:reasons.append('incomplete item roster')
        if now>data['valid_until_epoch']:reasons.append('snapshot expired')
        if not 0<=now-data['source_heartbeat_epoch']<=180:reasons.append('collector evidence stale')
        if 'stale' in countries.values():reasons.append('country evidence stale')
        if 'unverified' in countries.values():reasons.append('country evidence unverified')
        result.update(snapshot_available=True,item_count=len(rows),published_epoch=data['published_epoch'],
            publication_age_seconds=max(0,now-data['published_epoch']),asof_epoch=data['asof_epoch'],
            valid_until_epoch=data['valid_until_epoch'],source_heartbeat_epoch=data['source_heartbeat_epoch'],
            source_age_seconds=now-data['source_heartbeat_epoch'],model_sha=data.get('model_sha'),
            publisher_sha=data.get('publisher_sha',data.get('model_sha')),countries=countries,
            item_states=dict(states),items_with_advice=advice,items_without_advice=len(rows)-advice,
            stock_success_rule=data.get('stock_success_rule'),issues=reasons)
        try:
            deadline=time.monotonic()+1
            with closing(sqlite3.connect(ledger.resolve(strict=True).as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
                db.execute('PRAGMA query_only=ON');db.set_progress_handler(lambda:time.monotonic()>deadline,1000)
                last=db.execute('SELECT issued,published FROM publications ORDER BY issued DESC LIMIT 1').fetchone()
                identity=db.execute('SELECT model_sha FROM issues WHERE item=? AND issued=?',
                    (next(iter(rows)),data['asof_epoch'])).fetchone() if rows else None
            result['ledger_bytes']=ledger.stat().st_size
            result['ledger_last_publication_epoch']=last[1] if last else None
            result['ledger_status']='current' if last and last[0]>=data['asof_epoch'] and identity and identity[0]==data.get('model_sha') else 'behind_or_identity_mismatch'
        except (OSError,sqlite3.Error):result['ledger_status']='unavailable'
        if result['ledger_status']!='current':reasons.append('evidence ledger not verified current')
        result['status']='healthy' if not reasons else 'delayed'
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        result['issues']=['live snapshot unavailable or invalid']
    return result
