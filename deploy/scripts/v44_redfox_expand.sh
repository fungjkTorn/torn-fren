#!/usr/bin/env bash
# V44 guarded promotion for the source-pinned Red Fox research adapter.
# Usage: bash deploy/scripts/v44_redfox_expand.sh benchmark|activate|rollback
# Only the 18->19 private worker overlay changes. Public web/poller/bot and
# production stock database remain untouched.
set -euo pipefail
MODE=benchmark
if [ "$#" -gt 0 ]; then MODE="$1"; fi
ROOT=/home/ubuntu/torn-fren-v38-probe
PY="$ROOT/.venv/bin/python"
STOCK=/opt/torn-fren/data/stock_history.db
SIDECAR=/var/lib/torn-fren-v38/private_predictions.db
SERVICE=torn-fren-v38-private-shadow.service
TIMER=torn-fren-v38-private-shadow.timer
BASE=/etc/systemd/system/torn-fren-v38-private-shadow.service.d/v42-xanax-addition.conf
OVER=/etc/systemd/system/torn-fren-v38-private-shadow.service.d/v44-redfox19.conf
BENCH=/tmp/torn-fren-v44-redfox-probe.txt
[ "$(id -un)" = ubuntu ] || { echo "STOP: Run as ubuntu."; exit 1; }

# It is always possible to revert only our 19th model without changing code.
if [ "$MODE" = rollback ]; then
  sudo systemctl stop "$TIMER"
  trap 'sudo systemctl start torn-fren-v38-private-shadow.timer >/dev/null 2>&1 || true' EXIT
  for n in $(seq 1 245); do
    if ! systemctl is-active --quiet "$SERVICE"; then break; fi
    sleep 1
  done
  if systemctl is-active --quiet "$SERVICE"; then
    echo "STOP: worker still active. Overlay not removed."
    exit 1
  fi
  sudo rm -f "$OVER"
  sudo systemctl daemon-reload
  echo "19th model removed. Underlying 18-model Xanax overlay is unchanged."
  exit 0
fi

[ "$MODE" = benchmark ] || [ "$MODE" = activate ] ||
  { echo "Usage: $0 benchmark|activate|rollback"; exit 1; }
test -x "$PY"
test -f "$STOCK"
test -f "$BASE"
test -z "$(git -C "$ROOT" status --porcelain)"
systemctl is-active --quiet "$TIMER"
for s in torn-fren-web torn-fren-poller torn-fren-bot; do
  systemctl is-active --quiet "$s.service" ||
    { echo "STOP: $s down."; exit 1; }
done
curl -fsS --max-time 12 http://127.0.0.1:8000/api/catalog >/dev/null

# Must be the installed 18-model config; no implicit reopening of any model.
if ! systemctl show "$SERVICE" -p ExecStart --no-pager | grep -q -- '--with-xanax'; then
  echo "STOP: Existing 18-item Xanax research configuration not detected."
  exit 1
fi
systemctl show "$SERVICE" -p CPUQuotaPerSecUSec -p MemoryMax -p TimeoutStartUSec --no-pager

# Always stop ONLY the research timer and let its current oneshot finish.
sudo systemctl stop "$TIMER"
trap 'sudo systemctl start torn-fren-v38-private-shadow.timer >/dev/null 2>&1 || true' EXIT
for n in $(seq 1 245); do
  if ! systemctl is-active --quiet "$SERVICE"; then break; fi
  sleep 1
done
if systemctl is-active --quiet "$SERVICE"; then
  echo "STOP: prior research worker still executing."
  exit 1
fi
cd "$ROOT"

if [ "$MODE" = benchmark ]; then
  echo "Protected source-pinned Red Fox benchmark, nothing activated."
  # The child process can only read collector history; systemd caps CPU,
  # memory and wall time exactly as for the existing V43 research probe.
  sudo systemd-run --unit=torn-fren-v44-redfox-probe --collect --wait --pipe \
    --working-directory="$ROOT" \
    -p CPUQuota=25% -p MemoryMax=1073741824 -p Nice=19 \
    -p TimeoutStartSec=65 \
    "$PY" -m research.v38_red_fox_single_tick \
    --db "$STOCK" --country uni --item "Red Fox Plushie" \
    --now "$(date +%s)" 2>&1 | tee "$BENCH"
  echo "Benchmark evidence saved to $BENCH; no scheduler changes."
  exit 0
fi

[ ! -f "$OVER" ] || { echo "STOP: Red Fox override already active."; exit 1; }
[ -f "$BENCH" ] || { echo "STOP: Run benchmark before activation."; exit 1; }

"$PY" - "$BENCH" <<'PY'
import json,re,sys,time
from pathlib import Path
p=Path(sys.argv[1])
if time.time()-p.stat().st_mtime>1800:
    raise SystemExit("STOP: benchmark older than 30 minutes")
content=p.read_text(encoding="utf-8")
results=[]
for line in content.splitlines():
    line=line.strip()
    if line.startswith("{") and line.endswith("}"):
        try: results.append(json.loads(line))
        except ValueError: pass
if len(results)!=1:
    raise SystemExit("STOP: benchmark must contain one candidate result")
r=results[0]
if r.get("key")!="uni:Red Fox Plushie" or r.get("model_config")!="red_fox_k18_global_regime_0.5":
    raise SystemExit("STOP: Wrong Red Fox model")
if r.get("status") not in ("RESEARCH_PROPOSAL_ONLY","NO_RECOMMENDATION"):
    raise SystemExit("STOP: Model did not pass readiness")
if "Finished with result: success" not in content or "code=exited/status=0" not in content:
    raise SystemExit("STOP: systemd benchmark did not complete successfully")
m=re.search(r"Service runtime:\s*([0-9.]+)s",content)
if m is None or float(m.group(1))>40:
    raise SystemExit("STOP: Red Fox exceeded 40s private wall budget")
if r.get("probability_calibrated") is True:
    raise SystemExit("STOP: Model unexpectedly claims calibrated probability")
print("Admitted Red Fox from protected VM benchmark:",m.group(1),"seconds")
PY

"$PY" - "$STOCK" <<'PY'
import sqlite3,sys,time
from pathlib import Path
p=Path(sys.argv[1]).resolve(strict=True)
with sqlite3.connect(p.as_uri()+"?mode=ro",uri=True,timeout=2) as c:
    row=c.execute("""SELECT MAX(timestamp) FROM poll_heartbeats
        WHERE mode='poll-cycle' AND success=1""").fetchone()
age=time.time()-row[0] if row and row[0] else 1e9
if not 0<=age<=120:
    raise SystemExit("STOP: collector stale")
print("Collector heartbeat age:",round(age,1),"seconds")
PY

# This lexicographically later drop-in only overrides the private ExecStart.
# Original quotas, timer frequency, sandbox and stock read-only protection
# continue to be inherited from the existing service.
printf '%s\n' \
 '[Service]' \
 'ExecStart=' \
 "ExecStart=$PY -m research.v38_budgeted_runner --execute --with-xanax --with-redfox --db $STOCK --sidecar $SIDECAR --max-jobs 19 --per-worker 30 --budget 220 --max-rows 10000" |
 sudo tee "$OVER" >/dev/null
if ! sudo systemctl daemon-reload; then
  sudo rm -f "$OVER"
  exit 1
fi
echo "Red Fox 19th private adapter configured. Public services unchanged."
echo "After timer restoration run: sudo systemctl start $SERVICE"
echo "To roll back: bash $ROOT/deploy/scripts/v44_redfox_expand.sh rollback"
