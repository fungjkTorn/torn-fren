#!/usr/bin/env bash
# Opt-in replacement of ONLY the existing local V160 research beta viewer.
# Never touch V160 forecast collector/recorder, deployed V2 or /experimental.
set -euo pipefail
[[ "$(id -un)" == ubuntu ]] || { echo "STOP: expected ubuntu user"; exit 1; }
UNIT=torn-fren-v160-beta-board.service
WORK=/home/ubuntu/torn-fren-v38-probe
ROOT=/home/ubuntu/torn-fren-private-models
CODE="$ROOT/v160_beta_board.py"
HELPER="$ROOT/v160_single_item_recheck.py"
LEDGER=/var/lib/torn-fren-v38/v160_v151_prospective24.db
BRANCH=research/v38-full-roster-live-prep-20261009
PIN=58da25f27eedb444fdd3bc5251fd95253c963c48

if ! systemctl is-active --quiet "$UNIT"; then
 echo "STOP previous private beta viewer inactive; no attempted upgrade"
 systemctl show "$UNIT" -p ActiveState -p SubState -p Result -p ExecMainStatus --no-pager || true
 sudo journalctl -u "$UNIT" -n 25 --no-pager -o short-iso || true
 exit 1
fi
systemctl is-enabled --quiet "$UNIT" || { echo "STOP private beta not enabled"; exit 1; }
test -f "$CODE" && test -r "$LEDGER" && test -x "$WORK/.venv/bin/python" ||
 { echo "STOP private viewer, research ledger or research venv unavailable"; exit 1; }
test ! -L "$CODE" && test ! -L "$HELPER" && test ! -L "$LEDGER" ||
 { echo "STOP unexpected symlink"; exit 1; }
[[ "$(git -C "$WORK" rev-parse --show-toplevel 2>/dev/null || true)" == "$WORK" ]] ||
 { echo "STOP expected research checkout missing"; exit 1; }

cd "$WORK"
git fetch -q origin "$BRANCH"
git cat-file -e "$PIN^{commit}"

NEW="$(mktemp "$ROOT/.v160-board-new.XXXXXXXX")"
NEW_HELPER="$(mktemp "$ROOT/.v160-check-new.XXXXXXXX")"
OLD="$(mktemp "$ROOT/.v160-board-old.XXXXXXXX")"
OLD_HELPER="$(mktemp "$ROOT/.v160-check-old.XXXXXXXX")"
PROBE="$(mktemp "$ROOT/.v160-beta-probe.XXXXXXXX")"
trap 'rm -f "$NEW" "$NEW_HELPER" "$OLD" "$OLD_HELPER" "$PROBE"' EXIT

git show "$PIN:deploy/scripts/v160_private_beta_board.py" > "$NEW"
git show "$PIN:deploy/scripts/v160_single_item_recheck.py" > "$NEW_HELPER"
git show "$PIN:deploy/scripts/v160_beta_http_readiness.py" > "$PROBE"
python3 -m py_compile "$NEW" "$NEW_HELPER" "$PROBE"
cp -p "$CODE" "$OLD"
HAS_OLD_HELPER=0
if [[ -f "$HELPER" ]]; then
 cp -p "$HELPER" "$OLD_HELPER"
 HAS_OLD_HELPER=1
fi

echo "===== REAL PRIVATE 24-ITEM LEDGER PRECHECK ====="
python3 -I - "$NEW" <<'PY'
import json,runpy,sys
m=runpy.run_path(sys.argv[1])
data=m["snapshot"]()
counts={"upcoming_or_due":0,"recent_now_recheck":0,"other":0}
for item in data["items"]:
    states={x["signal"] for x in item["models"].values()}
    if "FUTURE_WATCH" in states or "DUE_NOW" in states:
        counts["upcoming_or_due"]+=1
    elif "RECENT_ISSUED_NOW_RECHECK" in states:
        counts["recent_now_recheck"]+=1
    else:
        counts["other"]+=1
print(json.dumps({"fresh":data["healthy"],"recorded":data["recorded_items"],
                  "signals":counts},sort_keys=True))
if not data["healthy"] or data["recorded_items"]!=24:
    raise SystemExit("STOP: must have fresh complete 24-item research ledger")
PY

echo "===== CURRENT SINGLE-ITEM READ-ONLY MODEL PREFLIGHT ====="
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
 timeout 65s nice -n 19 "$WORK/.venv/bin/python" -I "$NEW_HELPER" \
 "mex:Jaguar Plushie"

diagnostics() {
 echo "===== PRIVATE VIEWER STATUS (collector/other units untouched) ====="
 systemctl show "$UNIT" -p ActiveState -p SubState -p Result -p ExecMainStatus -p NRestarts --no-pager || true
 echo "===== PRIVATE VIEWER RECENT LOG ====="
 sudo journalctl -u "$UNIT" -n 35 --no-pager -o short-iso || true
}
restore() {
 echo "Restoring previous beta viewer only."
 install -m 0700 "$OLD" "$CODE"
 if [[ "$HAS_OLD_HELPER" == 1 ]]; then
   install -m 0700 "$OLD_HELPER" "$HELPER"
 else
   rm -f "$HELPER"
 fi
 if ! sudo systemctl restart "$UNIT"; then
   diagnostics
   echo "STOP rollback restart failed; manual investigation required"
   return 1
 fi
 if ! python3 -I "$PROBE" --mode rollback --wait 25; then
   diagnostics
   echo "STOP rollback page not healthy; manual investigation required"
   return 1
 fi
 echo "ROLLBACK VERIFIED: previous private viewer serves all 24 items."
}

# Replace only the dedicated private viewer executable/helper.
install -m 0700 "$NEW_HELPER" "$HELPER"
install -m 0700 "$NEW" "$CODE"
if ! sudo systemctl restart "$UNIT"; then
 diagnostics
 restore
 exit 1
fi

echo "===== BOUNDED NEW PRIVATE PAGE STARTUP & API READINESS ====="
# systemctl restart can return before Python has bound 127.0.0.1.
# Do not mistake a normal startup race for a broken deployment.
if ! python3 -I "$PROBE" --mode new --wait 40; then
 diagnostics
 if restore; then
   echo "FAILED new private page readiness; previous page restored and verified."
 else
   echo "FAILED: beta rollback also needs operator attention; see diagnostics."
 fi
 exit 1
fi
echo "SUCCESS: live private beta updated. Original V2, /experimental, collector and V160 timer unchanged."
echo "Refresh http://127.0.0.1:8765/ in your existing SSH tunnel."
