"""Research-only latest prediction sidecar schema; production is unchanged."""

LATEST_TABLE = """
CREATE TABLE IF NOT EXISTS latest_predictions (
    item_key TEXT PRIMARY KEY,
    model_family TEXT NOT NULL,
    status TEXT NOT NULL,
    computed_at INTEGER NOT NULL,
    stock_as_of INTEGER,
    valid_until INTEGER NOT NULL,
    departure INTEGER,
    arrival INTEGER
)
"""
