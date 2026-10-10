#!/usr/bin/env bash
# V49 Lion/Panda exact two-expert research cost probe.
# Usage: bash deploy/scripts/v49_lion_panda_pair_probe.sh lion|panda
# Does NOT stop V48 and does NOT change V44/V48 scheduling.
set -euo pipefail
TARGET=lion
if [ "$#" -gt 0 ]; then TARGET="$1"; fi
case "$TARGET" in lion|panda) ;; *)
  echo "Usage: $0 lion|panda"; exit 2 ;; esac

ROOT=/home/ubuntu/torn-fren-v38-probe
PY="$ROOT/.venv/bin/python"
STOCK=/opt/torn-fren/data/stock_history.db
UNIT="torn-fren-v49-$TARGET-expert-pair"
test "$(id -un)" = ubuntu
test -x "$PY"
test -f "$STOCK"
test -z "$(git -C "$ROOT" status --porcelain)"
for s in torn-fren-web.service torn-fren-poller.service torn-fren-bot.service torn-fren-v38-private-shadow.timer torn-fren-v48-cache-warmup.timer; do
  systemctl is-active --quiet "$s" || {
    echo "STOP: $s not active. No models were modified."
    exit 1
  }
done
# Do not intentionally pause either ongoing researcher.
if systemctl is-active --quiet torn-fren-v38-private-shadow.service; then
  echo "DEFERRED: 19-model research cycle is running. Retry shortly."
  exit 0
fi
cd "$ROOT"
echo "V49 $TARGET original analog pair, CPU=15%, RAM=1GiB, no ML weights, read-only."
sudo systemd-run --unit="$UNIT" --collect --wait --pipe \
  --working-directory="$ROOT" \
  -p User=ubuntu -p Group=ubuntu \
  -p CPUQuota=15% -p MemoryMax=1073741824 \
  -p Nice=19 -p IOSchedulingClass=idle \
  -p TimeoutStartSec=110 \
  -p NoNewPrivileges=yes -p ProtectSystem=strict \
  -p ProtectHome=read-only -p PrivateTmp=yes \
  "$PY" -m research.v49_lion_panda_pair_probe \
  --db "$STOCK" --target "$TARGET" --now "$(date +%s)"
echo "V49 pair probe finished. 19-model and cache timers unchanged."
