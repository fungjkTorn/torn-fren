"""Standalone, read-only collector export: seven challengers, stock evidence only.

Safe to stream into python3 over SSH; no project imports or installs needed.
Creates a NEW private file. Does not replace the live research database.
"""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import pwd
import sqlite3
import tempfile
import time

ITEMS = ('arg:Monkey Plushie','can:Wolverine Plushie','cay:Stingray Plushie',
         'chi:Peony','sou:African Violet','sou:Lion Plushie','uni:Xanax')
DDL = '''
CREATE TABLE stock_history(id INTEGER PRIMARY KEY,timestamp INTEGER,country TEXT,item_name TEXT,quantity INTEGER,source TEXT);
CREATE INDEX stock_item ON stock_history(country,lower(item_name),timestamp,id);
CREATE INDEX stock_clock ON stock_history(timestamp);
CREATE TABLE poll_heartbeats(id INTEGER PRIMARY KEY,timestamp INTEGER,mode TEXT,success INTEGER);
CREATE INDEX poll_time ON poll_heartbeats(timestamp);
CREATE TABLE collection_gaps(start_timestamp INTEGER,end_timestamp INTEGER);
CREATE TABLE country_stock_observations(id INTEGER PRIMARY KEY,received_epoch INTEGER,country TEXT,source TEXT,country_update_epoch INTEGER,clock_status TEXT);
CREATE INDEX country_time ON country_stock_observations(country,received_epoch,id);
CREATE TABLE research_metadata(key TEXT PRIMARY KEY,value TEXT);
'''


def export(source,output,*,days=120,owner=None):
    source=Path(source).resolve(strict=True);output=Path(output)
    if output.exists() or output.is_symlink() or source==output.resolve():
        raise ValueError('choose a new output file; source and existing exports cannot be replaced')
    if not 14<=days<=120:
        raise ValueError('history days must be 14..120')
    fd,name=tempfile.mkstemp(prefix='.challenger-export-',dir=output.parent)
    os.close(fd);temp=Path(name);os.chmod(temp,0o600)
    try:
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True,timeout=15)) as src, closing(sqlite3.connect(temp)) as dst:
            src.execute('PRAGMA query_only=ON');src.execute('PRAGMA temp_store=MEMORY');src.execute('BEGIN')
            latest=src.execute("SELECT MAX(timestamp) FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1").fetchone()[0]
            if latest is None:raise ValueError('no collector heartbeat')
            cutoff=min(int(time.time()),latest);start=cutoff-days*86400
            dst.executescript(DDL);counts={}
            for key in ITEMS:
                country,item=key.split(':',1)
                prior=src.execute('''SELECT timestamp,country,item_name,quantity,source FROM stock_history
                    WHERE country=? AND lower(item_name)=lower(?) AND timestamp<? ORDER BY timestamp DESC,id DESC LIMIT 1''',(country,item,start)).fetchone()
                rows=src.execute('''SELECT timestamp,country,item_name,quantity,source FROM stock_history
                    WHERE country=? AND lower(item_name)=lower(?) AND timestamp BETWEEN ? AND ? ORDER BY timestamp,id LIMIT 200001''',(country,item,start,cutoff)).fetchall()
                if len(rows)>200000:raise ValueError('stock row cap exceeded for '+key)
                if prior:rows.insert(0,prior)
                if not rows:raise ValueError('missing item '+key)
                dst.executemany('INSERT INTO stock_history(timestamp,country,item_name,quantity,source) VALUES(?,?,?,?,?)',rows)
                counts[key]=len(rows)
            polls=src.execute('''SELECT timestamp,mode,success FROM poll_heartbeats
                WHERE timestamp BETWEEN ? AND ? AND mode='poll-cycle' ORDER BY timestamp LIMIT 500001''',(start,cutoff)).fetchall()
            if len(polls)>500000:raise ValueError('poll cap exceeded')
            dst.executemany('INSERT INTO poll_heartbeats(timestamp,mode,success) VALUES(?,?,?)',polls)
            dst.executemany('INSERT INTO collection_gaps VALUES(?,?)',src.execute('''SELECT start_timestamp,
                CASE WHEN end_timestamp>? THEN NULL ELSE end_timestamp END FROM collection_gaps
                WHERE start_timestamp<=? AND (end_timestamp IS NULL OR end_timestamp>=?)''',(cutoff,cutoff,start)))
            has_clocks=src.execute("SELECT 1 FROM sqlite_master WHERE name='country_stock_observations'").fetchone()
            if has_clocks:
                for country in sorted({k.split(':')[0] for k in ITEMS}):
                    clocks=src.execute('''SELECT received_epoch,country,source,country_update_epoch,clock_status
                        FROM country_stock_observations WHERE country=? AND received_epoch BETWEEN ? AND ?
                        ORDER BY received_epoch,id LIMIT 500001''',(country,start,cutoff)).fetchall()
                    if len(clocks)>500000:raise ValueError('country clock cap exceeded')
                    dst.executemany('INSERT INTO country_stock_observations(received_epoch,country,source,country_update_epoch,clock_status) VALUES(?,?,?,?,?)',clocks)
            metadata={'schema':'corrected-challenger-history-v1','cutoff':cutoff,'history_days':days,
                'items':counts,'sanitized_stock_only':True,'collector_modified':False,
                'country_clock_table_available':bool(has_clocks)}
            dst.executemany('INSERT INTO research_metadata VALUES(?,?)',[(k,json.dumps(v)) for k,v in metadata.items()])
            dst.commit()
            if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('integrity check failed')
        if owner:
            user=pwd.getpwnam(owner);os.chown(temp,user.pw_uid,user.pw_gid)
        # Hard-link publication fails if another process created this name.
        os.link(temp,output);temp.unlink()
        return dict(metadata,status='SNAPSHOT_READY',output=str(output),bytes=output.stat().st_size)
    finally:
        if temp.exists():temp.unlink()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    p.add_argument('--days',type=int,default=120);p.add_argument('--owner')
    a=p.parse_args();print(json.dumps(export(a.source,a.output,days=a.days,owner=a.owner),sort_keys=True))
