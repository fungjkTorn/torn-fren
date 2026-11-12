#!/usr/bin/env bash
# V87 opt-in web-only 21+3 preview overlay with exact-source gate and rollback.
# Run as ubuntu: bash v87_web24_preview.sh status|enable|rollback [staged_module]
# Does NOT touch production collector, V75/V82/V85, or the primary history UI.
set -euo pipefail
export SYSTEMD_PAGER=cat
[[ "$(id -un)" == "ubuntu" ]] || { echo "STOP: run as ubuntu"; exit 1; }
action="${1:-status}"
STAGED="${2:-}"
ROOT=/opt/torn-fren
APP="$ROOT/web/app.py"
MODULE="$ROOT/web/v87_experimental24_overlay.py"
DROPIN=/etc/systemd/system/torn-fren-web.service.d/v87-experimental24-preview.conf
BACKUP=/home/ubuntu/torn-fren-private-models/v87_web24_rollback
BASE=http://127.0.0.1:8000
SERVICE=torn-fren-web.service
ORIGINAL="$BACKUP/app.py.before-v87"
AFTER_HASH="$BACKUP/after-v87.sha256"

probe() {
python3 - "$1" <<'PY'
import json, sys
from urllib.parse import urlencode
from urllib.request import urlopen
mode = sys.argv[1]
base = "http://127.0.0.1:8000"
def get(path):
    with urlopen(base + path, timeout=8) as r:
        if r.status != 200:
            raise AssertionError(f"HTTP {r.status}: {path}")
        return json.load(r)
j = get("/api/experimental/v41/predictions")
rows = j["latest"]
keys = [r["item_key"] for r in rows]
assert len(set(keys)) == len(keys), "duplicate item keys"
preview = ("chi:Panda Plushie", "sou:Lion Plushie", "jap:Xanax")
if mode == "21":
    assert len(rows) == 21 and not set(preview).intersection(keys), "not a clean baseline 21"
else:
    assert len(rows) == 24 and set(preview).issubset(keys), "overlay is not exactly 24"
    for row in rows:
        if row["item_key"] in preview:
            assert row["actionable"] is False
            assert row["experimental"] is True
            assert row["prediction_accuracy_verified"] is False
            assert row["status"].startswith("RESEARCH_PREVIEW_")
            assert row["quantity_threshold"] == 30
    # Confirm old 21 survive the overlay, and filtered endpoints remain correct.
    for country, item in (("jap", "Xanax"), ("chi", "Panda Plushie"),
                          ("sou", "Lion Plushie")):
        filtered = get("/api/experimental/v41/predictions?" +
                       urlencode({"country": country, "item": item}))
        assert [r["item_key"] for r in filtered["latest"]] == [f"{country}:{item}"]
    legacy = get("/api/experimental/v41/predictions?" +
                 urlencode({"country":"arg", "item":"Monkey Plushie"}))
    # Preserve the pre-existing V41 single-item response, which may be
    # a dict, a list, or a null result depending on its original semantics.
    assert isinstance(legacy, dict) and "latest" in legacy
    assert legacy.get("experimental") is True
from urllib.request import urlopen
for endpoint in ("/experimental", "/api/catalog"):
    with urlopen(base + endpoint, timeout=8) as r:
        assert r.status == 200, f"{endpoint}: {r.status}"
print(json.dumps({
    "status": "V87_WEBSITE_"+mode+"_VERIFIED",
    "rows": len(rows), "unique": len(set(keys)),
    "preview": [r["item_key"] for r in rows if r["item_key"] in preview],
    "new_statuses": {r["item_key"]: r["status"] for r in rows
                    if r["item_key"] in preview}
}, sort_keys=True))
PY
}

rollback_files() {
  [[ -f "$ORIGINAL" ]] || { echo "STOP: original web app backup absent"; return 1; }
  sudo cp -p "$ORIGINAL" "$APP"
  sudo rm -f "$MODULE" "$DROPIN"
  sudo systemctl daemon-reload
  sudo systemctl restart "$SERVICE"
  echo "V87 files reverted; waiting for original web service to return."
  local restored=0
  for attempt in $(seq 1 30); do
    if systemctl is-active --quiet "$SERVICE" &&
       curl -fsS --max-time 4 "$BASE/api/experimental/v41/predictions" >/dev/null 2>&1; then
      restored=1; break
    fi
    sleep 2
  done
  [[ "$restored" == 1 ]] || { echo "STOP: rollback service not healthy within 60s"; return 1; }
  probe 21
  echo "Original 21-item website verified after rollback."
}

