"""Separately predeclared Chamois/Camel windows; no model selection or promotion."""
import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path

ITEM='swi:Chamois Plushie'
BASELINE='zero_path_aligned_analog70'
CHALLENGER='zero_path_cycle_median70'
MATURITY=28800+6960+190+300


SPECS={
    'chamois':dict(name='chamois_cycle_forward_v1',item=ITEM,baseline=BASELINE,challenger=CHALLENGER,maturity=MATURITY),
    'camel_tree':dict(name='camel_tree_forward_v1',item='uae:Camel Plushie',
        baseline='zero_path_inventory_flow_peak',challenger='zero_path_tree_stable_peak',
        secondary='zero_path_aligned_analog50',maturity=28800+10800+190+300),
}


def validate(protocol,*,kind='chamois'):
    if kind not in SPECS:raise ValueError('Unsupported forward kind')
    spec=SPECS[kind];p=protocol
    if p.get('protocol_version')!=1 or p.get('name')!=spec['name']:
        raise ValueError('Unrecognized cycle forward protocol')
    if not re.fullmatch('[0-9a-f]{40}',p.get('model_sha','')):
        raise ValueError('Invalid exact source pin')
    for k in ('declared_epoch','issue_start_epoch','issue_end_epoch','truth_ready_epoch'):
        if type(p.get(k)) is not int:raise ValueError('Invalid protocol epoch')
    if not 0<p['declared_epoch']<p['issue_start_epoch'] or p['issue_start_epoch']%300:
        raise ValueError('Window must be declared before aligned start')
    if p['issue_end_epoch']-p['issue_start_epoch']!=86400:
        raise ValueError('Expected fixed 24-hour issue window')
    if p['truth_ready_epoch']<p['issue_end_epoch']+spec['maturity']:
        raise ValueError('Insufficient outcome maturity')
    if p.get('item_keys')!=[spec['item']] or p.get('primary_comparisons')!={spec['challenger']:spec['baseline']}:
        raise ValueError('Changed predeclared primary comparison')
    if 'secondary' in spec and p.get('secondary_comparisons')!={spec['challenger']:spec['secondary']}:
        raise ValueError('Changed secondary cost comparator')
    if p.get('primary_metric')!='replanned_all_five_minute_starts' or p.get('frozen') is not True:
        raise ValueError('Unsupported evaluation protocol')
    return p


def gate(protocol_path,source,state_root,*,kind='chamois'):
    raw=Path(protocol_path).read_bytes();p=validate(json.loads(raw),kind=kind)
    digest=hashlib.sha256(raw).hexdigest()
    state=None if state_root is None else Path(state_root)/('cycle_forward_'+digest+'.done')
    source=Path(source).resolve(strict=True)
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as cx:
        cx.execute('PRAGMA query_only=ON')
        m=dict(cx.execute('SELECT key,value FROM research_metadata'))
    if m.get('sanitized_stock_only')!='true' or m.get('roster_size')!='24':
        raise ValueError('Unrecognized isolated research snapshot')
    cutoff=int(m['source_cutoff_epoch'])
    return dict(should_run=cutoff>=p['truth_ready_epoch'] and (state is None or not state.exists()),
        digest=digest,state_path=str(state) if state is not None else None,snapshot_cutoff=cutoff,
        truth_ready_epoch=p['truth_ready_epoch'],model_sha=p['model_sha'])


def evaluate(protocol_path,source,*,source_sha,replayer=None,kind='chamois'):
    p=validate(json.loads(Path(protocol_path).read_text()),kind=kind);spec=SPECS[kind]
    if source_sha!=p['model_sha']:raise ValueError('Executing source differs from frozen source')
    if replayer is None:
        from research.continuous_departure_replay import replay
        replayer=replay
    # Use the ordinary read-only gate even for direct/manual invocation.
    ready=gate(protocol_path,source,None,kind=kind)
    if not ready['should_run']:raise ValueError('Forward truth is not mature')
    r=replayer(source=source,days=1,issue_end=p['issue_end_epoch'],
        item_keys=p['item_keys'],focused_zero=True,model_sha=p['model_sha'])
    if r['issue_window_end_epoch']!=p['issue_end_epoch'] or r['asof_epoch']<p['truth_ready_epoch']:
        raise ValueError('Replay did not honor frozen window')
    if set(r['items'])!={spec['item']}:raise ValueError('Replay item mismatch')
    item=r['items'][spec['item']]
    for policy in (spec['baseline'],spec['challenger'])+((spec['secondary'],) if 'secondary' in spec else ()):
        s=item['policies'][policy]['replanned_all_five_minute_starts']
        if s['starts']!=288 or s.get('PENDING',0):
            raise ValueError('Incomplete fixed-window start cohort or maturity')
    r['predeclared_cycle_protocol']=p
    r['protocol_digest']=ready['digest']
    r['automatic_promotion']=False
    r['training_protocol']='Primary models warm start from retained observed past; only labels/paths mature before each issue or canonical refit. No retuning. Cold-start adaptive-selector/residual diagnostics are not primary comparisons.'
    return r


def main():
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=('gate','evaluate'))
    ap.add_argument('--protocol',required=True);ap.add_argument('--source',required=True)
    ap.add_argument('--state-root');ap.add_argument('--github-output');ap.add_argument('--source-sha')
    ap.add_argument('--kind',choices=tuple(SPECS),default='chamois')
    a=ap.parse_args()
    if a.action=='gate':
        if not a.state_root:ap.error('--state-root required for gate')
        r=gate(a.protocol,a.source,a.state_root,kind=a.kind)
        if a.github_output:
            with open(a.github_output,'a') as out:
                for k in ('should_run','state_path','digest'):
                    print(k+'='+str(r[k]).lower() if type(r[k]) is bool else k+'='+str(r[k]),file=out)
    else:r=evaluate(a.protocol,a.source,source_sha=a.source_sha,kind=a.kind)
    print(json.dumps(r,sort_keys=True))


if __name__=='__main__':main()
