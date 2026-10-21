"""Research-only latest prediction sidecar schema; never edits collector DB."""

LATEST_TABLE = """
CREATE TABLE IF NOT EXISTS latest_predictions (
    item_key TEXT PRIMARY KEY,
    model_family TEXT NOT NULL,
    model_config TEXT,
    status TEXT NOT NULL,
    computed_at INTEGER NOT NULL,
    stock_as_of INTEGER,
    valid_until INTEGER NOT NULL,
    next_due_at INTEGER NOT NULL,
    departure INTEGER,
    arrival INTEGER,
    executed INTEGER NOT NULL DEFAULT 0
)
"""

ATTEMPT_TABLE = """
CREATE TABLE IF NOT EXISTS inference_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_key TEXT NOT NULL,
    attempted_at INTEGER NOT NULL,
    status TEXT NOT NULL,
    elapsed_ms INTEGER
)
"""

# Immutable research candidate decisions (NOT evidence of actual player travel).
CANDIDATE_TABLE = """
CREATE TABLE IF NOT EXISTS v42_candidate_decisions (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 item_key TEXT NOT NULL,
 computed_at INTEGER NOT NULL,
 model_family TEXT NOT NULL,
 model_config TEXT,
 stock_as_of INTEGER,
 status TEXT NOT NULL,
 departure INTEGER,
 arrival INTEGER,
 valid_until INTEGER NOT NULL,
 actual_player_departure INTEGER NOT NULL DEFAULT 0,
 UNIQUE(item_key,computed_at)
)
"""