if [[ "$action" == "status" ]]; then
  echo "===== V87 INSTALLATION STATUS ====="
  [[ -f "$DROPIN" ]] && echo "V87 feature drop-in exists" || echo "V87 feature drop-in absent"
  [[ -f "$MODULE" ]] && echo "V87 adapter exists" || echo "V87 adapter absent"
  systemctl show "$SERVICE" -p ActiveState -p Result -p MainPID --no-pager
  systemctl is-active --quiet "$SERVICE" || exit 1
  python3 - <<'PY'
import json
from urllib.request import urlopen
with urlopen("http://127.0.0.1:8000/api/experimental/v41/predictions",timeout=8) as r:
    d=json.load(r)
print(json.dumps({"rows":len(d.get("latest",[])),
                  "unique_keys":len(set(x.get("item_key") for x in d.get("latest",[])))},
                 sort_keys=True))
PY
  exit 0
fi

if [[ "$action" == "rollback" ]]; then
  [[ -f "$AFTER_HASH" ]] || { echo "STOP: no V87 installation hash"; exit 1; }
  CURRENT="$(sha256sum "$APP" | awk '{print $1}')"
  EXPECTED="$(cat "$AFTER_HASH")"
  [[ "$CURRENT" == "$EXPECTED" ]] || {
    echo "STOP: deployed web app changed since V87. Refusing to overwrite later changes."
    exit 1
  }
  rollback_files
  echo "===== V87 REVERTED TO ORIGINAL 21 ====="
  exit 0
fi

[[ "$action" == "enable" ]] || { echo "Usage: status|enable|rollback [staged_module]"; exit 2; }
[[ -n "$STAGED" && -f "$STAGED" && ! -L "$STAGED" ]] || {
  echo "STOP: pass an existing regular, staged V87 adapter module"; exit 1;
}
systemctl is-active --quiet "$SERVICE" || { echo "STOP: website service inactive"; exit 1; }
for timer in torn-fren-v38-private-shadow.timer torn-fren-v82-pair-forward.timer torn-fren-v85-japan-forward.timer; do
  systemctl is-active --quiet "$timer" || { echo "STOP: research timer $timer inactive"; exit 1; }
done
[[ -f "$APP" && ! -L "$APP" ]] || { echo "STOP: unexpected web app"; exit 1; }
[[ ! -e "$DROPIN" && ! -e "$MODULE" ]] || { echo "STOP: V87 already present; use status"; exit 1; }
# A failed prior V87 deployment intentionally keeps its baseline backup.
# Reuse only after byte-for-byte verification against today's deployed app.
if [[ -e "$ORIGINAL" || -L "$ORIGINAL" ]]; then
  [[ -f "$ORIGINAL" && ! -L "$ORIGINAL" ]] || {
    echo "STOP: prior backup is not a regular file"; exit 1;
  }
  sudo cmp -s "$ORIGINAL" "$APP" || {
    echo "STOP: deployed app differs from prior baseline; inspect before retry"; exit 1;
  }
  echo "Verified original 21-item app matches preserved prior backup."
elif [[ -e "$BACKUP" && ! -d "$BACKUP" ]]; then
  echo "STOP: invalid rollback directory"; exit 1
fi
echo "===== VERIFYING EXISTING 21 ====="
probe 21
echo "===== OFFLINE CHECK AGAINST LIVE FILTERED RESPONSE SHAPES ====="
python3 - "$STAGED" <<'PY'
import importlib.util
import json
import sys
import time
from urllib.parse import urlencode
from urllib.request import urlopen

