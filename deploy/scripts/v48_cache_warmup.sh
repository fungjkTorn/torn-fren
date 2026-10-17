#!/usr/bin/env bash
# V48 protected automated research CACHE warmup. Never changes live 19 models.
# bash deploy/scripts/v48_cache_warmup.sh install|status|stop|rollback
set -euo pipefail
MODE=status
if [ "$#" -gt 0 ]; then MODE="$1"; fi
case "$MODE" in install|status|stop|rollback) ;;
*) echo "Usage: $0 install|status|stop|rollback"; exit 2 ;; esac
ROOT=/home/ubuntu/torn-fren-v38-probe
PY="$ROOT/.venv/bin/python"
SVC=torn-fren-v48-cache-warmup.service
TIMER=torn-fren-v48-cache-warmup.timer
SVC_FILE=/etc/systemd/system/torn-fren-v48-cache-warmup.service
TIMER_FILE=/etc/systemd/system/torn-fren-v48-cache-warmup.timer
DIR=/var/lib/torn-fren-v47

if [ "$MODE" = status ]; then
  systemctl is-active "$TIMER" || true
  systemctl show "$SVC" -p ActiveState -p Result -p MemoryPeak -p CPUUsageNSec --no-pager || true
  if [ -x "$PY" ] && [ -f "$ROOT/research/v48_cache_warmup.py" ]; then
    (cd "$ROOT" && "$PY" -m research.v48_cache_warmup --status)
  fi
  echo "Recent V48 research ticks:"
  sudo journalctl -u "$SVC" -n 14 -o cat --no-pager || true
  exit 0
fi

if [ "$MODE" = stop ] || [ "$MODE" = rollback ]; then
  sudo systemctl disable --now "$TIMER" 2>/dev/null || true
  # Do NOT kill a SQLite writer mid-transaction. Wait for final 85s worker.
  for n in $(seq 1 100); do
    if ! systemctl is-active --quiet "$SVC"; then break; fi
    sleep 1
  done
  if systemctl is-active --quiet "$SVC"; then
    echo "STOP: V48 cache writer still active, leaving units intact."
    exit 1
  fi
  if [ "$MODE" = rollback ]; then
    sudo rm -f "$SVC_FILE" "$TIMER_FILE"
    sudo systemctl daemon-reload
    echo "V48 units removed; historical cache retained. V44 untouched."
  else
    echo "V48 background warmup disabled; historical cache retained."
  fi
  exit 0
fi

[ "$(id -un)" = ubuntu ] || { echo "STOP: run as ubuntu."; exit 1; }
test -x "$PY"
test -f /opt/torn-fren/data/stock_history.db
test -z "$(git -C "$ROOT" status --porcelain)"
[ ! -e "$SVC_FILE" ] && [ ! -e "$TIMER_FILE" ] ||
  { echo "STOP: V48 already installed. Use status, stop or rollback."; exit 1; }
for svc in torn-fren-v38-private-shadow.timer torn-fren-web.service torn-fren-poller.service torn-fren-bot.service; do
  systemctl is-active --quiet "$svc" || { echo "STOP: $svc inactive"; exit 1; }
done
systemctl show torn-fren-v38-private-shadow.service -p ExecStart --no-pager |
  grep -q -- '--with-redfox' || { echo "STOP: 19-model Red Fox overlay missing."; exit 1; }
(cd "$ROOT" && "$PY" -m unittest discover -s tests -p 'test_v48_cache_warmup.py' -q)
sudo install -d -o ubuntu -g ubuntu -m 700 "$DIR"

sudo tee "$SVC_FILE" >/dev/null <<'UNIT'
[Unit]
Description=V48 private low-priority Monkey Chamois historical cache backfill
After=local-fs.target
[Service]
Type=oneshot
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/torn-fren-v38-probe
ExecStart=/home/ubuntu/torn-fren-v38-probe/.venv/bin/python -m research.v48_cache_warmup --db /opt/torn-fren/data/stock_history.db --cache /var/lib/torn-fren-v47/online_expert_cache.db --budget 40 --max-decisions 24
CPUQuota=20%
MemoryMax=1073741824
Nice=19
IOSchedulingClass=idle
TimeoutStartSec=85
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/var/lib/torn-fren-v47
UMask=0077
UNIT

sudo tee "$TIMER_FILE" >/dev/null <<'UNIT'
[Unit]
Description=V48 resuming historical expert cache, low priority
[Timer]
OnBootSec=2min
OnUnitInactiveSec=30s
AccuracySec=15s
RandomizedDelaySec=10s
Unit=torn-fren-v48-cache-warmup.service
Persistent=false
[Install]
WantedBy=timers.target
UNIT

sudo systemctl daemon-reload
if ! sudo systemctl enable --now "$TIMER"; then
  sudo rm -f "$SVC_FILE" "$TIMER_FILE"
  sudo systemctl daemon-reload
  echo "STOP: install failed; restored previous configuration."
  exit 1
fi
echo "V48 optional cache-only timer enabled. CPU=20%, Memory=1GiB, max=85s."
echo "19-model V44 scheduler, public bot, collector, website all unchanged."
echo "To inspect: bash $ROOT/deploy/scripts/v48_cache_warmup.sh status"
echo "To disable: bash $ROOT/deploy/scripts/v48_cache_warmup.sh stop"
echo "To remove: bash $ROOT/deploy/scripts/v48_cache_warmup.sh rollback"
