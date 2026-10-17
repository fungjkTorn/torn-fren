"""Measure offline candidate snapshot publication cost; no service installation."""
import copy
import math
import sqlite3
import time
from collections import Counter
from contextlib import closing
from pathlib import Path

from research.build_travel_event_snapshot import prepare
from services.travel_read_model import build_board


def measure(*,source,assignments,model_sha):
    path=Path(source).resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        cutoff=int(dict(db.execute('SELECT key,value FROM research_metadata'))['source_cutoff_epoch'])
    started=time.perf_counter()
    snapshot=prepare(path,model_sha=model_sha,assignments=assignments,now=cutoff)
    elapsed=time.perf_counter()-started
    finished=cutoff+math.ceil(elapsed)
    strict=copy.deepcopy(snapshot)
    for record in strict.get('item_departure_recommendations',{}).values():
        record['execution_policy']='strict_point_v1'
    def view(data):
        board=build_board(data,now=finished)
        return {'statuses':dict(Counter(row['decision']['status'] for row in board['rows'])),
            'clocks_available':sum(row['departure_epoch'] is not None for row in board['rows']),
            'immediate_actionable':sum(row['departure_epoch'] is not None and row['departure_epoch']<=finished for row in board['rows']),
            'source_poll_age_seconds':board['source_poll_age_seconds']}
    return {'status':'OFFLINE_PUBLICATION_COST_PROBE','model_sha':model_sha,
        'snapshot_issue_epoch':cutoff,'build_elapsed_seconds':elapsed,
        'simulated_finish_epoch':finished,'strict_at_finish':view(strict),
        'selected_profile_at_finish':view(snapshot),
        'interpretation':'Historical snapshot build-cost diagnostic, not live publication or real network delay',
        'includes_network_or_user_delay':False,'production_changed':False}
