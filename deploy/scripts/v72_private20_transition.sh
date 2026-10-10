#!/usr/bin/env bash
# V72 research-only 20-model private timer overlay. Production remains untouched.
# Usage: bash deploy/scripts/v72_private20_transition.sh status|enable|rollback
set -euo pipefail
cd /home/ubuntu/torn-fren-v38-probe
[[ "$(id -un)" == "ubuntu" ]] || { echo "STOP: run as ubuntu"; exit 1; }
ACTION="${1:-}"
UNIT=torn-fren-v38-private-shadow
V48=torn-fren-v48-cache-warmup
SERVICE="${UNIT}.service"
TIMER="${UNIT}.timer"
DIR="/etc/systemd/system/${SERVICE}.d"
V65="${DIR}/v65-private-mirror19.conf"
OVERRIDE="${DIR}/v72-private-mirror20.conf"
SOURCE="deploy/systemd/v72-private-mirror20.conf"
if [[ "$ACTION" == "status" ]]; then
  echo "RESEARCH TIMERS"
  systemctl is-active "$TIMER" "${V48}.timer" || true
  echo "CURRENT PRIVATE ExecStart"
  systemctl show -p ExecStart --value "$SERVICE"
  echo "EXISTING V65/V72 OVERLAYS"
  sudo test -f "$V65" && echo "v65 rollback: present" || echo "v65 rollback: missing"
  sudo test -f "$OVERRIDE" && echo "v72 overlay: present" || echo "v72 overlay: absent"
  exit 0
fi
[[ "$ACTION" == "enable" || "$ACTION" == "rollback" ]] || {
  echo "Usage: bash $0 status|enable|rollback"; exit 2;
}
systemctl is-active --quiet "$TIMER" || { echo "STOP: V38 research timer inactive"; exit 1; }
systemctl is-active --quiet "${V48}.timer" || { echo "STOP: V48 cache timer inactive"; exit 1; }
sudo test -f "$V65" || { echo "STOP: V65 fallback override missing"; exit 1; }
test -f "$SOURCE" || { echo "STOP: V72 overlay not in research checkout"; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "STOP: checkout contains uncommitted changes"; exit 1; }
# Never delete an unexpected/admin-modified drop-in.
if sudo test -e "$OVERRIDE" && ! sudo cmp -s "$SOURCE" "$OVERRIDE"; then
  echo "STOP: installed V72 overlay differs from pinned checkout"; exit 1;
fi
RESTORE_TIMER=0
restore_timer() {
  if [[ "$RESTORE_TIMER" == "1" ]]; then
    sudo systemctl start "$TIMER" || true
  fi
}
trap restore_timer EXIT
sudo systemctl stop "$TIMER"
RESTORE_TIMER=1
# Do not kill an ongoing V65/72 calculation; wait for natural completion.
for i in $(seq 1 140); do
  STATE="$(systemctl show "$SERVICE" -p ActiveState --value)"
  if [[ "$STATE" == "inactive" || "$STATE" == "failed" ]]; then
    break
  fi
  sleep 2
done
if [[ "$STATE" != "inactive" && "$STATE" != "failed" ]]; then
  echo "STOP: research service did not become idle; timer will be restarted"
  exit 1
fi
if [[ "$ACTION" == "enable" ]]; then
  sudo install -o root -g root -m 0644 "$SOURCE" "$OVERRIDE"
else
  sudo rm -f -- "$OVERRIDE"
fi
sudo systemctl daemon-reload
EXEC="$(systemctl show "$SERVICE" -p ExecStart --value)"
if [[ "$ACTION" == "enable" ]]; then
  if [[ "$EXEC" != *"research.v72_private_mirror20_shadow_tick"* ]]; then
    echo "STOP: unexpected effective ExecStart; revert new override"
    sudo rm -f -- "$OVERRIDE"
    sudo systemctl daemon-reload
    exit 1
  fi
else
  if [[ "$EXEC" != *"research.v65_private_mirror_shadow_tick"* ]]; then
    echo "STOP: rollback did not restore V65 ExecStart; manual inspection required"
    exit 1
  fi
fi
sudo systemctl start "$TIMER"
RESTORE_TIMER=0
trap - EXIT
echo "V72 private transition: $ACTION"
systemctl is-active "$TIMER" "${V48}.timer"
systemctl show "$SERVICE" -p ExecStart --value
echo "Only research ExecStart overlay modified; V48 and public services unchanged."
