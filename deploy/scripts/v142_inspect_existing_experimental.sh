#!/usr/bin/env bash
# Read-only deployed two-view verification. Does NOT deploy, install or restart.
set -euo pipefail
[[ "$(id -un)" == "ubuntu" ]] || { echo "STOP: run as ubuntu"; exit 1; }
python3 - <<'PY'
import hashlib
import json
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

BASE = "http://127.0.0.1:8000"
LIMIT = 2_000_000
BASE24 = {
"arg:Ceibo Flower","arg:Monkey Plushie",
"can:Crocus","can:Wolverine Plushie","can:Xanax",
"cay:Banana Orchid","cay:Stingray Plushie",
"chi:Panda Plushie","chi:Peony",
"haw:Orchid","jap:Cherry Blossom","jap:Xanax",
"mex:Dahlia","mex:Jaguar Plushie",
"sou:African Violet","sou:Lion Plushie",
"swi:Chamois Plushie","swi:Edelweiss",
"uae:Camel Plushie","uae:Tribulus Omanense",
"uni:Heather","uni:Nessie Plushie","uni:Red Fox Plushie","uni:Xanax",
}
assert len(BASE24) == 24

def fetch(path):
    try:
        with urlopen(BASE+path,timeout=8) as response:
            content=response.read(LIMIT+1)
            if len(content)>LIMIT:
                return {"http":response.status,"error":"RESPONSE_TOO_LARGE"},None
            return {"http":response.status,"bytes":len(content)},content
    except HTTPError as error:
        return {"http":error.code,"error":"HTTP_ERROR"},None
    except (URLError,TimeoutError,OSError):
        return {"http":None,"error":"UNREACHABLE"},None

status={}
for route in ("/","/experimental","/api/experimental/v41/predictions"):
    info,content=fetch(route)
    status[route]=info
    if route=="/experimental" and content is not None:
        raw=content.decode("utf-8","replace").lower()
        status[route]["html_sha256"]=hashlib.sha256(content).hexdigest()
        status[route]["mentions_departure"]=("depart" in raw)
        status[route]["mentions_model"]=("model" in raw)
        status[route]["mentions_stale_or_refresh"]=(
            "stale" in raw or "refresh" in raw or "valid_until" in raw)
    if route=="/api/experimental/v41/predictions" and content is not None:
        try:
            payload=json.loads(content)
        except (ValueError,UnicodeError):
            status[route]["error"]="INVALID_JSON"
            continue
        rows=payload.get("latest") if isinstance(payload,dict) else (
            payload if isinstance(payload,list) else None)
        if not isinstance(rows,list):
            status[route]["error"]="UNKNOWN_RESPONSE_SHAPE"
            continue
        keys=[r.get("item_key") for r in rows if isinstance(r,dict)]
        recognized={k for k in keys if isinstance(k,str)}
        status[route]["record_count"]=len(rows)
        status[route]["unique_item_count"]=len(recognized)
        status[route]["expected24_present_count"]=len(recognized & BASE24)
        status[route]["missing_24"]=sorted(BASE24-recognized)
        status[route]["unexpected_item_count"]=len(recognized-BASE24)
        status[route]["duplicate_item_keys"]=sorted(
            k for k,n in Counter(keys).items() if isinstance(k,str) and n>1)
        status[route]["fields_in_first_record"]=(
            sorted(rows[0].keys()) if rows and isinstance(rows[0],dict) else [])
        status[route]["per_item"]=[
            {"item_key":r.get("item_key"),
             "model_family":r.get("model_family"),
             "model_config":r.get("model_config"),
             "status":r.get("status"),
             "computed_at":r.get("computed_at"),
             "valid_until":r.get("valid_until"),
             "actionable":r.get("actionable"),
             "departure_exists":isinstance(r.get("departure"),int),
             "arrival_exists":isinstance(r.get("arrival"),int)}
            for r in rows if isinstance(r,dict) and r.get("item_key") in BASE24
        ]
app=Path("/opt/torn-fren/web/app.py")
status["deployed_app"]={
    "exists":app.is_file() and not app.is_symlink(),
    "sha256":hashlib.sha256(app.read_bytes()).hexdigest()
       if app.is_file() and not app.is_symlink() else None,
}
static=Path("/opt/torn-fren/web/static")
status["deployed_html_filenames"]=sorted(
    p.name for p in static.glob("*.html") if p.is_file() and not p.is_symlink()
) if static.is_dir() and not static.is_symlink() else []
overlay=Path("/etc/systemd/system/torn-fren-web.service.d/v87-experimental24-preview.conf")
status["v87_dropin_exists"]=overlay.is_file() and not overlay.is_symlink()
print("===== V142 READ-ONLY EXISTING PAGE BETA INSPECTION =====")
print(json.dumps(status,indent=2,sort_keys=True))
print("No environment secrets, API keys, HTML source, or database records printed.")
PY
