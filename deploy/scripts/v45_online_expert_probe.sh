#!/usr/bin/env bash
# V45 protected and isolated one-expert historical replay.
# Usage: bash deploy/scripts/v45_online_expert_probe.sh monkey|chamois
# Does not publish any new research models or alter public processes.
set -euo pipefail
TARGET="monkey"
if [ "$#" -gt 0 ]; then TARGET="$1"; fi
case "$TARGET" in monkey|chamois) ;; *) echo "Usage: $0 monkey|chamois"; exit 2 ;; esac
ROOT=/home/ubuntu/torn-fren-v38-probe
PY="$ROOT/.venv/bin/python"
STOCK=/opt/torn-fren/data/stock_history.db
TIMER=torn-fren-v38-private-shadow.timer
SERVICE=torn-fren-v38-private-shadow.service
[ "$(id -un)" = ubuntu ]
test -f "$STOCK"
test -x "$PY"
test -z "$(git -C "$ROOT" status --porcelain)"
for s in torn-fren-web torn-fren-poller torn-fren-bot; do
  systemctl is-active --quiet "$s.service" || { echo "STOP: $s down"; exit 1; }
done
systemctl is-active --quiet "$TIMER"
sudo systemctl stop "$TIMER"
trap 'sudo systemctl start torn-fren-v38-private-shadow.timer >/dev/null 2>&1 || true' EXIT
for n in $(seq 1 245); do
  if ! systemctl is-active --quiet "$SERVICE"; then break; fi
  sleep 1
done
if systemctl is-active --quiet "$SERVICE"; then
  echo "STOP: research cycle still active"
  exit 1
fi
cd "$ROOT"
echo "Probe $TARGET: one original expert (0/24), not an integrated model."
sudo systemd-run --unit="torn-fren-v45-$TARGET-expert0" --collect --wait --pipe \
  --working-directory="$ROOT" \
  -p CPUQuota=25% -p MemoryMax=1073741824 \
  -p Nice=19 -p TimeoutStartSec=100 \
  "$PY" -m research.v45_online_template_probe \
  --db "$STOCK" --target "$TARGET" \
  --expert-index 0 --now "$(date +%s)"
echo "Research-only benchmark complete. Existing 19 models unchanged."
