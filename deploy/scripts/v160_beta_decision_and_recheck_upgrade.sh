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
PIN=0225bb0b222a7b56cae5168f3102c5b8362fc7db

systemctl is-active --quiet "$UNIT" || { echo "STOP existing private beta inactive"; exit 1; }
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
trap 'rm -f "$NEW" "$NEW_HELPER" "$OLD" "$OLD_HELPER"' EXIT

git show "$PIN:deploy/scripts/v160_private_beta_board.py" > "$NEW"
git show "$PIN:deploy/scripts/v160_single_item_recheck.py" > "$NEW_HELPER"
python3 -m py_compile "$NEW" "$NEW_HELPER"
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

restore() {
 echo "Restoring previous beta viewer only."
 install -m 0700 "$OLD" "$CODE"
 if [[ "$HAS_OLD_HELPER" == 1 ]]; then
   install -m 0700 "$OLD_HELPER" "$HELPER"
 fi
 sudo systemctl restart "$UNIT" || true
}

# Replace only the dedicated private viewer executable/helper.
install -m 0700 "$NEW_HELPER" "$HELPER"
install -m 0700 "$NEW" "$CODE"
if ! sudo systemctl restart "$UNIT"; then
 restore
 exit 1
fi

echo "===== NEW PRIVATE RESEARCH PAGE AND API SELF-CHECK ====="
if ! python3 - <<'PY'
import json,urllib.request
base="http://127.0.0.1:8765"
with urllib.request.urlopen(base,timeout=4) as r:
    content=r.read(180000).decode("utf8")
    assert "Where should I fly?" in content
    assert "Recalculate this item NOW" in content
with urllib.request.urlopen(base+"/api/live",timeout=4) as r:
    data=json.load(r)
    assert len(data["items"])==24 and data["healthy"]
    assert "signal" in data["items"][0]["models"]["independent"]
print("PASS: 24-item prioritized page + current one-item UI")
PY
then
 restore
 echo "FAILED new private page smoke; old private page restored."
 exit 1
fi
echo "SUCCESS: live private beta updated. Original V2, /experimental, collector and V160 timer unchanged."
echo "Refresh http://127.0.0.1:8765/ in your existing SSH tunnel."
