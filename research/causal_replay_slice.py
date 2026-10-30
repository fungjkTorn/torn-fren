"""Advance a private issue-truncated SQLite mirror without rebuilding history.

The sealed source is immutable for one replay. Native readers are sequential
with advance(), never concurrent with a mutation. Gap closure remains unknown
until its observed end has passed the issue clock. Source is always read-only.
"""
import sqlite3
from contextlib import closing
from pathlib import Path

from research.matched_champion_audit import causal_copy


class CausalReplaySlice:
    def __init__(self,source,target):
        self.source=Path(source).resolve(strict=True);self.target=Path(target)
        if self.source==self.target.resolve():raise ValueError('Source and private slice must differ')
        if self.target.exists() or self.target.is_symlink():raise ValueError('Use a new replay slice')
        self.issued=None
        with closing(sqlite3.connect(self.source.as_uri()+'?mode=ro',uri=True)) as src:
            self.countries=[r[0] for r in src.execute('SELECT DISTINCT country FROM country_stock_observations')] if src.execute("SELECT 1 FROM sqlite_master WHERE name='country_stock_observations'").fetchone() else []

    def __enter__(self):return self

    def advance(self,issued):
        if type(issued) is not int or self.issued is not None and issued<=self.issued:
            raise ValueError('Strictly increasing issue clocks required')
        if self.issued is None:causal_copy(self.source,self.target,issued)
        else:
            self.target.chmod(0o600)
            try:
                with closing(sqlite3.connect(self.source.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(self.target)) as dst:
                    src.execute('PRAGMA query_only=ON');src.execute('BEGIN')
                    with dst:
                        dst.executemany('INSERT INTO stock_history VALUES(?,?,?,?,?,?)',src.execute(
                            'SELECT id,timestamp,country,item_name,quantity,source FROM stock_history WHERE timestamp>? AND timestamp<=?',(self.issued,issued)))
                        dst.executemany('INSERT INTO poll_heartbeats(timestamp,mode,success) VALUES(?,?,?)',src.execute(
                            'SELECT timestamp,mode,success FROM poll_heartbeats WHERE timestamp>? AND timestamp<=?',(self.issued,issued)))
                        for country in self.countries:
                            dst.executemany('INSERT INTO country_stock_observations VALUES(?,?,?,?,?,?)',src.execute(
                                'SELECT id,received_epoch,country,source,country_update_epoch,clock_status FROM country_stock_observations WHERE country=? AND received_epoch>? AND received_epoch<=?',(country,self.issued,issued)))
                        # Gaps are small metadata, and existing gap closures can
                        # become newly knowable without adding a new row.
                        dst.execute('DELETE FROM collection_gaps')
                        dst.executemany('INSERT INTO collection_gaps(start_timestamp,end_timestamp) VALUES(?,?)',src.execute(
                            'SELECT start_timestamp,CASE WHEN end_timestamp>? THEN NULL ELSE end_timestamp END FROM collection_gaps WHERE start_timestamp<=?',(issued,issued)))
            finally:self.target.chmod(0o400)
        self.issued=issued
        return self.target

    def __exit__(self,*args):
        if self.target.exists():self.target.chmod(0o600);self.target.unlink()
