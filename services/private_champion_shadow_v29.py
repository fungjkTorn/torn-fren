"""Private, OFF-BY-DEFAULT V29 research shadow contract.

This is explicitly *not* a champion inference implementation. The current
site/Discord routes are unchanged. The private route shows V2 as a clearly
identified reference and an unexecuted frozen challenger identity.

No stock databases are written; no stored API keys are read or emitted.
"""
from __future__ import annotations

import hmac
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / "research" / "all_236_champions_v26.json"
ENABLED_ENV = "TORN_FREN_CHAMPION_SHADOW_ENABLED"
TOKEN_ENV = "TORN_FREN_CHAMPION_SHADOW_TOKEN"
REGISTRY_ENV = "TORN_FREN_CHAMPION_SHADOW_REGISTRY_PATH"


class ShadowUnavailable(Exception):
    pass


class ShadowUnauthorized(Exception):
    pass


def authorized(token: str | None, environ: dict[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    if env.get(ENABLED_ENV, "").strip().lower() not in ("1", "true", "yes"):
        return False
    secret = env.get(TOKEN_ENV, "")
    # Weak test/development secrets must not accidentally expose forecast data.
    return len(secret) >= 32 and bool(token) and hmac.compare_digest(secret, token)


def _registry(path: str | Path) -> dict:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if manifest.get("schema") != "torn-fren-all-236-provisional-champions-v26":
        raise ShadowUnavailable("unrecognized frozen registry schema")
    if manifest.get("all_live_promotions_prohibited") is not True:
        raise ShadowUnavailable("registry is not explicitly research-only")
    items = manifest.get("items") or {}
    if len(items) != 236:
        raise ShadowUnavailable("expected exactly 236 frozen item entries")
    return items


def _utc_timestamp(value: Any) -> int | None:
    # A timestamp is valid only when the source explicitly supplied a
    # positive numeric Unix timestamp. Do not manufacture predictions.
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    return int(value)


def make_shadow_snapshot(
    country: str,
    item_name: str,
    supplied_token: str | None,
    *,
    v2_fn: Callable | None = None,
    environ: dict[str, str] | None = None,
    registry_path: str | Path | None = None,
    challenger_fn: Callable | None = None,
) -> dict:
    env = os.environ if environ is None else environ
    if env.get(ENABLED_ENV, "").strip().lower() not in ("1", "true", "yes"):
        raise ShadowUnavailable("shadow is disabled")
    if not authorized(supplied_token, env):
        raise ShadowUnauthorized("invalid private shadow authorization")
    code, name = country.strip().lower(), item_name.strip()
    if len(code) != 3 or not code.isalpha() or not name or len(name) > 120:
        raise ValueError("invalid country/item")
    key = code + ":" + name
    items = _registry(registry_path or env.get(REGISTRY_ENV) or DEFAULT_REGISTRY)
    candidate = items.get(key)
    if candidate is None:
        raise KeyError("item not in frozen catalog")

    selected = candidate.get("current_provisional_candidate") or {}
    model_family = selected.get("model_family")
    if not model_family:
        raise ShadowUnavailable("item has no research candidate")
    if v2_fn is None:
        from services.prediction_v2_live import build_live_prediction_v2
        reference_fn = build_live_prediction_v2
    else:
        reference_fn = v2_fn
    baseline = {"status": "unavailable", "reason": "V2 baseline failed"}
    try:
        # Avoid duplicated forecast audit records from diagnostics.
        prediction = reference_fn(code, name, record_audit=False)
        if isinstance(prediction, dict):
            display = prediction.get("display_prediction") or {}
            baseline = {
                "status": "available" if display else "no_reachable_prediction",
                "model": "existing_live_v2_reference_only",
                "prediction_number": display.get("prediction_number"),
                "projected": bool(display.get("projected")),
                "travel_reliability": prediction.get("travel_reliability"),
                "ready_for_live_guidance": bool(prediction.get("ready_for_live_guidance")),
                "recommended_leave_by_timestamp": _utc_timestamp(
                    display.get("recommended_leave_by_timestamp")),
                "recommended_arrival_timestamp": _utc_timestamp(
                    display.get("recommended_arrival_timestamp")),
            }
    except Exception:
        # Do not echo stack traces, keys, environment or internal paths to API clients.
        pass

    challenger={"status":"DISABLED","champion_executed":False}
    try:
        if challenger_fn is None:
            from services.private_challenger_adapter_v31 import research_candidate
            candidate_fn=research_candidate
        else:
            candidate_fn=challenger_fn
        challenger=candidate_fn(code,name,selected,candidate.get("category","other"),
                                environ=env)
        if not isinstance(challenger,dict):
            challenger={"status":"INVALID_RESEARCH_WORKER_RESULT","champion_executed":False}
    except Exception:
        challenger={"status":"RESEARCH_WORKER_FAILED","champion_executed":False}
    actually_executed=(challenger.get("status")=="RESEARCH_PROPOSAL_ONLY" and
                       challenger.get("champion_executed") is True)

    return {
        "schema": "torn-fren-private-research-shadow-v29",
        "generated_at": int(time.time()),
        "key": key,
        "mode": "READ_ONLY_DIAGNOSTIC",
        "default_live_routing": "UNCHANGED",
        "champion_executed": actually_executed,
        "champion_status": ("FROZEN_RESEARCH_SINGLE_TICK_ONLY" if actually_executed
                            else "FROZEN_CANDIDATE_NOT_INTEGRATED"),
        "candidate_model_family": model_family,
        "candidate_config": selected.get("config_name"),
        "candidate_promoted": False,
        "chance_calibrated": False,
        "baseline": baseline,
        "challenger": challenger,
        "note": ("Baseline timestamps come only from V2. Any challenger timestamps "
                 "are private research single-tick proposals, not live guidance or "
                 "calibrated chances; production V2 routing is unchanged."),
    }
