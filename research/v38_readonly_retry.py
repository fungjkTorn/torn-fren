"""Private research-only bounded retry for transient live-stock SQLite failures.

Rerun the entire read on a fresh mode=ro connection. Never retry partial
sidecar writes or bypass freshness, gap and future-record safeguards.
"""
from __future__ import annotations
import sqlite3
import time

def retryable(exc):
    code=getattr(exc,"sqlite_errorcode",None)
    if isinstance(code,int):
        return (code & 255) in (sqlite3.SQLITE_CANTOPEN,
                                sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED)
    return str(exc).lower() in (
        "unable to open database file","database is locked",
        "database table is locked","database schema is locked")

def read_with_retry(read,*,sleep=time.sleep,delays=(0.25,0.5,1.0)):
    for attempt in range(len(delays)+1):
        try:
            return read()
        except sqlite3.OperationalError as exc:
            if attempt==len(delays) or not retryable(exc):
                raise
            sleep(delays[attempt])
    raise AssertionError("unreachable")
