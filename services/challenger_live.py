"""Isolated six-item forward publisher; retains the original ten publisher."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import time

from services.forward_beta_roster import CHALLENGER_MODELS
from services.first_release_live import publish
from services.first_release_source import refresh_tail


def bootstrap(collector,output):
    """Copy only stock evidence, all available causal history, never secrets."""
    from deploy.research_runner.export_snapshot import DDL
    output=Path(output)
    if output.exists() or output.is_symlink():raise ValueError('new source filename required')
    with closing(sqlite3.connect(Path(collector).resolve(strict=True).as_uri()+'?mode=ro',uri=True,timeout=15)) as src:
        src.execute('PRAGMA query_only=ON');src.execute('BEGIN')
        cutoff=min(int(time.time()),src.execute("SELECT MAX(timestamp) FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1").fetchone()[0])
        with closing(sqlite3.connect(output)) as dst:
            dst.executescript(DDL)
            for key in CHALLENGER_MODELS:
                country,item=key.split(':',1)
                rows=src.execute('SELECT timestamp,country,item_name,quantity,source FROM stock_history WHERE country=? AND lower(item_name)=lower(?) AND timestamp<=? ORDER BY timestamp,id LIMIT 200001',(country,item,cutoff)).fetchall()
                if not rows or len(rows)>200000:raise ValueError('missing or excessive item history: '+key)
                dst.executemany('INSERT INTO stock_history(timestamp,country,item_name,quantity,source) VALUES(?,?,?,?,?)',rows)
            polls=src.execute("SELECT timestamp,mode,success FROM poll_heartbeats WHERE mode='poll-cycle' AND timestamp<=? ORDER BY timestamp,id LIMIT 500001",(cutoff,)).fetchall()
            if len(polls)>500000:raise ValueError('poll history exceeds bounded export')
            dst.executemany('INSERT INTO poll_heartbeats(timestamp,mode,success) VALUES(?,?,?)',polls)
            gaps=src.execute('SELECT start_timestamp,CASE WHEN end_timestamp>? THEN NULL ELSE end_timestamp END FROM collection_gaps WHERE start_timestamp<=? LIMIT 10001',(cutoff,cutoff)).fetchall()
            if len(gaps)>10000:raise ValueError('gap history exceeds bounded export')
            dst.executemany('INSERT INTO collection_gaps VALUES(?,?)',gaps)
            for country in sorted({k.split(':')[0] for k in CHALLENGER_MODELS}):
                receipts=src.execute('''SELECT received_epoch,country,source,country_update_epoch,clock_status FROM country_stock_observations WHERE country=? AND received_epoch<=? ORDER BY received_epoch,id LIMIT 500001''',(country,cutoff)).fetchall()
                if not receipts or len(receipts)>500000:raise ValueError('country clock history unavailable or excessive')
                dst.executemany("INSERT INTO country_stock_observations(received_epoch,country,source,country_update_epoch,clock_status,export_clock_status,item_count) VALUES(?,?,?,?,?,'UNVERIFIED',0)",receipts)
            dst.execute('INSERT INTO research_metadata VALUES(?,?)',('training_policy',json.dumps('ALL_AVAILABLE_CAUSAL_HISTORY_NO_ROLLING_LOOKBACK')))
            dst.commit()
            if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('source integrity check failed')
    os.chmod(output,0o600)
    return {'status':'CHALLENGER_SOURCE_READY','cutoff':cutoff,'collector_modified':False,'history_truncated':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--collector',required=True)
    p.add_argument('--state',required=True);p.add_argument('--source');p.add_argument('--model-sha',required=True)
    a=p.parse_args();state=Path(a.state);source=Path(a.source) if a.source else state/'stock_history.sqlite'
    info=refresh_tail(source,a.collector,cutoff=int(time.time()),model_roster=CHALLENGER_MODELS)
    result=publish(source,state,model_sha=a.model_sha,publisher_sha=a.model_sha,
        model_roster=CHALLENGER_MODELS,time_budget_seconds=90,item_timeout_seconds=45,challenger_cohort=True)
    result['source_refresh']=info
    print(json.dumps(result))


if __name__=='__main__':main()
