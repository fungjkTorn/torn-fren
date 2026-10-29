"""Refresh a private inference copy with a small, causal collector tail.

The full fourteen-day export remains the history source. Only recent rows for
approved items, poll receipts, country clocks and gap boundaries are read from
the collector. The collector is opened read-only and never attached for writes.
"""
from contextlib import closing
from pathlib import Path
import sqlite3
import time

from services.first_release_schedule import FIRST_RELEASE_MODELS

MAX_EXPORT_LAG=600
MAX_ROWS=20000


def refresh_tail(snapshot,collector,*,cutoff):
    snapshot=Path(snapshot).resolve(strict=True);collector=Path(collector).resolve(strict=True)
    if snapshot==collector:raise ValueError('inference copy must differ from collector')
    if type(cutoff) is not int:raise ValueError('integer causal cutoff required')
    deadline=time.monotonic()+6
    with closing(sqlite3.connect(collector.as_uri()+'?mode=ro',uri=True,timeout=3)) as live, closing(sqlite3.connect(snapshot)) as dest:
        live.execute('PRAGMA query_only=ON')
        live.execute('PRAGMA temp_store=MEMORY')
        live.set_progress_handler(lambda:time.monotonic()>deadline,10000)
        base=dest.execute("SELECT MAX(timestamp) FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1").fetchone()[0]
        if type(base) is not int or not 0<=cutoff-base<=MAX_EXPORT_LAG:
            raise ValueError('full export is too old or noncausal for bounded tail refresh')
        since=base-60
        live.execute('BEGIN')
        hb=live.execute("SELECT MAX(timestamp) FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1 AND timestamp<=?",(cutoff,)).fetchone()[0]
        if type(hb) is not int or hb<base or cutoff-hb>90:
            raise ValueError('collector tail has no fresh successful poll')
        def bounded(sql,params=()):
            rows=live.execute(sql+' LIMIT ?',(*params,MAX_ROWS+1)).fetchall()
            if len(rows)>MAX_ROWS:raise ValueError('collector tail row cap exceeded')
            return rows
        total=0
        with dest:
            for key in FIRST_RELEASE_MODELS:
                country,item=key.split(':',1)
                rows=bounded('''SELECT timestamp,country,item_name,quantity,source FROM stock_history
                    WHERE country=? AND item_name=? AND timestamp BETWEEN ? AND ?
                    ORDER BY timestamp,id''',(country,item,since,cutoff))
                total+=len(rows)
                if total>MAX_ROWS:raise ValueError('collector stock tail row cap exceeded')
                dest.execute('DELETE FROM stock_history WHERE country=? AND lower(item_name)=lower(?) AND timestamp>=?',(country,item,since))
                dest.executemany('INSERT INTO stock_history(timestamp,country,item_name,quantity,source) VALUES(?,?,?,?,?)',rows)
            cols={r[1] for r in live.execute('PRAGMA table_info(poll_heartbeats)')}
            provider='source' if 'source' in cols else 'NULL'
            polls=bounded('SELECT timestamp,mode,success,'+provider+' FROM poll_heartbeats WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp,id',(since,cutoff))
            dest.execute('DELETE FROM poll_heartbeats WHERE timestamp>=?',(since,))
            dest.executemany('INSERT INTO poll_heartbeats(timestamp,mode,success,source) VALUES(?,?,?,?)',polls)
            gaps=bounded('SELECT start_timestamp,end_timestamp FROM collection_gaps WHERE start_timestamp<=? AND COALESCE(end_timestamp,9223372036854775807)>=? ORDER BY start_timestamp',(cutoff,since))
            gaps=[(start,end if end is None or end<=cutoff else None) for start,end in gaps]
            dest.execute('DELETE FROM collection_gaps WHERE COALESCE(end_timestamp,9223372036854775807)>=?',(since,))
            dest.executemany('INSERT INTO collection_gaps(start_timestamp,end_timestamp) VALUES(?,?)',gaps)
            has_clocks=live.execute("SELECT 1 FROM sqlite_master WHERE name='country_stock_observations' AND type='table'").fetchone()
            if not has_clocks:raise ValueError('live country stock clocks are required')
            countries=sorted({key.split(':',1)[0] for key in FIRST_RELEASE_MODELS})
            receipts=0
            for country in countries:
                rows=bounded('''SELECT received_epoch,country,source,country_update_epoch,export_epoch,
                    clock_status,export_clock_status,item_count FROM country_stock_observations
                    WHERE country=? AND received_epoch BETWEEN ? AND ? ORDER BY received_epoch,id''',(country,since,cutoff))
                receipts+=len(rows)
                if receipts>MAX_ROWS:raise ValueError('collector country-clock tail row cap exceeded')
                dest.execute('DELETE FROM country_stock_observations WHERE country=? AND received_epoch>=?',(country,since))
                dest.executemany('''INSERT INTO country_stock_observations(received_epoch,country,source,country_update_epoch,export_epoch,
                    clock_status,export_clock_status,item_count) VALUES(?,?,?,?,?,?,?,?)''',rows)
        live.execute('ROLLBACK')
    return {'status':'READ_ONLY_COLLECTOR_TAIL_APPLIED','cutoff_epoch':cutoff,
            'export_heartbeat_epoch':base,'collector_heartbeat_epoch':hb,
            'tail_start_epoch':since,'stock_rows':total,'poll_rows':len(polls),
            'country_rows':receipts,'gap_rows':len(gaps),'collector_written':False}
