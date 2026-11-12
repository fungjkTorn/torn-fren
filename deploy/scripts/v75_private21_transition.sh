#!/usr/bin/env bash
# Guarded V75 private 21-model switch, V72 intact for rollback.
# Operator runs only AFTER separate V75 one-shot passes under VM caps.
# Usage: bash deploy/scripts/v75_private21_transition.sh status|enable|rollback
set -euo pipefail
export SYSTEMD_PAGER=cat
cd /home/ubuntu/torn-fren-v38-probe
[[ "$(id -un)" == ubuntu ]] || { echo "STOP: run as ubuntu"; exit 1; }
ACTION="${1:-}"
UNIT=torn-fren-v38-private-shadow
SERVICE="$UNIT.service"
TIMER="$UNIT.timer"
V48=torn-fren-v48-cache-warmup.timer
DIR="/etc/systemd/system/$SERVICE.d"
V72="$DIR/v72-private-mirror20.conf"
OVERRIDE="$DIR/v75-private-mirror21.conf"
SOURCE="deploy/systemd/v75-private-mirror21.conf"

if [[ "$ACTION" == status ]]; then
  echo "===== RESEARCH SERVICE ====="
  systemctl show "$SERVICE" -p ActiveState -p ExecStart --no-pager
  echo "===== V72 FALLBACK ====="
  sudo test -f "$V72" && echo "present" || echo "missing"
  echo "===== V75 OVERLAY ====="
  sudo test -f "$OVERRIDE" && echo "present" || echo "absent"
  systemctl is-active "$TIMER" "$V48" || true
  exit 0
fi

[[ "$ACTION" == enable || "$ACTION" == rollback ]] || { echo "status|enable|rollback required"; exit 2; }
systemctl is-active --quiet "$TIMER" || { echo "STOP: research timer inactive"; exit 1; }
systemctl is-active --quiet "$V48" || { echo "STOP: V48 timer inactive"; exit 1; }
sudo test -f "$V72" || { echo "STOP: V72 rollback drop-in missing"; exit 1; }
test -f "$SOURCE" || { echo "STOP: V75 source drop-in absent"; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "STOP: dirty research checkout"; exit 1; }
if sudo test -e "$OVERRIDE" && ! sudo cmp -s "$SOURCE" "$OVERRIDE"; then
  echo "STOP: installed V75 drop-in differs from audited source"
  exit 1
fi
RESTORE=0
restore() { [[ "$RESTORE" == 0 ]] || sudo systemctl start "$TIMER" || true; }
trap restore EXIT

sudo systemctl stop "$TIMER"
RESTORE=1
for i in $(seq 1 140); do
  STATE="$(systemctl show "$SERVICE" -p ActiveState --value)"
  if [[ "$STATE" == inactive || "$STATE" == failed ]]; then break; fi
  sleep 2
done
[[ "$STATE" == inactive || "$STATE" == failed ]] || {
  echo "STOP: worker not idle; timer restored by trap"; exit 1;
}

if [[ "$ACTION" == enable ]]; then
  sudo install -o root -g root -m 0644 "$SOURCE" "$OVERRIDE"
else
  sudo rm -f -- "$OVERRIDE"
fi
sudo systemctl daemon-reload
EFFECTIVE="$(systemctl show "$SERVICE" -p ExecStart --value)"
if [[ "$ACTION" == enable ]]; then
  [[ "$EFFECTIVE" == *"research.v75_private21_chamois_smoke"* ]] || {
    echo "STOP: V75 override not effective; reverting"
    sudo rm -f "$OVERRIDE"
    sudo systemctl daemon-reload
    exit 1
  }
else
  [[ "$EFFECTIVE" == *"research.v72_private_mirror20_shadow_tick"* ]] || {
    echo "STOP: rollback did not restore V72; inspect overrides"
    exit 1
  }
fi
sudo systemctl start "$TIMER"
RESTORE=0
trap - EXIT
echo "V75 protected research transition: $ACTION"
systemctl is-active "$TIMER" "$V48"
systemctl show "$SERVICE" -p ExecStart --value
echo "Public web/poller/bot and V48 cache untouched; website still reads V72."
