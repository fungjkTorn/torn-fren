"""Warm Prediction V2 disk profiles outside the request path.

Run this after a model/profile schema change or on a fresh production install.
It walks every collected foreign item and lets prediction_v2_live._profile()
reuse a valid disk profile or build/persist a missing one.

This intentionally warms only the relatively static model profile, not a live
prediction target. Live restock/depletion state remains calculated normally.
"""

import argparse
import time

from services.history_service import get_stock_catalog
from services.prediction_v2_live import PROFILE_SCHEMA_VERSION, _profile


def iter_catalog_items(country_filter=None):
    catalog = get_stock_catalog()
    wanted = (country_filter or "").strip().lower()
    for country_row in catalog.get("countries", []):
        country = (country_row.get("country") or "").lower()
        if wanted and country != wanted:
            continue
        for item in country_row.get("items", []):
            name = item.get("item_name")
            if name:
                yield country, name


def main():
    parser = argparse.ArgumentParser(description="Warm Torn Fren Prediction V2 profiles.")
    parser.add_argument("--country", help="Optional 3-letter country code, e.g. chi")
    parser.add_argument(
        "--pause",
        type=float,
        default=0.10,
        help="Seconds to pause between items (default: 0.10)",
    )
    args = parser.parse_args()

    items = list(iter_catalog_items(args.country))
    total = len(items)
    print(
        f"Warming {total} Prediction V2 profile(s) "
        f"for schema {PROFILE_SCHEMA_VERSION}..."
    )

    ok = 0
    failed = 0
    started_all = time.perf_counter()

    for index, (country, item_name) in enumerate(items, start=1):
        started = time.perf_counter()
        try:
            profile = _profile(country, item_name, force=False)
            elapsed = time.perf_counter() - started
            print(
                f"[{index}/{total}] {country}/{item_name}: "
                f"{elapsed:.2f}s · {profile.get('model_name')} · "
                f"{profile.get('model_evidence_tier')}"
            )
            ok += 1
        except Exception as exc:
            elapsed = time.perf_counter() - started
            print(
                f"[{index}/{total}] {country}/{item_name}: "
                f"FAILED after {elapsed:.2f}s · {exc}"
            )
            failed += 1

        if args.pause > 0:
            time.sleep(args.pause)

    elapsed_all = time.perf_counter() - started_all
    print(
        f"Finished in {elapsed_all:.1f}s. "
        f"successful={ok}, failed={failed}, total={total}"
    )
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
