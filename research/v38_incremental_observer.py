"""Bounded, read-only collector delta observer; writes only research sidecar.

Initial bootstrap must catch up before workers trust item source state.
Rowid changes and collection gap revisions invalidate dependent features.
"""
from __future__ import annotations
import sqlite3
from pathlib import Path


def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS v38_source_cursor(
        singleton INTEGER PRIMARY KEY CHECK(singleton=1),
        last_id INTEGER NOT NULL, gap_rev INTEGER NOT NULL,
        caught_up INTEGER NOT NULL DEFAULT 0
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS v38_stock_state(
        item_key TEXT PRIMARY KEY, last_id INTEGER NOT NULL,
        stock_as_of INTEGER NOT NULL, quantity INTEGER NOT NULL
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS v38_feature_cache(
        item_key TEXT NOT NULL, config TEXT NOT NULL, schema_version TEXT NOT NULL,
        clock_slot INTEGER NOT NULL, source_row_id INTEGER NOT NULL,
        gap_rev INTEGER NOT NULL, features_json TEXT NOT NULL,
        PRIMARY KEY(item_key,config,schema_version,clock_slot)
    )""")
    con.commit()


def observe(stock_db, sidecar, max_rows=10000):
    if not 1 <= max_rows <= 50000:
        raise ValueError("batch outside bounds")
    initialize(sidecar)
    p = Path(stock_db).resolve(strict=True)
    with sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=2) as src:
        src.execute("PRAGMA query_only=ON")
        maximum=src.execute("SELECT COALESCE(MAX(id),0) FROM stock_history").fetchone()[0]
        gaps=src.execute("SELECT COALESCE(MAX(id),0) FROM collection_gaps").fetchone()[0]
        old=sidecar.execute("SELECT last_id,gap_rev FROM v38_source_cursor WHERE singleton=1").fetchone()
        last_id=old[0] if old else 0
        reset=maximum<last_id
        if reset: last_id=0
        rows=src.execute("""SELECT id,timestamp,country,item_name,quantity
            FROM stock_history WHERE id>? ORDER BY id LIMIT ?""",
            (last_id,max_rows)).fetchall()
    affected=set()
    with sidecar:
        if reset:
            sidecar.execute("DELETE FROM v38_stock_state")
            sidecar.execute("DELETE FROM v38_feature_cache")
        for rowid,stamp,country,item,qty in rows:
            key=f"{str(country).lower()}:{item}"
            existing=sidecar.execute(
                "SELECT quantity FROM v38_stock_state WHERE item_key=?", (key,)
            ).fetchone()
            if existing is None or existing[0]!=int(qty):
                affected.add(key)
            sidecar.execute("""INSERT INTO v38_stock_state VALUES(?,?,?,?)
                ON CONFLICT(item_key) DO UPDATE SET
                last_id=CASE WHEN excluded.quantity!=v38_stock_state.quantity
                    THEN excluded.last_id ELSE v38_stock_state.last_id END,
                stock_as_of=excluded.stock_as_of,
                quantity=excluded.quantity
                WHERE excluded.stock_as_of>=v38_stock_state.stock_as_of""",
                (key,int(rowid),int(stamp),int(qty)))
        if rows: last_id=int(rows[-1][0])
        if old and (gaps!=old[1] or reset):
            sidecar.execute("DELETE FROM v38_feature_cache")
        elif affected:
            sidecar.executemany("DELETE FROM v38_feature_cache WHERE item_key=?",
                                [(k,) for k in affected])
        sidecar.execute("""INSERT INTO v38_source_cursor VALUES(1,?,?,?)
            ON CONFLICT(singleton) DO UPDATE SET
            last_id=excluded.last_id,gap_rev=excluded.gap_rev,
            caught_up=excluded.caught_up""",(last_id,gaps,int(last_id>=maximum)))
    return {"processed":len(rows),"last_id":last_id,
            "observed_max_id":maximum,"caught_up":last_id>=maximum,
            "gap_revision":gaps,"affected_keys":sorted(affected),"reset":reset}
