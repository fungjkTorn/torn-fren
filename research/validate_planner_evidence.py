"""Validate tracking against an exported live ledger, without model inference."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

from services.first_release_evidence import connect
from services.simulated_trip_evidence import POLICY,summary


def readonly(path):
    return sqlite3.connect(Path(path).resolve(strict=True).as_uri()+'?mode=ro',uri=True)


def preserved_evidence(db):
    """Fingerprint original evidence, excluding the new derived policy only."""
    result={}
    for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall():
        columns={r[1] for r in db.execute('PRAGMA table_info("'+name+'")')}
        query='SELECT * FROM "'+name+'"'
        params=()
        if 'policy' in columns:query+=' WHERE policy!=?';params=(POLICY,)
        digest=hashlib.sha256();count=0
        for row in db.execute(query+' ORDER BY rowid',params):
            digest.update(json.dumps(tuple(row),separators=(',',':')).encode());digest.update(b'\n');count+=1
        if count:result[name]={'rows':count,'sha256':digest.hexdigest()}
    return result


def validate(ledger,stock,checkpoints=()):
    with closing(readonly(ledger)) as original, closing(readonly(stock)) as src, tempfile.TemporaryDirectory(prefix='planner-validation-') as td:
        if original.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('invalid source ledger')
        before=preserved_evidence(original)
        sha=original.execute('SELECT model_sha FROM issues ORDER BY issued DESC LIMIT 1').fetchone()[0]
        pairs=original.execute('SELECT DISTINCT item,model_sha FROM issues WHERE model_sha=? ORDER BY item',(sha,)).fetchall()
        if len(pairs)!=10:raise ValueError('expected active ten-item cohort')
        cutoff=src.execute("SELECT MAX(timestamp) FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1").fetchone()[0]
        start=original.execute('SELECT MIN(issued) FROM issues WHERE model_sha=?',(sha,)).fetchone()[0]
        if not checkpoints:checkpoints=(start+300,start+(cutoff-start)//3,start+2*(cutoff-start)//3)
        stops=sorted({t for t in checkpoints if start<=t<cutoff})+[cutoff]
        with closing(connect(Path(td)/'batch.sqlite')) as batch, closing(connect(Path(td)/'incremental.sqlite')) as incremental:
            original.backup(batch);original.backup(incremental)
            expected={key:summary(batch,src,item_key=key,model_sha=model,cutoff=cutoff) for key,model in pairs}
            batch.commit()
            for stop in stops:
                for key,model in pairs:
                    result=summary(incremental,src,item_key=key,model_sha=model,cutoff=stop)
                    if result['target_identity_audit']['duplicate_target_groups']:raise AssertionError((key,stop,'duplicate targets'))
                    if stop==cutoff and result!=expected[key]:raise AssertionError((key,'incremental differs from batch'))
                incremental.commit()
            trips=incremental.execute('SELECT item,id,payload FROM simulated_trips WHERE policy=? ORDER BY item,id',(POLICY,)).fetchall()
            for key,model in pairs:
                if summary(incremental,src,item_key=key,model_sha=model,cutoff=cutoff)!=expected[key]:raise AssertionError((key,'repeated summary changed'))
            if trips!=incremental.execute('SELECT item,id,payload FROM simulated_trips WHERE policy=? ORDER BY item,id',(POLICY,)).fetchall():
                raise AssertionError('repeated reconciliation changed frozen trips')
            for key,_,payload in trips:
                trip=json.loads(payload)
                issued=json.loads(original.execute('SELECT payload FROM issues WHERE item=? AND issued=?',(key,trip['issued_epoch'])).fetchone()[0])
                decision=issued['decision']
                if (trip['departure_epoch'],trip['arrival_epoch'])!=(decision['estimated_departure_epoch'],decision['estimated_arrival_epoch']):raise AssertionError((key,'frozen geometry differs from published advice'))
                if not trip['published_epoch']<=trip['departure_epoch']<=trip['valid_until']:raise AssertionError((key,'unpublished or stale departure'))
            if preserved_evidence(batch)!=before or preserved_evidence(incremental)!=before:raise AssertionError('original evidence changed')
            fields=('simulated_trips_total','successes','known','failures','unknown','pending','success_fraction','observed_restocks_since_start','restock_profile','target_identity_audit')
            return {'status':'LIVE_LEDGER_TRACKING_VALIDATED','evidence_policy':POLICY,'model_sha':sha,
                    'first_issued':start,'source_cutoff':cutoff,'incremental_checkpoints':stops,
                    'frozen_trips':len(trips),'duplicate_target_groups':0,'batch_equals_incremental':True,
                    'repeated_reconciliation_unchanged':True,'published_geometry_preserved':True,
                    'original_evidence_preserved':True,'model_inference_run':False,
                    'items':{key:{field:value.get(field) for field in fields} for key,value in expected.items()}}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ledger',required=True);p.add_argument('--stock',required=True)
    p.add_argument('--checkpoint',type=int,action='append',default=[])
    a=p.parse_args();print(json.dumps(validate(a.ledger,a.stock,a.checkpoint),indent=2))
