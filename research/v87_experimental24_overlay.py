"""V87 opt-in READ-ONLY bridge: 21 deployed experimental rows + 3 private previews.

Pure adapter, not mounted to a web route until the deployed /opt web source
has been audited and a guarded rollback is prepared. Its responsibility is
to present the 24-item experimental data contract WITHOUT upgrading any
research recommendation to actionable or accuracy-verified.
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from pathlib import Path

PAIR = Path("/home/ubuntu/torn-fren-private-models/v81_pair_forward.db")
JAPAN = Path("/home/ubuntu/torn-fren-private-models/v84_japan_forward.db")
ADDED = ("chi:Panda Plushie", "sou:Lion Plushie", "jap:Xanax")
SELECTED_VARIANT = "selector"  # Explicitly experimental, not a validated winner.
STEP = 300
GRACE = 10
HORIZON = 28800
TRAVEL = {"chi:Panda Plushie": 9600, "sou:Lion Plushie": 11820,
          "jap:Xanax": 8940}
META = {"chi:Panda Plushie": "PAIR_SELECTOR_UNVALIDATED",
        "sou:Lion Plushie": "PAIR_SELECTOR_UNVALIDATED",
        "jap:Xanax": "JAPAN_V8_REGIME_UNVALIDATED"}
MAX_SOURCE_LAG = 180
PINS = {"chi:Panda Plushie": "84037c778301fa5a3825007dd439abec7c971ec05b176efae3bffe99fc827280",
        "sou:Lion Plushie": "a8a5e7d989c701fa75975dd9b8d73c128e5fd895298443c2cfd6bb3d72e824bd"}


def _read_one(path, sql, args):
    """No create/open fallback. SQLite sidecar must already exist and be regular."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.parent.is_symlink():
        return None
    try:
        with closing(sqlite3.connect(path.resolve(strict=True).as_uri() + "?mode=ro",
                                     uri=True, timeout=2)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            row = conn.execute(sql, args).fetchone()
            return dict(row) if row else None
    except (sqlite3.Error, OSError):
        return None


def _base(key, now):
    return {"item_key": key, "model_family": META[key],
            "model_config": "NOT_YET_OBSERVED",
            "status": "RESEARCH_PREVIEW_NO_VALID_RESULT",
            "computed_at": None, "stock_as_of": None,
            "collector_last_verified": None,
            "valid_until": None, "departure": None, "arrival": None,
            "planning_horizon_seconds": HORIZON,
            "quantity_threshold": 30, "grace_seconds": GRACE,
            "actionable": False, "experimental": True,
            "prediction_accuracy_verified": False,
            "preview_note": "Forward-testing only; accuracy not yet established.",
            "preview_variant": None}


def _recent(r, *, issued_key, source_key, expires_at, now):
    try:
        t, source = r[issued_key], r[source_key]
        return (type(t) is int and type(source) is int
                and 0 <= t - source <= MAX_SOURCE_LAG
                and 0 <= now - t <= STEP + 60
                and type(expires_at) is int and expires_at > now)
    except (KeyError, TypeError, ValueError):
        return False


def _pair(key, now, db):
    row = _base(key, now)
    latest = _read_one(db, """SELECT item_key,variant,issued_at,planned_at,
                         stock_as_of,valid_until,status,selected_expert,
                         departure,arrival,artifact_sha256,min_quantity,grace_seconds,
                         actual_player_departure
                         FROM pair_issued_decisions
                         WHERE item_key=? AND variant=?
                         ORDER BY issued_at DESC,id DESC LIMIT 1""",
                       (key, SELECTED_VARIANT))
    if latest is None:
        return row
    row.update(computed_at=latest.get("issued_at"),
               stock_as_of=latest.get("stock_as_of"),
               collector_last_verified=latest.get("stock_as_of"),
               valid_until=latest.get("valid_until"),
               model_config="selector/" + str(latest.get("selected_expert", "unknown")),
               preview_variant=SELECTED_VARIANT)
    issued = latest.get("issued_at")
    planned = latest.get("planned_at")
    age_ok = _recent(latest, issued_key="issued_at",
                     source_key="stock_as_of",
                     expires_at=latest.get("valid_until"), now=now)
    grid_ok = (type(planned) is int and type(issued) is int and
               planned % STEP == 0 and 0 <= issued - planned <= STEP and
               latest.get("valid_until") == issued + STEP)
    if not age_ok or not grid_ok:
        row["status"] = "RESEARCH_PREVIEW_STALE"
        return row
    if latest.get("status") != "FORWARD_CANDIDATE_ONLY":
        row["status"] = "RESEARCH_PREVIEW_" + str(latest.get("status", "ABSTAINED"))[:72]
        return row
    dep, arr = latest.get("departure"), latest.get("arrival")
    if (latest.get("item_key") != key or latest.get("variant") != SELECTED_VARIANT
            or latest.get("artifact_sha256") != PINS[key]
            or latest.get("min_quantity") != 30
            or latest.get("grace_seconds") != GRACE
            or latest.get("actual_player_departure") != 0
            or type(dep) is not int or type(arr) is not int
            or type(issued) is not int
            or not issued <= dep <= issued + HORIZON
            or arr != dep + TRAVEL[key]):
        row["status"] = "RESEARCH_PREVIEW_INVALID"
        return row
    if dep <= now:
        row["status"] = "RESEARCH_PREVIEW_DEPARTURE_PASSED"
        return row
    row.update(status="RESEARCH_PREVIEW_UNVALIDATED",
               departure=dep, arrival=arr)
    return row


def _japan(now, db):
    key = "jap:Xanax"
    row = _base(key, now)
    latest = _read_one(db, """SELECT slot,queried_at,issued_at,source_heartbeat,
                         status,model_config,departure,arrival,
                         quantity_threshold,grace_seconds,
                         actual_player_departure,source_model,experiment
                         FROM japan_forward_decisions
                         ORDER BY issued_at DESC LIMIT 1""", ())
    if latest is None:
        return row
    issued = latest.get("issued_at")
    row.update(computed_at=issued, stock_as_of=latest.get("source_heartbeat"),
               collector_last_verified=latest.get("source_heartbeat"),
               valid_until=issued + STEP if type(issued) is int else None,
               model_config=str(latest.get("model_config") or "UNSPECIFIED"),
               preview_variant="v8_regime_candidate")
    age_ok = _recent(latest, issued_key="issued_at",
                     source_key="source_heartbeat",
                     expires_at=row["valid_until"], now=now)
    query = latest.get("queried_at")
    slot = latest.get("slot")
    basic_ok = (type(query) is int and type(slot) is int
                and type(issued) is int and slot == query // STEP * STEP
                and 0 <= issued - query <= 60
                and latest.get("quantity_threshold") == 30
                and latest.get("grace_seconds") == GRACE
                and latest.get("actual_player_departure") == 0
                and latest.get("source_model") == "v8_regime_candidate_checkpoint_parity_pending"
                and latest.get("experiment") == "v84_japan_private_canary")
    if not age_ok or not basic_ok:
        row["status"] = "RESEARCH_PREVIEW_STALE_OR_INVALID"
        return row
    if latest.get("status") != "FORWARD_CANDIDATE_ONLY":
        row["status"] = "RESEARCH_PREVIEW_" + str(latest.get("status", "ABSTAINED"))[:72]
        return row
    dep, arr = latest.get("departure"), latest.get("arrival")
    if (type(dep) is not int or type(arr) is not int
            or not issued <= dep <= query + HORIZON
            or arr - dep != TRAVEL[key]):
        row["status"] = "RESEARCH_PREVIEW_INVALID"
        return row
    if dep <= now:
        row["status"] = "RESEARCH_PREVIEW_DEPARTURE_PASSED"
        return row
    row.update(status="RESEARCH_PREVIEW_UNVALIDATED",
               departure=dep, arrival=arr)
    return row


def previews(*, now=None, pair_db=PAIR, japan_db=JAPAN):
    instant = int(time.time() if now is None else now)
    return [_pair("chi:Panda Plushie", instant, pair_db),
            _pair("sou:Lion Plushie", instant, pair_db),
            _japan(instant, japan_db)]


def merge_response(payload, *, now=None, pair_db=PAIR, japan_db=JAPAN):
    """Extend a verified existing 21-item API response; don't mutate it."""
    if not isinstance(payload, dict) or not isinstance(payload.get("latest"), list):
        raise ValueError("expected experimental API JSON with latest list")
    old = payload["latest"]
    if len(old) != 21 or any(not isinstance(r, dict) for r in old):
        raise ValueError("expected existing 21 research rows, no partial overlay")
    keys = [r.get("item_key") for r in old]
    if len(set(keys)) != 21 or any(k in ADDED for k in keys):
        raise ValueError("existing roster duplicate or collided with preview")
    result = dict(payload)
    result["latest"] = [*old, *previews(now=now, pair_db=pair_db,
                                       japan_db=japan_db)]
    result["experimental"] = True
    result["prediction_accuracy_verified"] = False
    result["preview_only_item_keys"] = list(ADDED)
    result["preview_warning"] = (
        "Three added models are unvalidated private research forecasts; "
        "timestamps are not gameplay instructions or calibrated probabilities."
    )
    return result

def overlay_response(payload, *, key=None, now=None, pair_db=PAIR, japan_db=JAPAN):
    """Opt-in HTTP response adapter; preserve original results if base drifts.

    Pair-filtered legacy queries remain unchanged. An exact request for one of
    the new preview items returns one non-actionable preview record.
    """
    if not isinstance(payload, dict):
        raise ValueError("invalid experimental API response")
    if key is not None:
        # The legacy endpoint returns a different shape for filtered lookups
        # (a single record or None rather than the full 21-row list).
        # Preserve old filtered requests byte-for-byte; construct a preview
        # list only for the three new item keys.
        if key not in ADDED:
            return payload
        rows = [r for r in previews(now=now, pair_db=pair_db,
                                    japan_db=japan_db) if r["item_key"] == key]
        result = dict(payload)
        result.update(latest=rows, experimental=True,
                      prediction_accuracy_verified=False,
                      preview_only_item_keys=[key],
                      preview_warning="Unvalidated research model; not a gameplay instruction.")
        return result
    if not isinstance(payload.get("latest"), list):
        result = dict(payload)
        result["preview_overlay_status"] = "BASE_ROSTER_SHAPE_UNEXPECTED"
        return result
    try:
        return merge_response(payload, now=now, pair_db=pair_db, japan_db=japan_db)
    except ValueError:
        # A partial, corrupted or changing V75 baseline must not cause a
        # production 500 or replace any of the original visible records.
        result = dict(payload)
        result["preview_overlay_status"] = "BASE_ROSTER_NOT_21"
        return result
