import argparse
import json
import time
from pathlib import Path

from services import history_service
from services.arrival_probability_tournament_v9 import run_item


FLOWERS = [
    ("mex", "Dahlia"),
    ("cay", "Banana Orchid"),
    ("can", "Crocus"),
    ("haw", "Orchid"),
    ("uni", "Heather"),
    ("swi", "Edelweiss"),
    ("arg", "Ceibo Flower"),
    ("jap", "Cherry Blossom"),
    ("chi", "Peony"),
    ("uae", "Tribulus Omanense"),
    ("sou", "African Violet"),
]

PLUSHIES = [
    ("mex", "Jaguar Plushie"),
    ("cay", "Stingray Plushie"),
    ("can", "Wolverine Plushie"),
    ("uni", "Nessie Plushie"),
    ("uni", "Red Fox Plushie"),
    ("swi", "Chamois Plushie"),
    ("arg", "Monkey Plushie"),
    ("chi", "Panda Plushie"),
    ("uae", "Camel Plushie"),
    ("sou", "Lion Plushie"),
]

XANAX = [
    ("can", "Xanax"),
    ("uni", "Xanax"),
]

ITEMS = FLOWERS + PLUSHIES + XANAX


def _slug(country, item):
    return f"{country}_{item.lower().replace(' ', '_').replace("'", '')}"


def _load_json(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def main():
    p = argparse.ArgumentParser(
        description=(
            "Checkpointed overnight direct-arrival tournament for all museum "
            "flowers/plushies plus Canada and United Kingdom Xanax."
        )
    )
    p.add_argument(
        "--db", default="data/stock_history.db",
        help="SQLite snapshot to use. The script never writes prediction data to it."
    )
    p.add_argument("--output-dir", default="data/overnight_arrival_v9")
    p.add_argument("--depth", type=int, default=8)
    p.add_argument(
        "--no-resume", action="store_true",
        help="Re-run items even if an item checkpoint JSON already exists."
    )
    p.add_argument(
        "--only", action="append", default=[],
        help="Optional COUNTRY:ITEM filter; may be repeated."
    )
    args = p.parse_args()

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    # Point all history helpers at the supplied immutable snapshot.
    history_service.DB_PATH = db_path
    history_service._DB_READY = False

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    master_path = out_dir / "master.json"

    filters = {x.lower() for x in args.only}
    items = [
        pair for pair in ITEMS
        if not filters or f"{pair[0]}:{pair[1]}".lower() in filters
    ]

    master = _load_json(master_path, {
        "schema": "arrival-probability-v9-overnight-v1",
        "db_path": str(db_path),
        "items_total": len(items),
        "results": {},
    })
    master["db_path"] = str(db_path)
    master["items_total"] = len(items)

    total_started = time.time()
    for index, (country, item_name) in enumerate(items, 1):
        slug = _slug(country, item_name)
        checkpoint = out_dir / f"{slug}.json"

        if checkpoint.exists() and not args.no_resume:
            report = _load_json(checkpoint, None)
            if report:
                master["results"][slug] = report
                print(
                    f"[{index}/{len(items)}] SKIP {country.upper()} / {item_name} "
                    f"(checkpoint exists)",
                    flush=True,
                )
                continue

        print(
            f"\n[{index}/{len(items)}] START {country.upper()} / {item_name}",
            flush=True,
        )
        started = time.time()
        try:
            report = run_item(
                country, item_name, max_depth=max(2, int(args.depth))
            )
            report["runtime_seconds"] = round(time.time() - started, 3)
            report["status"] = "complete"
        except Exception as exc:
            report = {
                "country": country,
                "item_name": item_name,
                "status": "error",
                "error": repr(exc),
                "runtime_seconds": round(time.time() - started, 3),
            }

        checkpoint.write_text(json.dumps(report, indent=2))
        master["results"][slug] = report
        master["updated_at_epoch"] = int(time.time())
        master_path.write_text(json.dumps(master, indent=2))

        selected = report.get("selected_on_training") or {}
        tr = selected.get("train") or {}
        ho = selected.get("holdout") or {}
        if report.get("status") == "complete":
            print(
                f"[{index}/{len(items)}] DONE {country.upper()} / {item_name} | "
                f"train={100*(tr.get('success_30_rate') or 0):.1f}% "
                f"holdout={100*(ho.get('success_30_rate') or 0):.1f}% "
                f"n={ho.get('n') or 0} | "
                f"{selected.get('config')} | "
                f"{report['runtime_seconds']:.1f}s",
                flush=True,
            )
        else:
            print(
                f"[{index}/{len(items)}] ERROR {country.upper()} / {item_name}: "
                f"{report.get('error')}",
                flush=True,
            )

    # Compact leaderboard for quick morning inspection.
    leaderboard = []
    for slug, report in master["results"].items():
        selected = report.get("selected_on_training") or {}
        hold = selected.get("holdout") or {}
        train = selected.get("train") or {}
        leaderboard.append({
            "slug": slug,
            "country": report.get("country"),
            "item_name": report.get("item_name"),
            "status": report.get("status"),
            "train_success": train.get("success_30_rate"),
            "holdout_success": hold.get("success_30_rate"),
            "holdout_n": hold.get("n"),
            "config": selected.get("config"),
        })
    leaderboard.sort(
        key=lambda r: (
            r["holdout_success"] is None,
            -(r["holdout_success"] or 0.0),
        )
    )
    master["leaderboard"] = leaderboard
    master["total_runtime_seconds"] = round(time.time() - total_started, 3)
    master["updated_at_epoch"] = int(time.time())
    master_path.write_text(json.dumps(master, indent=2))

    print(f"\nFinished. Master report: {master_path}", flush=True)


if __name__ == "__main__":
    main()
