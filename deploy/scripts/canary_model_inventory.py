"""Read-only, metadata-only inventory of the five owner-local specialists.

No collector reads, model inference, service changes, journal writes, directory
searches or model-weight output. Presence is not parity or release approval.
"""
import hashlib
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path

PINS={'lion':'a8a5e7d989c701fa75975dd9b8d73c128e5fd895298443c2cfd6bb3d72e824bd',
      'panda':'84037c778301fa5a3825007dd439abec7c971ec05b176efae3bffe99fc827280'}
KEYS={'lion':'sou:Lion Plushie','panda':'chi:Panda Plushie'}


def regular(path):
    p=Path(path)
    return p.is_file() and not p.is_symlink() and not p.parent.is_symlink()


def selector(path,target,now=None):
    out=dict(item_key=KEYS[target],kind='PINNED_SELECTOR',release_approved=False)
    if not regular(path):return dict(out,status='ARTIFACT_ABSENT')
    try:
        p=Path(path)
        if p.stat().st_size>2097152:return dict(out,status='ARTIFACT_TOO_LARGE')
        blob=p.read_bytes();digest=hashlib.sha256(blob.rstrip(b'\r\n')).hexdigest()
        if digest!=PINS[target]:return dict(out,status='ARTIFACT_PIN_MISMATCH',sha256=digest)
        d=json.loads(blob);clock=int(time.time()) if now is None else now
        valid=(d.get('schema')=='torn-fren-v50-research-selector-v1'
               and d.get('key')==KEYS[target] and d.get('target')==target
               and d.get('research_only') is True and d.get('approved_for_live') is False
               and type(d.get('train_asof')) is int and 0<d['train_asof']<=clock)
        return dict(out,status='PINNED_ARTIFACT_FOUND' if valid else 'ARTIFACT_CONTRACT_MISMATCH',
                    sha256=digest,train_asof=d.get('train_asof'),
                    resolved_disagreements=d.get('resolved_disagreements'))
    except (OSError,ValueError,TypeError):return dict(out,status='ARTIFACT_UNREADABLE')


def cache_inventory(path):
    keys=('arg:Monkey Plushie','swi:Chamois Plushie')
    out=[]
    if not regular(path):return [dict(item_key=k,status='EXPERT_CACHE_ABSENT',release_approved=False) for k in keys]
    try:
        with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=3)) as c:
            c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
            for key in keys:
                n,anchor,resolved=c.execute('SELECT COUNT(*),MAX(anchor_ts),MAX(resolved_at) FROM expert_resolutions WHERE item_key=?',(key,)).fetchone()
                experts=c.execute('SELECT COUNT(DISTINCT expert_id) FROM expert_resolutions WHERE item_key=? AND anchor_ts=?',(key,anchor)).fetchone()[0]
                out.append(dict(item_key=key,status='EXPERT_CACHE_ROWS_FOUND' if n else 'EXPERT_CACHE_EMPTY',
                    rows=n,latest_anchor=anchor,latest_resolution=resolved,latest_anchor_experts=experts,
                    parity_checked=False,release_approved=False))
    except (sqlite3.Error,OSError):return [dict(item_key=k,status='EXPERT_CACHE_UNREADABLE',release_approved=False) for k in keys]
    return out


def japan_inventory(ledger,deployed,reference):
    out=dict(item_key='jap:Xanax',status='JAPAN_LEDGER_ABSENT',release_approved=False)
    try:
        if regular(ledger):
            with closing(sqlite3.connect(Path(ledger).resolve().as_uri()+'?mode=ro',uri=True,timeout=3)) as c:
                c.execute('PRAGMA query_only=ON')
                r=c.execute('SELECT issued_at,status,model_generation,model_config,source_model FROM japan_forward_decisions ORDER BY slot DESC LIMIT 1').fetchone()
            if r:out.update(status='JAPAN_LEDGER_METADATA_FOUND',issued_at=r[0],record_status=r[1],
                            model_generation=r[2],model_config=r[3],source_model=r[4])
        if regular(deployed) and regular(reference):
            digest=hashlib.sha256(Path(deployed).read_bytes()).hexdigest()
            out.update(deployed_source_sha256=digest,
                       matches_checkout_source=digest==hashlib.sha256(Path(reference).read_bytes()).hexdigest())
    except (OSError,sqlite3.Error):out['status']='JAPAN_METADATA_UNREADABLE'
    return out


def inventory(home=Path('/home/ubuntu'),cache=Path('/var/lib/torn-fren-v47/online_expert_cache.db')):
    root=Path(home)/'torn-fren-private-models'
    records=cache_inventory(cache)
    records.extend(selector(root/(target+'_selector_artifact.json'),target) for target in ('panda','lion'))
    records.append(japan_inventory(root/'v84_japan_forward.db',
        Path(home)/'torn-fren-v38-probe/research/japan_xanax/v8_regime_candidate.py',
        Path(__file__).resolve().parents[2]/'research/japan_xanax/v8_regime_candidate.py'))
    return records


if __name__=='__main__':
    for record in inventory():print(json.dumps(record,sort_keys=True))
    print(json.dumps(dict(status='READ_ONLY_INVENTORY_COMPLETE',items=5,
        full_roster_target=24,production_modified=False,weights_exported=False,parity_certified=False)))
