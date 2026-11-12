#!/usr/bin/env bash
# V77: guarded experimental-page V75 source switch and independent rollback.
set -euo pipefail
export SYSTEMD_PAGER=cat
[[ "$(id -un)" == ubuntu ]] || { echo "STOP: run as ubuntu"; exit 1; }
ACTION="$1"
WEB=torn-fren-web.service
V73=/etc/systemd/system/torn-fren-web.service.d/v73-v72-beta-snapshot.conf
V77=/etc/systemd/system/torn-fren-web.service.d/v77-chamois21-beta.conf
OLD=/var/lib/torn-fren-v38/v72_private_predictions.db
NEW=/var/lib/torn-fren-v38/v75_private_predictions.db
API=http://127.0.0.1:8000/api/experimental/v41/predictions
if [[ "$ACTION" == status ]]; then
  sudo test -e "$V77" && echo "V77 installed" || echo "V77 not installed"
  systemctl show "$WEB" -p MainPID -p ActiveState -p DropInPaths --no-pager
  exit 0
fi
[[ "$ACTION" == enable || "$ACTION" == rollback ]] || { echo "status|enable|rollback"; exit 2; }
sudo test -f "$V73" || { echo "STOP: missing V73 fallback"; exit 1; }
if [[ "$ACTION" == enable ]]; then
  sudo test ! -e "$V77" || { echo "STOP: V77 already exists"; exit 1; }
  sudo -u ubuntu python3 - <<'PY'
import sqlite3,time
p="/var/lib/torn-fren-v38/v75_private_predictions.db"
with sqlite3.connect(f"file:{p}?mode=ro",uri=True) as c:
    rows=c.execute("SELECT item_key,computed_at FROM latest_predictions").fetchall()
keys={key for key,t in rows}
assert len(keys)==21 and {"arg:Monkey Plushie","swi:Chamois Plushie"} <= keys
assert time.time()-max(t for _,t in rows)<360
print("V75 sidecar: 21 rows including Chamois; latest tick within six minutes")
PY
fi
RESTORE=0
rollback_after_failure() {
  [[ "$RESTORE" == 0 ]] && return
  echo "Web verification failed. Restoring previous V73 configuration."
  sudo rm -f "$V77"
  sudo systemctl daemon-reload
  sudo systemctl restart "$WEB"
}
trap rollback_after_failure EXIT
if [[ "$ACTION" == enable ]]; then
  RESTORE=1
  printf '[Service]\nEnvironment=TORN_FREN_V41_SNAPSHOT_DB=%s\n' "$NEW" |
    sudo tee "$V77" >/dev/null
else
  sudo test -f "$V77" || { echo "Already using V73"; exit 0; }
  sudo rm -f "$V77"
fi
sudo systemctl daemon-reload
sudo systemctl restart "$WEB"
UP=0
for i in $(seq 1 30); do
  if systemctl is-active --quiet "$WEB" &&
      curl -fsS --max-time 3 "$API" >/dev/null 2>&1; then
    UP=1;break
  fi
  sleep 2
done
[[ "$UP" == 1 ]] || { echo "STOP: web API not ready"; exit 1; }
PID="$(systemctl show "$WEB" -p MainPID --value)"
CURRENT="$(sudo tr '\0' '\n' < "/proc/$PID/environ" |
    grep '^TORN_FREN_V41_SNAPSHOT_DB=' || true)"
if [[ "$ACTION" == enable ]]; then
  [[ "$CURRENT" == "TORN_FREN_V41_SNAPSHOT_DB=$NEW" ]] || exit 1
  curl -fsS --max-time 8 "$API" | python3 -c '
import json,sys
d=json.load(sys.stdin)
r=d if isinstance(d,list) else next((d[k] for k in ("latest","rows","predictions","items") if isinstance(d.get(k),list)),[])
ks={x.get("item_key") for x in r}
assert len(r)==21 and {"swi:Chamois Plushie","arg:Monkey Plushie"} <= ks
print("Experimental API: 21 private research records")
'
else
  [[ "$CURRENT" == "TORN_FREN_V41_SNAPSHOT_DB=$OLD" ]] || exit 1
fi
RESTORE=0
trap - EXIT
echo "V77 experimental data source $ACTION successful: $CURRENT"
