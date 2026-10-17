#!/usr/bin/env bash
# Japan Xanax V8 checkpoint-inspired candidate, read-only VM probe ONLY.
# Current V42 18-model timer is paused temporarily; restored even on failure.
# Will not publish Japan Xanax to website or modify the collector.
set -euo pipefail
ROOT=/home/ubuntu/torn-fren-v38-probe
PY="$ROOT/.venv/bin/python"
STOCK=/opt/torn-fren/data/stock_history.db
TIMER=torn-fren-v38-private-shadow.timer
WORKER=torn-fren-v38-private-shadow.service
test "$(id -un)" = ubuntu
test -x "$PY"
test -f "$STOCK"
test -z "$(git -C "$ROOT" status --porcelain)"
for s in torn-fren-poller torn-fren-web torn-fren-bot; do
  systemctl is-active --quiet "$s.service" || { echo "STOP: $s inactive."; exit 1; }
done
systemctl is-active --quiet "$TIMER"
sudo systemctl stop "$TIMER"
trap 'sudo systemctl start torn-fren-v38-private-shadow.timer >/dev/null 2>&1 || true' EXIT
for n in $(seq 1 245); do
  if ! systemctl is-active --quiet "$WORKER"; then break; fi
  sleep 1
done
if systemctl is-active --quiet "$WORKER"; then
  echo "STOP: research worker still running."
  exit 1
fi
cd "$ROOT"
NOW=$(date +%s)
echo "Read-only Japan Xanax candidate; CPUQuota=25%, MemoryMax=1GiB, 80s deadline."
sudo systemd-run --unit=torn-fren-v43-japan-probe \
  --collect --wait --pipe --working-directory="$ROOT" \
  -p CPUQuota=25% -p MemoryMax=1073741824 \
  -p Nice=19 -p TimeoutStartSec=80 \
  "$PY" -m research.japan_xanax.v8_regime_candidate \
  --db "$STOCK" --country jap --item Xanax --now "$NOW"
echo "Probe only: Japan Xanax remains blocked pending retrospective parity audit."
