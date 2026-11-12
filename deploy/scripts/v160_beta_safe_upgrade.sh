#!/usr/bin/env bash
# Upgrade ONLY the already-running loopback V160 private beta viewer.
# The independent five-minute V160 prospective recorder is NOT altered.
set -euo pipefail
[[ "$(id -un)" == "ubuntu" ]] || { echo "STOP: expected ubuntu"; exit 1; }
UNIT=torn-fren-v160-beta-board.service
CODE=/home/ubuntu/torn-fren-private-models/v160_beta_board.py
WORK=/home/ubuntu/torn-fren-v38-probe
ROSTER=/home/ubuntu/torn-fren-private-models/v160_stage/pinned/research/v38_roster.json
LEDGER=/var/lib/torn-fren-v38/v160_v151_prospective24.db
BRANCH=research/v38-full-roster-live-prep-20261009
# CI-verified file revision; upgrade never uses moving origin HEAD for code.
PIN=b98d1e92166dcfc1e0c0fd0d2043e16c18e337e5

systemctl is-active --quiet "$UNIT" || { echo "STOP: private beta service is not active"; exit 1; }
systemctl is-enabled --quiet "$UNIT" || { echo "STOP: private beta service is not enabled"; exit 1; }
test -r "$LEDGER" && test -r "$ROSTER" && test -f "$CODE" ||
  { echo "STOP: private beta source / roster / ledger absent"; exit 1; }
test ! -L "$CODE" && test ! -L "$ROSTER" && test ! -L "$LEDGER" ||
  { echo "STOP: unexpected symlink"; exit 1; }
[[ "$(git -C "$WORK" rev-parse --show-toplevel 2>/dev/null || true)" == "$WORK" ]] ||
  { echo "STOP: incorrect Git research checkout"; exit 1; }
cd "$WORK"
git fetch -q origin "$BRANCH"
git cat-file -e "$PIN^{commit}"

NEW="$(mktemp /home/ubuntu/torn-fren-private-models/.v160-new.XXXXXXXX)"
BACKUP="$(mktemp /home/ubuntu/torn-fren-private-models/.v160-backup.XXXXXXXX)"
trap 'rm -f "$NEW" "$BACKUP"' EXIT
git show "$PIN:deploy/scripts/v160_private_beta_board.py" > "$NEW"
python3 -m py_compile "$NEW"
cp -p "$CODE" "$BACKUP"
if cmp -s "$NEW" "$CODE"; then
  echo "Private beta already has this exact revision; no restart needed."
  exit 0
fi

# Execute the NEW reader against the ACTUAL immutable 24-item ledger before
# touching the running service. Do not substitute synthetic fixture data.
python3 -I - "$NEW" <<'PY'
import json,runpy,sys
m=runpy.run_path(sys.argv[1])
r=m["snapshot"]()
signals={
    "upcoming_or_due":0,"recent_now_recheck":0,"no_current_candidate":0
}
for item in r["items"]:
    states={v["signal"] for v in item["models"].values()}
    if "FUTURE_WATCH" in states or "DUE_NOW" in states:
        signals["upcoming_or_due"]+=1
    elif "RECENT_ISSUED_NOW_RECHECK" in states:
        signals["recent_now_recheck"]+=1
    else:
        signals["no_current_candidate"]+=1
print(json.dumps({"preview":"VERIFIED_LIVE_V160_DECISION_FEED",
    "issued_epoch":r["issued_epoch"],"roster":r["recorded_items"],
    "fresh":r["healthy"],"signals":signals},sort_keys=True))
if not r["healthy"] or r["recorded_items"]!=24:
    raise SystemExit("STOP: current V160 issue stale or incomplete; no upgrade")
PY

# Everything touched below is the *separate new private beta* service only.
# If the upgrade fails, restore its old executable and start it again.
restore() {
  echo "Private beta check failed; restoring its previous executable..."
  install -m 0700 "$BACKUP" "$CODE"
  sudo systemctl restart "$UNIT" || true
}
install -m 0700 "$NEW" "$CODE"
if ! sudo systemctl restart "$UNIT"; then
  restore
  exit 1
fi

# Probe both freshly loaded HTML and 24-item API response.
good=0
for attempt in 1 2 3; do
  if python3 - <<'PY'
import json,urllib.request
base="http://127.0.0.1:8765"
with urllib.request.urlopen(base+"/",timeout=3) as f:
    page=f.read(180000).decode("utf-8")
    assert f.status==200 and "Where should I fly?" in page
with urllib.request.urlopen(base+"/api/live",timeout=3) as f:
    data=json.load(f)
    assert f.status==200 and data["healthy"]
    assert len(data["items"])==24
    assert all(len(v["models"])==2 for v in data["items"])
print("NEW_PRIVATE_BETA_HTTP_PASS 24/24")
PY
  then good=1; break; fi
  sleep 2
done
if [[ "$good" != 1 ]]; then
  restore
  echo "STOP: new beta failed HTTP self-check; previous code restored."
  exit 1
fi
echo "SUCCESS: revised private departure board running."
echo "Refresh http://127.0.0.1:8765/ in your existing SSH tunnel."
echo "V160 collector/recorder, existing original V2 graph and /experimental unchanged."
