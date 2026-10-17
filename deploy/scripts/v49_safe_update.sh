#!/usr/bin/env bash
# V49 guarded checkout while keeping V44 and V48 enabled.
# Run after 'git fetch origin research/v38-full-roster-live-prep-20261009'.
# Both timers are restored via EXIT trap, even if checkout fails.
set -euo pipefail
ROOT=/home/ubuntu/torn-fren-v38-probe
COMMIT="$(git rev-parse FETCH_HEAD)"
V44=torn-fren-v38-private-shadow
V48=torn-fren-v48-cache-warmup
cd "$ROOT"
test "$(id -un)" = ubuntu
test -z "$(git status --porcelain)"
git cat-file -e "$COMMIT^{commit}"
for u in "$V44.timer" "$V48.timer"; do
  systemctl is-active --quiet "$u" || {
    echo "STOP: $u inactive. No timers modified."
    exit 1
  }
done
restore() {
  sudo systemctl start "$V44.timer" "$V48.timer" || true
}
trap restore EXIT
sudo systemctl stop "$V44.timer" "$V48.timer"
wait_done() {
  local unit="$1" state
  for _ in $(seq 1 140); do
    state="$(systemctl show -p ActiveState --value "$unit")"
    case "$state" in
      inactive|failed) return 0 ;;
      *) sleep 2 ;;
    esac
  done
  echo "STOP: $unit still active or activating after wait."
  return 1
}
wait_done "$V44.service"
wait_done "$V48.service"
git switch --detach "$COMMIT"
echo "V49 diagnostic code installed; both existing timer configurations unchanged."
