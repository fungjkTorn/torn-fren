"""V57 bounded, privacy-safe exception fingerprints for private research only.

Error families and traceback location are logged without exception text,
raw SQL, DB paths, user secrets or API keys. Result statuses and routing
remain unchanged. Used by V18/V19 native workers and Red Fox.
"""
from __future__ import annotations

import sqlite3
import traceback

_SQLITE_FAMILIES = {
    sqlite3.SQLITE_BUSY: "SQLITE_BUSY",
    sqlite3.SQLITE_LOCKED: "SQLITE_LOCKED",
    sqlite3.SQLITE_CANTOPEN: "SQLITE_CANTOPEN",
    sqlite3.SQLITE_READONLY: "SQLITE_READONLY",
    sqlite3.SQLITE_IOERR: "SQLITE_IOERR",
    sqlite3.SQLITE_FULL: "SQLITE_FULL",
    sqlite3.SQLITE_CORRUPT: "SQLITE_CORRUPT",
    sqlite3.SQLITE_SCHEMA: "SQLITE_SCHEMA",
    sqlite3.SQLITE_NOTADB: "SQLITE_NOTADB",
    sqlite3.SQLITE_PERM: "SQLITE_PERM",
    sqlite3.SQLITE_NOMEM: "SQLITE_NOMEM",
}
_ALLOWED_LOCATIONS = {
    "history_service.py", "private_v18_champion_worker_v35.py",
    "frozen_candidate_worker_v31.py", "common.py",
    "plushie_flower_dynamic_planner_v18.py",
    "plushie_flower_dynamic_planner_v19.py",
    "plushie_flower_dynamic_planner_v20.py",
    "v38_v18_single_tick.py","v38_v19_single_tick.py",
    "v38_red_fox_single_tick.py", "v38_readonly_retry.py",
}
_VALID_FUNCTION = {
    "_connect","_get_all_item_rows_with_source","get_collection_gaps",
    "inspect_live_source","read_source_once","read_with_retry",
    "load_item","single_tick","predict","build","__init__",
    "vals","plan","_state","_best_ref","rolling",
    "_install_frozen_readonly_history",
}


def fingerprint(exc):
    tag="OTHER_RESEARCH_EXCEPTION"
    if isinstance(exc,sqlite3.OperationalError):
        number=getattr(exc,"sqlite_errorcode",None)
        base=(number & 255) if isinstance(number,int) else None
        tag=_SQLITE_FAMILIES.get(base,"SQLITE_OPERATIONAL_OTHER")
        # SQLite can report generic SQLITE_ERROR or absent extended
        # code. Whitelist known short messages; never echo raw text.
        if tag=="SQLITE_OPERATIONAL_OTHER":
            msg=str(exc).lower()
            for phrase,safe in (
                ("unable to open database file","SQLITE_CANTOPEN"),
                ("database is locked","SQLITE_BUSY"),
                ("database table is locked","SQLITE_LOCKED"),
                ("database schema is locked","SQLITE_LOCKED"),
                ("attempt to write a readonly database","SQLITE_READONLY"),
                ("readonly database","SQLITE_READONLY"),
                ("no such table:","SQLITE_MISSING_TABLE"),
                ("disk i/o error","SQLITE_IOERR"),
            ):
                if phrase in msg:
                    tag=safe
                    break
    elif isinstance(exc,ValueError):
        msg=str(exc)
        if msg=="future stock rows relative to requested as-of":
            tag="SOURCE_ADVANCED_AFTER_SNAPSHOT_CHECK"
        elif msg.startswith("no rows for "):
            tag="TARGET_HISTORY_UNAVAILABLE"
        elif "zero-size array" in msg:
            tag="EMPTY_ARRAY_REDUCTION"
        elif "nan" in msg.lower() or "inf" in msg.lower():
            tag="INVALID_NUMERICAL_FEATURE"
        else:
            tag="VALUE_ERROR_OTHER"
    elif isinstance(exc,KeyError):
        tag="MISSING_MODEL_FEATURE"
    elif isinstance(exc,IndexError):
        tag="INDEX_OUT_OF_RANGE"
    else:
        tag="OTHER_"+type(exc).__name__.upper()[:30]
    result={"error_type":type(exc).__name__,"error_tag":tag}
    # Last known project module frame; no absolute paths or SQL contents.
    frames=traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else []
    for f in reversed(frames):
        basename=f.filename.rsplit("/",1)[-1]
        if basename in _ALLOWED_LOCATIONS:
            result["error_module"]=basename
            result["error_line"]=int(f.lineno)
            if f.name in _VALID_FUNCTION:
                result["error_function"]=f.name
            break
    return result
