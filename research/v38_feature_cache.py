"""Versioned, gap-aware, slot-specific research features, never public cache."""
import json
from research.v38_incremental_observer import initialize


def get(con, *, key, config, schema, slot):
    initialize(con)
    row=con.execute("""
        SELECT s.last_id, c.gap_rev, c.caught_up,
               f.source_row_id, f.gap_rev, f.features_json
        FROM v38_stock_state s
        JOIN v38_source_cursor c ON c.singleton=1
        JOIN v38_feature_cache f ON f.item_key=s.item_key
        WHERE s.item_key=? AND f.config=? AND f.schema_version=?
              AND f.clock_slot=?
    """,(key,config,schema,int(slot))).fetchone()
    if row and row[2] and row[0]==row[3] and row[1]==row[4]:
        return json.loads(row[5])
    return None


def put(con, *, key, config, schema, slot, features):
    if not isinstance(features, dict):
        raise ValueError("features must be a JSON object")
    initialize(con)
    state=con.execute("""
        SELECT s.last_id,c.gap_rev,c.caught_up
        FROM v38_stock_state s JOIN v38_source_cursor c ON c.singleton=1
        WHERE s.item_key=?
    """,(key,)).fetchone()
    if state is None or not state[2]:
        return False
    with con:
        con.execute("""
            INSERT OR REPLACE INTO v38_feature_cache VALUES(?,?,?,?,?,?,?)
        """,(key,config,schema,int(slot),state[0],state[1],
             json.dumps(features,separators=(",",":"),allow_nan=False)))
    return True


def prune_old_slots(con, older_than_slot):
    with con:
        r=con.execute("DELETE FROM v38_feature_cache WHERE clock_slot<?",
                      (int(older_than_slot),))
    return r.rowcount
