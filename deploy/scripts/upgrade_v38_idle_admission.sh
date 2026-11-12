#!/usr/bin/env bash
# V38 independent five-item private shadow CPU admission update ONLY.
# Opt-in is never set on website, bot, poller, or V39 audit service.
set -euo pipefail
EXPECTED_PROD="dd84271a40b6e5dac2551c9fbb1291f47463c057"
REF="research/v38-full-roster-live-prep-20261009"
TARGET="${1:-}"
ROOT="/home/ubuntu/torn-fren-v38-probe"
if [[ ! "$TARGET" =~ ^[0-9a-f]{40}$ ]]; then
  echo "STOP: expected tested 40-hex commit" >&2; exit 2
fi
test "$(git -C /opt/torn-fren rev-parse HEAD)" = "$EXPECTED_PROD"
for s in torn-fren-poller.service torn-fren-web.service torn-fren-bot.service \
  torn-fren-routine-audit.timer torn-fren-v38-private-shadow.timer; do
  test "$(systemctl is-active "$s")" = active
done
curl -fsS --connect-timeout 3 --max-time 15 \
  http://127.0.0.1:8000/api/catalog >/dev/null
cd "$ROOT"
test -z "$(git status --porcelain)"
git fetch origin "$REF"
test "$(git rev-parse FETCH_HEAD)" = "$TARGET"
git merge-base --is-ancestor HEAD FETCH_HEAD
git merge --ff-only FETCH_HEAD
test "$(git rev-parse HEAD)" = "$TARGET"
.venv/bin/python -m unittest discover -s tests -p test_v38_idle_admission.py -q
.venv/bin/python -m unittest discover -s tests -p test_v38_capacity_guard.py -q
.venv/bin/python -m py_compile research/v38_idle_admission.py research/v38_capacity_guard.py
UNIT=deploy/systemd/torn-fren-v38-private-shadow.service
grep -Fx "CPUQuota=25%" "$UNIT"
grep -Fx "Nice=19" "$UNIT"
grep -Fx "Environment=TORN_FREN_V38_IDLE_ADMISSION=1" "$UNIT"
grep -Fx "ReadOnlyPaths=/opt/torn-fren/data" "$UNIT"
grep -Fx "ReadWritePaths=/var/lib/torn-fren-v38" "$UNIT"
test "$(systemctl is-active torn-fren-v38-private-shadow.service)" != active || {
  echo "STOP: five-model worker currently running; wait for completion" >&2
  exit 2
}
# Backup original systemd unit in the isolated research folder. Do not
# modify stock SQLite or touch public services.
stamp=$(date -u +%Y%m%dT%H%M%SZ)
cp /etc/systemd/system/torn-fren-v38-private-shadow.service \
  "$ROOT/private-shadow-before-idle-admission-$stamp.service"
sudo install -m 644 "$UNIT" /etc/systemd/system/torn-fren-v38-private-shadow.service
sudo systemctl daemon-reload
sudo systemd-analyze verify /etc/systemd/system/torn-fren-v38-private-shadow.service
echo "===== PRIVATE TIMER ACTIVE; NO FORCED MODEL EXECUTION ====="
systemctl list-timers --all torn-fren-v38-private-shadow.timer
systemctl show torn-fren-v38-private-shadow.service \
    -p Environment -p CPUQuotaPerSecUSec -p MemoryMax
echo "DONE. Next five-minute tick samples CPU idle+PSI before attempting research."
