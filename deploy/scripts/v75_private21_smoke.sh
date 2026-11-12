#!/usr/bin/env bash
# One-shot V75 candidate smoke. Does NOT install or switch research timers.
set -euo pipefail
cd /home/ubuntu/torn-fren-v38-probe
test "$(id -un)" = ubuntu || { echo "STOP: run as ubuntu"; exit 1; }
test "$(git status --porcelain)" = "" || { echo "STOP: uncommitted research files"; exit 1; }
systemctl is-active --quiet torn-fren-v38-private-shadow.timer || {
  echo "STOP: private V72 timer inactive"; exit 1;
}
systemctl is-active --quiet torn-fren-v48-cache-warmup.timer || {
  echo "STOP: independent V48 timer inactive"; exit 1;
}
state="$(systemctl show torn-fren-v38-private-shadow.service -p ActiveState --value)"
if [[ "$state" != "inactive" ]]; then
  echo "DEFER: V72 research service is $state; retry in idle interval"
  exit 0
fi
if sudo test -f /etc/systemd/system/torn-fren-v38-private-shadow.service.d/v75-private-mirror21.conf; then
  echo "STOP: V75 override already installed; use status command instead"
  exit 1
fi
echo "V75 protected one-shot 21-model smoke; active V72 and V48 timers remain enabled"
sudo systemd-run \
  --unit="torn-fren-v75-private-one-shot-$(date -u +%H%M%S)" \
  --collect --wait --pipe \
  --working-directory=/home/ubuntu/torn-fren-v38-probe \
  -p User=ubuntu \
  -p Group=ubuntu \
  -p CPUQuota=25% \
  -p MemoryMax=1024M \
  -p Nice=19 \
  -p IOSchedulingClass=idle \
  -p TimeoutStartSec=240 \
  -p NoNewPrivileges=yes \
  -p PrivateTmp=yes \
  -p ProtectHome=read-only \
  -p ProtectSystem=strict \
  -p ReadOnlyPaths=/opt/torn-fren/data \
  -p ReadOnlyPaths=/var/lib/torn-fren-v47 \
  -p ReadWritePaths=/var/lib/torn-fren-v38 \
  -p UMask=0077 \
  -p Environment=OPENBLAS_NUM_THREADS=1 \
  -p Environment=OMP_NUM_THREADS=1 \
  -p Environment=MKL_NUM_THREADS=1 \
  -p Environment=TORN_FREN_V38_IDLE_ADMISSION=1 \
  /home/ubuntu/torn-fren-v38-probe/.venv/bin/python \
  -m research.v75_private21_chamois_smoke
