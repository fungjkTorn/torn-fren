#!/usr/bin/env bash
# V82 opt-in independent private Lion/Panda forward comparison timer.
# Uses only its own units. Never stops/restarts V75, cache, web, bot or collector.
# Usage: bash deploy/scripts/v82_pair_forward_timer.sh status|enable|disable
set -euo pipefail
export SYSTEMD_PAGER=cat
[[ "$(id -un)" == "ubuntu" ]] || { echo "STOP: use ubuntu user"; exit 1; }
cd /home/ubuntu/torn-fren-v38-probe
ACTION="$1"
SERVICE=torn-fren-v82-pair-forward.service
TIMER=torn-fren-v82-pair-forward.timer
SRC_S=deploy/systemd/"$SERVICE"
SRC_T=deploy/systemd/"$TIMER"
DST_S=/etc/systemd/system/"$SERVICE"
DST_T=/etc/systemd/system/"$TIMER"

if [[ "$ACTION" == "status" ]]; then
  echo "===== V82 TIMER ====="
  systemctl list-timers --all "$TIMER" --no-pager
  echo "===== V82 SERVICE ====="
  systemctl show "$SERVICE" -p ActiveState -p SubState -p Result -p ExecStart -p CPUQuotaPerSecUSec -p MemoryMax --no-pager || true
  echo "===== PRIVATE LEDGER ====="
  .venv/bin/python -m research.v81_pair_forward_comparison --status
  exit 0
fi
if [[ "$ACTION" == "disable" ]]; then
  sudo systemctl disable --now "$TIMER" || true
  echo "V82 disabled. Other timers and research/production services unchanged."
  exit 0
fi
[[ "$ACTION" == "enable" ]] || { echo "Usage: status|enable|disable"; exit 2; }
[[ "$(git status --porcelain)" == "" ]] || { echo "STOP: dirty research checkout"; exit 1; }
test -f "$SRC_S" && test -f "$SRC_T" || { echo "STOP: missing audited V82 units"; exit 1; }
systemctl is-active --quiet torn-fren-v38-private-shadow.timer || { echo "STOP: V75 timer inactive"; exit 1; }
systemctl is-active --quiet torn-fren-v48-cache-warmup.timer || { echo "STOP: cache timer inactive"; exit 1; }
test -f /home/ubuntu/torn-fren-private-models/lion_selector_artifact.json || { echo "STOP: missing Lion weights"; exit 1; }
test -f /home/ubuntu/torn-fren-private-models/panda_selector_artifact.json || { echo "STOP: missing Panda weights"; exit 1; }
echo "===== V81 RESEARCH TESTS ====="
.venv/bin/python -m unittest discover -s tests -p 'test_v81_pair_forward_comparison.py' -q
echo "===== SYSTEMD UNIT VALIDATION ====="
systemd-analyze calendar '*-*-* *:04/5:00' >/dev/null
sudo systemd-analyze verify "$SRC_S" "$SRC_T"
if sudo test -e "$DST_S" && ! sudo cmp -s "$SRC_S" "$DST_S"; then
  echo "STOP: installed V82 service differs from versioned file"
  exit 1
fi
if sudo test -e "$DST_T" && ! sudo cmp -s "$SRC_T" "$DST_T"; then
  echo "STOP: installed V82 timer differs from versioned file"
  exit 1
fi
if systemctl is-active --quiet "$TIMER"; then
  echo "V82 already active; no changes."
  systemctl list-timers --all "$TIMER" --no-pager
  exit 0
fi
sudo install -o root -g root -m 0644 "$SRC_S" "$DST_S"
sudo install -o root -g root -m 0644 "$SRC_T" "$DST_T"
sudo systemctl daemon-reload
sudo systemctl enable --now "$TIMER"
systemctl is-active --quiet "$TIMER" || { echo "V82 failed to become active"; exit 1; }
echo "===== V82 TIMER ENABLED ====="
systemctl list-timers --all "$TIMER" --no-pager
echo "Only V82 timer enabled; existing V75/cache/web/collector/bot unchanged."
