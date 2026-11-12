"""V38 research-only extension: exact frozen V18 configs for all 10 V18 flowers/plushies.

Uses the *same original* live single-tick engine as the proven V35 Heather and
Wolverine pilot; unlike V35, this separate research entry point permits only
the additional source-pinned V18 item/config pairs in v38_roster.json.

No website/bot routing changes, no automated travel, no secret access.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from research.v57_exception_fingerprint import fingerprint

from services.private_v18_champion_worker_v35 import single_tick as frozen_v18_tick

# Source-pinned fixed list. Never infer a config from an arbitrary CLI argument.
V18_APPROVED = {
    "arg:Ceibo Flower": "dyn3",
    "can:Crocus": "dyn5",
    "can:Wolverine Plushie": "dyn8",
    "cay:Banana Orchid": "dyn7",
    "cay:Stingray Plushie": "dyn7",
    "haw:Orchid": "dyn3",
    "mex:Dahlia": "dyn2",
    "mex:Jaguar Plushie": "dyn3",
    "uae:Tribulus Omanense": "dyn3",
    "uni:Heather": "dyn3",
}


def predict(db: str | Path, country: str, item: str, now: int) -> dict:
    country = country.lower().strip()
    item = item.strip()
    key = f"{country}:{item}"
    config = V18_APPROVED.get(key)
    if config is None:
        return {"status": "NOT_APPROVED_FROZEN_V18_V38"}
    return frozen_v18_tick(
        db, country, item, config, int(now),
        approved_configs=V18_APPROVED,
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", required=True)
    p.add_argument("--country", required=True)
    p.add_argument("--item", required=True)
    p.add_argument("--now", required=True, type=int)
    args = p.parse_args()
    try:
        response = predict(args.db, args.country, args.item, args.now)
    except Exception as exc:
        response = {"status": "V38_NATIVE_ERROR", **fingerprint(exc)}
    print(json.dumps(response, sort_keys=True))


if __name__ == "__main__":
    main()
