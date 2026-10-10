#!/usr/bin/env bash
# V42 private-only sixteen-champion staging. Original FIVE-item service is
# unchanged unless a measured 16-worker run passes a conservative gate.
# Usage: bash deploy/scripts/v42_expand_16_shadow.sh benchmark
#        bash deploy/scripts/v42_expand_16_shadow.sh activate
#        bash deploy/scripts/v42_expand_16_shadow.sh rollback
# Never restarts the web, collector, bot, or other auditing services.
set -u
MODE=benchmark
if [ "$#" -gt 0 ]; then MODE="$1"; fi
ROOT=/home/ubuntu/torn-fren-v38-probe
SERVICE=torn-fren-v38-private-shadow.service
TIMER=torn-fren-v38-private-shadow.timer
OVERRIDE=/etc/systemd/system/torn-fren-v38-private-shadow.service.d/v42-sixteen-shadow.conf
BENCH=/tmp/torn-fren-v42-16-probe.json
PY="$ROOT/.venv/bin/python"
STOCK=/opt/torn-fren/data/stock_history.db
SIDECAR=/var/lib/torn-fren-v38/private_predictions.db

check_live() {
  [ "$(id -un)" = ubuntu ] || return 1
  [ -x "$PY" ] || return 1
  [ -f "$STOCK" ] || return 1
  [ -z "$(git -C "$ROOT" status --porcelain)" ] || return 1
  systemctl is-active --quiet torn-fren-web.service || return 1
  systemctl is-active --quiet torn-fren-poller.service || return 1
  systemctl is-active --quiet torn-fren-bot.service || return 1
  systemctl is-active --quiet "$TIMER" || return 1
  return 0
}

if [ "$MODE" = rollback ]; then
  echo "Stopping research TIMER only; wait for running model to finish."
  sudo systemctl stop "$TIMER" || exit 1
  for i in $(seq 1 55); do
    if ! systemctl is-active --quiet "$SERVICE"; then break; fi
    sleep 1
  done
  if systemctl is-active --quiet "$SERVICE"; then
    sudo systemctl start "$TIMER"
    echo "Research service still busy. No override removed."
    exit 1
  fi
  sudo rm -f "$OVERRIDE" || exit 1
  sudo systemctl daemon-reload || exit 1
  sudo systemctl start "$TIMER" || exit 1
  echo "Restored five-source-pinned-model research service."
  exit 0
fi

check_live || { echo "STOP: Production services or clean research worktree gate failed."; exit 1; }
cd "$ROOT" || exit 1
echo "Original research worker isolation:"
systemctl show "$SERVICE" -p CPUQuotaPerSecUSec -p MemoryMax -p TimeoutStartUSec --no-pager

if [ "$MODE" = benchmark ]; then
  echo "Benchmark: 16 frozen adapters, serial/nice, 210-second cap."
  echo "Existing five-item research timer stays on. Collector is read-only."
  curl -fsS --max-time 10 http://127.0.0.1:8000/api/catalog >/dev/null || exit 1
  nice -n 19 timeout 225s "$PY" -m research.v38_readonly_resource_probe \
       --db "$STOCK" --all --timeout 30 --budget 210 > "$BENCH" || {
     echo "Read-only benchmark failed. Nothing deployed."
     exit 1
   }
  "$PY" -m json.tool "$BENCH" || exit 1
  curl -fsS --max-time 10 http://127.0.0.1:8000/api/catalog >/dev/null || exit 1
  echo "Benchmark saved to $BENCH. 25% service CPU quota is NOT applied"
  echo "to the benchmark, so activation conservatively scales elapsed time x4."
  echo "Review all 16 results before running activate."
  exit 0
fi

[ "$MODE" = activate ] || { echo "Unknown mode"; exit 1; }
[ ! -e "$OVERRIDE" ] || { echo "STOP: Override already installed."; exit 1; }
[ -f "$BENCH" ] || { echo "STOP: Benchmark file missing."; exit 1; }

# Use a fresh benchmark from the past 30 minutes, matching ALL 16 frozen
# adapters. Allow honest NO_RECOMMENDATION but no model exceptions/timeouts.
"$PY" - "$BENCH" <<'PY' || exit 1
import json,sys,time
from pathlib import Path
from research.v38_readonly_resource_probe import ALL
p=Path(sys.argv[1])
if time.time()-p.stat().st_mtime>1800:
    raise SystemExit("STOP: benchmark evidence older than 30 minutes")
data=json.loads(p.read_text(encoding="utf-8"))
rows=data.get("items",[])
if len(rows)!=16 or {r.get("item") for r in rows}!=set(ALL):
    raise SystemExit("STOP: benchmark did not include exact 16 adapters")
if data.get("tested_count")!=16:
    raise SystemExit("STOP: not all workers ran")
allowed={"RESEARCH_PROPOSAL_ONLY","NO_RECOMMENDATION"}
failures=[r for r in rows if r.get("status") not in allowed]
if failures:
    raise SystemExit("STOP: Worker failures or unsupported status: "+str(failures))
total=float(data.get("total_elapsed_seconds",1e9))
if total*4>180:
    raise SystemExit("STOP: estimated 25%-CPU wall time >180s: "+str(total*4))
print("Passed conservative admission; benchmark:",round(total,2),"seconds")
PY

curl -fsS --max-time 10 http://127.0.0.1:8000/api/catalog >/dev/null || exit 1
"$PY" - "$STOCK" <<'PY' || exit 1
import sys,sqlite3,time
from pathlib import Path
p=Path(sys.argv[1]).resolve(strict=True)
with sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=2) as db:
    stamp=db.execute("""SELECT MAX(timestamp) FROM poll_heartbeats
        WHERE mode='poll-cycle' AND success=1""").fetchone()[0]
age=time.time()-stamp if stamp is not None else 1e9
if not 0<=age<=120: raise SystemExit("STOP: stale collector")
print("Collector heartbeat age:",round(age,1),"s")
PY

# Five-model timer is paused only while overriding the private research
# ExecStart. Existing CPU/memory quota, sandbox and timer remain unchanged.
sudo systemctl stop "$TIMER" || exit 1
for i in $(seq 1 55); do
  if ! systemctl is-active --quiet "$SERVICE"; then break; fi
  sleep 1
done
if systemctl is-active --quiet "$SERVICE"; then
  sudo systemctl start "$TIMER"
  echo "STOP: original worker still executing; no changes made."
  exit 1
fi
sudo mkdir -p /etc/systemd/system/torn-fren-v38-private-shadow.service.d || {
  sudo systemctl start "$TIMER"; exit 1;
}
if ! printf '%s\n' \
    '[Service]' \
    'ExecStart=' \
    "ExecStart=$PY -m research.v38_budgeted_runner --execute --db $STOCK --sidecar $SIDECAR --max-jobs 16 --per-worker 30 --budget 220 --max-rows 10000" |
    sudo tee "$OVERRIDE" >/dev/null; then
  sudo rm -f "$OVERRIDE"
  sudo systemctl start "$TIMER"
  exit 1
fi
sudo systemctl daemon-reload || exit 1
if ! sudo systemctl start "$TIMER"; then
  sudo rm -f "$OVERRIDE"
  sudo systemctl daemon-reload
  sudo systemctl start "$TIMER"
  exit 1
fi
echo "Configured 16-worker private timer; V41 website reads its sidecar."
echo "If any scheduled cycle strains resources, run:"
echo "bash $ROOT/deploy/scripts/v42_expand_16_shadow.sh rollback"
