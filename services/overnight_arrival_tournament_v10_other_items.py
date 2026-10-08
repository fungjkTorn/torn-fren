import argparse
import json
import sqlite3
import time
from pathlib import Path

from services import history_service
from services.deep_arrival_tournament_v10 import run_item


COUNTRIES = ("mex", "cay", "can", "haw", "uni", "arg", "swi", "jap", "chi", "uae", "sou")

CORE_ITEMS = {
    ("mex", "Dahlia"), ("cay", "Banana Orchid"), ("can", "Crocus"),
    ("haw", "Orchid"), ("uni", "Heather"), ("swi", "Edelweiss"),
    ("arg", "Ceibo Flower"), ("jap", "Cherry Blossom"), ("chi", "Peony"),
    ("uae", "Tribulus Omanense"), ("sou", "African Violet"),
    ("mex", "Jaguar Plushie"), ("cay", "Stingray Plushie"),
    ("can", "Wolverine Plushie"), ("uni", "Nessie Plushie"),
    ("uni", "Red Fox Plushie"), ("swi", "Chamois Plushie"),
    ("arg", "Monkey Plushie"), ("chi", "Panda Plushie"),
    ("uae", "Camel Plushie"), ("sou", "Lion Plushie"),
    ("can", "Xanax"), ("uni", "Xanax"), ("jap", "Xanax"),
}


def slug(country, item):
    return f"{country}_{item.lower().replace(' ', '_').replace(chr(39), '')}"


def load(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def discover_items(db_path, min_changes):
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT LOWER(country), item_name, COUNT(*) AS changes
            FROM stock_history
            WHERE LOWER(country) IN ({})
            GROUP BY LOWER(country), item_name
            ORDER BY LOWER(country), item_name
            """.format(",".join("?" for _ in COUNTRIES)),
            COUNTRIES,
        ).fetchall()

    core_lower = {(c.lower(), i.lower()) for c, i in CORE_ITEMS}
    found = []
    for country, item, changes in rows:
        if (country.lower(), item.lower()) in core_lower:
            continue
        if int(changes) < int(min_changes):
            continue
        found.append((country.lower(), item, int(changes)))
    return found


def main():
    p = argparse.ArgumentParser(
        description=(
            "Run the V10 direct-arrival tournament across every other foreign "
            "stock item observed in the DB, excluding the main flowers/plushies/"
            "CAN-UNI-JAP Xanax benchmark set."
        )
    )
    p.add_argument("--db", default="data/stock_history.db")
    p.add_argument("--output-dir", default="data/overnight_arrival_v10_other_items")
    p.add_argument(
        "--min-changes", type=int, default=30,
        help="Skip extremely sparse items with fewer raw quantity-change rows."
    )
    p.add_argument("--no-resume", action="store_true")
    args = p.parse_args()

    db = Path(args.db).resolve()
    if not db.exists():
        raise SystemExit(f"Database not found: {db}")

    history_service.DB_PATH = db
    history_service._DB_READY = False

    items = discover_items(db, args.min_changes)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    master_path = out / "master.json"

    master = load(master_path, {
        "schema": "deep-arrival-v10-other-items-v1",
        "db_path": str(db),
        "results": {},
    })
    master["db_path"] = str(db)
    master["items_total"] = len(items)
    master["min_changes"] = int(args.min_changes)
    master["discovered_items"] = [
        {"country": c, "item_name": i, "raw_change_rows": n}
        for c, i, n in items
    ]

    print(
        f"Discovered {len(items)} non-core foreign items with >= "
        f"{args.min_changes} raw changes.",
        flush=True,
    )

    started_all = time.time()
    for idx, (country, item, changes) in enumerate(items, 1):
        s = slug(country, item)
        cp = out / f"{s}.json"

        if cp.exists() and not args.no_resume:
            report = load(cp, None)
            if report:
                master["results"][s] = report
                print(f"[{idx}/{len(items)}] SKIP {country.upper()} / {item}", flush=True)
                continue

        print(
            f"\n[{idx}/{len(items)}] START {country.upper()} / {item} "
            f"(raw changes={changes})",
            flush=True,
        )
        t0 = time.time()
        try:
            report = run_item(country, item)
            report["status"] = "complete"
        except Exception as exc:
            report = {
                "country": country,
                "item_name": item,
                "status": "error",
                "error": repr(exc),
            }

        report["raw_change_rows"] = changes
        report["runtime_seconds"] = round(time.time() - t0, 3)
        cp.write_text(json.dumps(report, indent=2))
        master["results"][s] = report
        master["updated_at_epoch"] = int(time.time())
        master_path.write_text(json.dumps(master, indent=2))

        sel = report.get("selected_on_training") or {}
        tr = sel.get("train") or {}
        ho = sel.get("holdout") or {}
        if report.get("status") == "complete":
            print(
                f"[{idx}/{len(items)}] DONE {country.upper()} / {item} | "
                f"train={100*(tr.get('success_30_rate') or 0):.1f}% "
                f"holdout={100*(ho.get('success_30_rate') or 0):.1f}% "
                f"n={ho.get('n') or 0} | {report['runtime_seconds']:.1f}s",
                flush=True,
            )
        else:
            print(
                f"[{idx}/{len(items)}] ERROR {country.upper()} / {item}: "
                f"{report.get('error')}",
                flush=True,
            )

    board = []
    for s, r in master["results"].items():
        sel = r.get("selected_on_training") or {}
        tr = sel.get("train") or {}
        ho = sel.get("holdout") or {}
        board.append({
            "slug": s,
            "country": r.get("country"),
            "item_name": r.get("item_name"),
            "status": r.get("status"),
            "raw_change_rows": r.get("raw_change_rows"),
            "train_success": tr.get("success_30_rate"),
            "holdout_success": ho.get("success_30_rate"),
            "holdout_n": ho.get("n"),
            "config": sel.get("config"),
        })
    board.sort(
        key=lambda x: (
            x["status"] != "complete",
            x["holdout_success"] is None,
            -(x["holdout_success"] or 0),
        )
    )
    master["leaderboard"] = board
    master["total_runtime_seconds"] = round(time.time() - started_all, 3)
    master["updated_at_epoch"] = int(time.time())
    master_path.write_text(json.dumps(master, indent=2))

    print(f"\nFinished: {master_path}", flush=True)


if __name__ == "__main__":
    main()
