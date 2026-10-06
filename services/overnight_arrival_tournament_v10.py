import argparse
import json
import time
from pathlib import Path

from services import history_service
from services.deep_arrival_tournament_v10 import run_item


FLOWERS = [
    ("mex", "Dahlia"), ("cay", "Banana Orchid"), ("can", "Crocus"),
    ("haw", "Orchid"), ("uni", "Heather"), ("swi", "Edelweiss"),
    ("arg", "Ceibo Flower"), ("jap", "Cherry Blossom"), ("chi", "Peony"),
    ("uae", "Tribulus Omanense"), ("sou", "African Violet"),
]
PLUSHIES = [
    ("mex", "Jaguar Plushie"), ("cay", "Stingray Plushie"),
    ("can", "Wolverine Plushie"), ("uni", "Nessie Plushie"),
    ("uni", "Red Fox Plushie"), ("swi", "Chamois Plushie"),
    ("arg", "Monkey Plushie"), ("chi", "Panda Plushie"),
    ("uae", "Camel Plushie"), ("sou", "Lion Plushie"),
]
XANAX = [("can", "Xanax"), ("uni", "Xanax"), ("jap", "Xanax")]
ALL = FLOWERS + PLUSHIES + XANAX

# Deep mode spends the night where V9 is weakest while still allowing --all
# for a full robustness rerun.
TARGETED = [
    ("can", "Wolverine Plushie"), ("uni", "Nessie Plushie"),
    ("uni", "Red Fox Plushie"), ("swi", "Chamois Plushie"),
    ("arg", "Monkey Plushie"), ("chi", "Panda Plushie"),
    ("uae", "Camel Plushie"), ("sou", "Lion Plushie"),
    ("uni", "Xanax"), ("jap", "Xanax"),
]


def slug(c, i):
    return f"{c}_{i.lower().replace(' ', '_').replace(chr(39), '')}"


def load(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="data/stock_history.db")
    p.add_argument("--output-dir", default="data/overnight_arrival_v10")
    p.add_argument("--all", action="store_true",
                   help="Run all flowers, plushies, and CAN/UNI/JAP Xanax.")
    p.add_argument("--only", action="append", default=[])
    p.add_argument("--no-resume", action="store_true")
    args = p.parse_args()

    db = Path(args.db).resolve()
    if not db.exists():
        raise SystemExit(f"Database not found: {db}")
    history_service.DB_PATH = db
    history_service._DB_READY = False

    items = ALL if args.all else TARGETED
    wanted = {x.lower() for x in args.only}
    if wanted:
        items = [x for x in ALL if f"{x[0]}:{x[1]}".lower() in wanted]

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    master_path = out / "master.json"
    master = load(master_path, {
        "schema": "deep-arrival-v10-overnight-v1",
        "db_path": str(db),
        "results": {},
    })
    master["items_total"] = len(items)
    master["db_path"] = str(db)

    started_all = time.time()
    for n, (country, item) in enumerate(items, 1):
        s = slug(country, item)
        cp = out / f"{s}.json"
        if cp.exists() and not args.no_resume:
            report = load(cp, None)
            if report:
                master["results"][s] = report
                print(f"[{n}/{len(items)}] SKIP {country.upper()} / {item}", flush=True)
                continue

        print(f"\n[{n}/{len(items)}] START {country.upper()} / {item}", flush=True)
        t0 = time.time()
        try:
            report = run_item(country, item)
            report["status"] = "complete"
        except Exception as exc:
            report = {
                "country": country, "item_name": item,
                "status": "error", "error": repr(exc),
            }
        report["runtime_seconds"] = round(time.time() - t0, 3)
        cp.write_text(json.dumps(report, indent=2))
        master["results"][s] = report
        master["updated_at_epoch"] = int(time.time())
        master_path.write_text(json.dumps(master, indent=2))

        sel = report.get("selected_on_training") or {}
        tr = sel.get("train") or {}
        ho = sel.get("holdout") or {}
        print(
            f"[{n}/{len(items)}] {report.get('status').upper()} "
            f"train={100*(tr.get('success_30_rate') or 0):.1f}% "
            f"holdout={100*(ho.get('success_30_rate') or 0):.1f}% "
            f"n={ho.get('n') or 0} "
            f"cfg={sel.get('config')} "
            f"{report['runtime_seconds']:.1f}s",
            flush=True,
        )

    board = []
    for s, r in master["results"].items():
        sel = r.get("selected_on_training") or {}
        tr = sel.get("train") or {}
        ho = sel.get("holdout") or {}
        board.append({
            "slug": s, "country": r.get("country"),
            "item_name": r.get("item_name"), "status": r.get("status"),
            "train_success": tr.get("success_30_rate"),
            "holdout_success": ho.get("success_30_rate"),
            "holdout_n": ho.get("n"), "config": sel.get("config"),
        })
    board.sort(key=lambda x: (x["holdout_success"] is None, -(x["holdout_success"] or 0)))
    master["leaderboard"] = board
    master["total_runtime_seconds"] = round(time.time() - started_all, 3)
    master_path.write_text(json.dumps(master, indent=2))
    print(f"\nFinished: {master_path}", flush=True)


if __name__ == "__main__":
    main()