spec = importlib.util.spec_from_file_location("v87_staged_preflight", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
root = "http://127.0.0.1:8000/api/experimental/v41/predictions"
def get(country=None, item=None):
    url = root if country is None else root + "?" + urlencode(
        {"country": country, "item": item})
    with urlopen(url, timeout=8) as response:
        return json.load(response)
now = int(time.time())
base = get()
combined = module.overlay_response(base, now=now)
records = combined["latest"]
assert len(records) == 24 and len({r["item_key"] for r in records}) == 24
assert records[:21] == base["latest"], "baseline 21 modified"
for country, item in (("chi", "Panda Plushie"),
                      ("sou", "Lion Plushie"), ("jap", "Xanax")):
    key = f"{country}:{item}"
    filtered_base = get(country, item)
    wrapped = module.overlay_response(filtered_base, key=key, now=now)
    assert isinstance(wrapped["latest"], list)
    assert [r["item_key"] for r in wrapped["latest"]] == [key]
    assert wrapped["latest"][0]["actionable"] is False
    assert wrapped["latest"][0]["prediction_accuracy_verified"] is False
legacy = get("arg", "Monkey Plushie")
assert module.overlay_response(legacy, key="arg:Monkey Plushie", now=now) == legacy
print(json.dumps({"offline_merged_rows":len(records), "filtered_preview_count":3,
                  "legacy_filtered_unchanged":True,
                  "new_statuses":{r["item_key"]:r["status"] for r in records[21:]}},
                 sort_keys=True))
PY
echo "===== BUILDING AND COMPILING EXACT-SOURCE PATCH ====="
mkdir -p "$BACKUP"
chmod 700 "$BACKUP"
if [[ ! -f "$ORIGINAL" ]]; then
  sudo cp -p "$APP" "$ORIGINAL"
fi
python3 - "$APP" "$BACKUP/modified_app.py" <<'PY'
import ast
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text(encoding="utf-8")
old = '''    return {"experimental": True, "prediction_accuracy_verified": False,
            "source": "PRECOMPUTED_READ_ONLY_SIDECAR", "latest": latest}'''
new = '''    response = {"experimental": True, "prediction_accuracy_verified": False,
                "source": "PRECOMPUTED_READ_ONLY_SIDECAR", "latest": latest}
    if os.environ.get("TORN_FREN_V87_EXPERIMENTAL24_PREVIEW") == "1":
        from web.v87_experimental24_overlay import overlay_response
        return overlay_response(response, key=key, now=now)
    return response'''
route = '@app.get("/api/experimental/v41/predictions")'
if source.count(route) != 1 or source.count(old) != 1 or "TORN_FREN_V87_EXPERIMENTAL24_PREVIEW" in source:
    raise SystemExit("STOP: deployed experimental source did not match guarded patch anchor")
patched = source.replace(old, new, 1)
ast.parse(patched, filename="web/app.py")
Path(sys.argv[2]).write_text(patched, encoding="utf-8")
print("Exact-route patch compiled, existing nonexperimental handlers unchanged")
PY
python3 -m py_compile "$STAGED" "$BACKUP/modified_app.py"
echo "===== APPLYING REVERSIBLE WEB-ONLY CHANGE ====="
RESTORE=0
recover() {
  if [[ "$RESTORE" == 1 ]]; then
    echo "WEB VERIFICATION FAILED: restoring original endpoint."
    rollback_files || echo "STOP: automatic rollback verification failed; investigate web health"
  fi
}
trap recover EXIT
RESTORE=1
sudo install -m 0644 "$STAGED" "$MODULE"
sudo cp "$BACKUP/modified_app.py" "$APP"
sha256sum "$APP" | awk '{print $1}' > "$AFTER_HASH"
printf '[Service]\nEnvironment=TORN_FREN_V87_EXPERIMENTAL24_PREVIEW=1\n' |
  sudo tee "$DROPIN" >/dev/null
sudo systemctl daemon-reload
sudo systemctl restart "$SERVICE"
echo "===== CHECKING 24-ITEM API AND ORIGINAL ROUTES ====="
UP=0
for i in $(seq 1 18); do
  if systemctl is-active --quiet "$SERVICE" &&
     curl -fsS --max-time 3 "$BASE/api/experimental/v41/predictions" >/dev/null 2>&1; then
     UP=1; break
  fi
  sleep 2
done
[[ "$UP" == 1 ]] || { echo "STOP: website failed restart/health"; exit 1; }
probe 24
RESTORE=0
trap - EXIT
echo "===== V87 EXPERIMENTAL 24 ENABLED; ORIGINAL BACKUP RETAINED ====="
echo "Rollback: bash deploy/scripts/v87_web24_preview.sh rollback (from this same staged script)"
