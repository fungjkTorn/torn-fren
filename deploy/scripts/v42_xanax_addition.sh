#!/usr/bin/env bash
# V42 Canada/UK Xanax optional private research rollout, no gameplay automation.
# Usage: bash deploy/scripts/v42_xanax_addition.sh benchmark|activate|rollback
# Does not touch web, collector, bot, or live production history.
set -euo pipefail
MODE=benchmark
if [ "$#" -gt 0 ]; then MODE="$1"; fi
ROOT=/home/ubuntu/torn-fren-v38-probe
PY="$ROOT/.venv/bin/python"
STOCK=/opt/torn-fren/data/stock_history.db
SIDECAR=/var/lib/torn-fren-v38/private_predictions.db
SERVICE=torn-fren-v38-private-shadow.service
TIMER=torn-fren-v38-private-shadow.timer
OVERRIDE=/etc/systemd/system/torn-fren-v38-private-shadow.service.d/v42-xanax-addition.conf
BENCH=/tmp/torn-fren-v42-two-xanax-benchmark.json
BASE=/etc/systemd/system/torn-fren-v38-private-shadow.service.d/v42-sixteen-shadow.conf

if [ "$MODE" = rollback ]; then
  sudo systemctl stop "$TIMER"
  for n in $(seq 1 245); do
    if ! systemctl is-active --quiet "$SERVICE"; then break; fi
    sleep 1
  done
  if systemctl is-active --quiet "$SERVICE"; then
    sudo systemctl start "$TIMER"
    echo "STOP: Private worker still busy; Xanax override left in place."
    exit 1
  fi
  sudo rm -f "$OVERRIDE"
  sudo systemctl daemon-reload
  sudo systemctl start "$TIMER"
  echo "Original 16-model private service restored."
  exit 0
fi

[ "$(id -un)" = ubuntu ] || { echo "STOP: use ubuntu."; exit 1; }
[ -x "$PY" ] && [ -f "$STOCK" ] && [ -f "$BASE" ] ||
  { echo "STOP: Missing 16-model V42 prerequisites."; exit 1; }
cd "$ROOT"
[ -z "$(git status --porcelain)" ] || { echo "STOP: Dirty research checkout."; exit 1; }
for s in torn-fren-web torn-fren-poller torn-fren-bot; do
  systemctl is-active --quiet "$s.service" || { echo "STOP: $s inactive."; exit 1; }
done
systemctl is-active --quiet "$TIMER" || { echo "STOP: private timer inactive."; exit 1; }
curl -fsS --max-time 10 http://127.0.0.1:8000/api/catalog >/dev/null

if [ "$MODE" = benchmark ]; then
  echo "Two frozen Xanax candidates tested read-only. No service changes."
  for n in $(seq 1 245); do
    if ! systemctl is-active --quiet "$SERVICE"; then break; fi
    sleep 1
  done
  if systemctl is-active --quiet "$SERVICE"; then
    echo "STOP: The 16-model scheduler is busy. Try again later."
    exit 1
  fi
  nice -n 19 "$PY" - "$STOCK" "$BENCH" <<'PY'
import json, subprocess, sys, time
from research.v42_xanax_candidate_tick import ALLOWED
stock,out=sys.argv[1:]
records=[];begin=time.monotonic()
for key in ALLOWED:
    country,item=key.split(":",1)
    cmd=[sys.executable,"-m","research.v42_xanax_candidate_tick",
         "--db",stock,"--country",country,"--item",item,
         "--now",str(int(time.time()))]
    t=time.monotonic()
    try:
        p=subprocess.run(cmd,text=True,capture_output=True,
                         check=False,timeout=30)
        if p.returncode or len(p.stdout)>8192:
            status="WORKER_ERROR"
        else:
            result=json.loads(p.stdout)
            status=result.get("status","INVALID_WORKER_OUTPUT")
    except (subprocess.TimeoutExpired,OSError,ValueError):
        status="WORKER_TIMEOUT_OR_ERROR"
    records.append({"item_key":key,"status":status,
                    "elapsed_seconds":round(time.monotonic()-t,3)})
evidence={"items":records,
          "total_elapsed_seconds":round(time.monotonic()-begin,3)}
with open(out,"w",encoding="utf-8") as f:json.dump(evidence,f,indent=2)
print(json.dumps(evidence,indent=2))
PY
  echo "Saved read-only benchmark: $BENCH"
  echo "No extra items live until activation passes the safety gate."
  exit 0
fi

[ "$MODE" = activate ] || { echo "Usage: benchmark|activate|rollback"; exit 1; }
[ -f "$BENCH" ] && [ ! -e "$OVERRIDE" ] ||
  { echo "STOP: missing benchmark or already activated."; exit 1; }

"$PY" - "$BENCH" <<'PY'
import json,sys,time
from pathlib import Path
from research.v42_xanax_candidate_tick import ALLOWED
p=Path(sys.argv[1]);d=json.loads(p.read_text())
rows=d.get("items",[])
if time.time()-p.stat().st_mtime>1800:
    raise SystemExit("STOP: benchmark >30 minutes old.")
if len(rows)!=2 or {r.get("item_key") for r in rows}!=set(ALLOWED):
    raise SystemExit("STOP: approved Xanax pair not fully tested.")
if any(r.get("status") not in ("RESEARCH_PROPOSAL_ONLY","NO_RECOMMENDATION") for r in rows):
    raise SystemExit("STOP: failed worker in benchmark: "+repr(rows))
total=float(d.get("total_elapsed_seconds",1e9))
if total*4>45: raise SystemExit("STOP: estimated 25%-quota wall budget >45s.")
print("Xanax CPU gate passed:",round(total,2),"s unthrottled.")
PY

"$PY" - "$STOCK" <<'PY'
import sqlite3,sys,time
from pathlib import Path
p=Path(sys.argv[1]).resolve(strict=True)
with sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=2) as c:
    stamp=c.execute("""SELECT MAX(timestamp) FROM poll_heartbeats
        WHERE mode='poll-cycle' AND success=1""").fetchone()[0]
age=time.time()-stamp if stamp is not None else 1e9
if not 0<=age<=120: raise SystemExit("STOP: collector heartbeat stale.")
print("Live collector age:",round(age,1),"s")
PY

sudo systemctl stop "$TIMER"
for n in $(seq 1 245); do
  if ! systemctl is-active --quiet "$SERVICE"; then break; fi
  sleep 1
done
if systemctl is-active --quiet "$SERVICE"; then
  sudo systemctl start "$TIMER"
  echo "STOP: prior research cycle still executing."
  exit 1
fi

printf '%s\n' \
 '[Service]' \
 'ExecStart=' \
 "ExecStart=$PY -m research.v38_budgeted_runner --execute --with-xanax --db $STOCK --sidecar $SIDECAR --max-jobs 18 --per-worker 30 --budget 220 --max-rows 10000" |
  sudo tee "$OVERRIDE" >/dev/null
sudo systemctl daemon-reload
if ! sudo systemctl start "$TIMER"; then
  sudo rm -f "$OVERRIDE"
  sudo systemctl daemon-reload
  sudo systemctl start "$TIMER"
  echo "STOP: Failed to start timer; restored original sixteen."
  exit 1
fi
echo "Xanax overlay enabled. Original stock collector, bot and website unchanged."
echo "Rollback command: bash $ROOT/deploy/scripts/v42_xanax_addition.sh rollback"
