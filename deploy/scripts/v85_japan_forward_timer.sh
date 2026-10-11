#!/usr/bin/env bash
# V85 opt-in private Japan forward capture. Never change public routing.
# Usage: bash deploy/scripts/v85_japan_forward_timer.sh status|enable|disable
set -euo pipefail
export SYSTEMD_PAGER=cat
[[ "$(id -un)" == ubuntu ]] || { echo "STOP: ubuntu user required"; exit 1; }
cd /home/ubuntu/torn-fren-v38-probe
action="${1:-status}"
service=torn-fren-v85-japan-forward.service
timer=torn-fren-v85-japan-forward.timer
src_service=deploy/systemd/"$service"
src_timer=deploy/systemd/"$timer"
dst_service=/etc/systemd/system/"$service"
dst_timer=/etc/systemd/system/"$timer"
if [[ "$action" == status ]]; then
  echo "===== JAPAN RESEARCH SCHEDULE ====="
  systemctl is-active "$timer" || true
  systemctl list-timers --all "$timer" --no-pager
  systemctl show "$service" -p ActiveState -p SubState -p Result -p ExecMainStatus -p TimeoutStartUSec -p CPUQuotaPerSecUSec -p MemoryMax --no-pager
  .venv/bin/python -m research.v84_japan_forward_canary --status
  exit 0
fi
if [[ "$action" == disable ]]; then
  sudo systemctl disable --now "$timer"
  echo "Japan V85 timer disabled; V75 and V82 unchanged."
  exit 0
fi
[[ "$action" == enable ]] || { echo "Usage: status|enable|disable"; exit 2; }
test -z "$(git status --porcelain)" || { echo "STOP: research checkout dirty"; exit 1; }
test -f "$src_service" && test -f "$src_timer" || { echo "STOP: V85 unit files missing"; exit 1; }
systemctl is-active --quiet torn-fren-v38-private-shadow.timer || { echo "STOP: V75 timer inactive"; exit 1; }
# During a guarded research-code checkout, V82's enabled timer is
# intentionally paused. Require that it remains enabled, not actively firing.
systemctl is-enabled --quiet torn-fren-v82-pair-forward.timer || { echo "STOP: V82 timer not enabled"; exit 1; }
test -d /home/ubuntu/torn-fren-private-models || { echo "STOP: missing private research directory"; exit 1; }
test -f /opt/torn-fren/data/stock_history.db || { echo "STOP: collector missing"; exit 1; }
echo "===== V84 UNIT TESTS ====="
.venv/bin/python -m unittest discover -s tests -p 'test_v84_japan_forward_canary.py' -q
echo "===== SYSTEMD UNIT VALIDATION ====="
systemd-analyze calendar '*-*-* *:04/5:40' >/dev/null
sudo systemd-analyze verify "$src_service" "$src_timer"
if sudo test -e "$dst_service" && ! sudo cmp -s "$src_service" "$dst_service"; then
  echo "STOP: installed Japan service not identical to versioned file"; exit 1
fi
if sudo test -e "$dst_timer" && ! sudo cmp -s "$src_timer" "$dst_timer"; then
  echo "STOP: installed Japan timer not identical to versioned file"; exit 1
fi
if systemctl is-active --quiet "$timer"; then
  echo "V85 timer already active; no installation changes."
  systemctl list-timers --all "$timer" --no-pager
  exit 0
fi
sudo install -o root -g root -m 0644 "$src_service" "$dst_service"
sudo install -o root -g root -m 0644 "$src_timer" "$dst_timer"
sudo systemctl daemon-reload
sudo systemctl enable --now "$timer"
systemctl is-active --quiet "$timer" || { echo "STOP: V85 timer not active"; exit 1; }
echo "===== V85 JAPAN TIMER ENABLED ====="
systemctl list-timers --all "$timer" --no-pager
echo "Only V85 timer enabled; V75/V82/website/poller/bot unchanged."
