"""Guarded UI-only Hot List upgrade (Nikeh profitability and 15-slot default).

No route, collector, forecast, service or database modifications.
Requires /experimental to serve the existing Hot List.
An unknown installed web asset stops the rollout before any writes.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import urllib.request
import zipfile

ROOT=Path("/opt/torn-fren")
ASSETS=ROOT/"web/first_release_assets"
BACKUPS=Path("/var/backups/torn-fren-ops")
SITE="http://127.0.0.1:8000"
NAMES=("hotlist.html","hotlist.js","hotlist-core.js","hotlist.css")
PACKAGE_NAMES={*(f"web/first_release_assets/{n}" for n in NAMES),
               "deploy/scripts/publish_hotlist_profitability.py"}
# Approved PR #25 / V2 web UI assets. Do not accept arbitrary VM changes.
APPROVED_PRIOR_BLOBS={
 "hotlist.html":("396c288f79048ce196c10cda0f5cf4ea09fa3e1c",),
 "hotlist.js":(
  "27032e5890cacec3c5e87705db50b9cb2a103ca7",  # PR #26 published Nikeh UI
  "a1b43cfe7fcf01fc8422f259f33a2c438e5e7ce1",  # PR #25
  "8be2046d2bb096f15b0a7a842babf396c1f6adae",  # PR #24 route release
 ),
 "hotlist-core.js":(
  "b6b02eb33eaf96838caa63b35e0781bd8c11bf60",  # PR #26 published Nikeh core
  "320678d633a8813460fc9249de7068f4f0375186",  # PR #25 threshold
  "629658ffa1a66eccf1e9f2ac3dd6f316dc3edbfa",  # PR #24 original core
 ),
 "hotlist.css":("d06b9cd60ea5881f380a5127676c73f2f46a1264",),
}

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def blob(raw):
    return hashlib.sha1(f"blob {len(raw)}".encode()+bytes([0])+raw).hexdigest()

def signed_prior(raw,name):
    if raw is None:
        return False
    approved=APPROVED_PRIOR_BLOBS[name]
    if blob(raw) in approved:
        return True
    converted=raw.replace(b"\r\n",b"\n")
    return b"\r" not in converted and blob(converted) in approved

def request(path):
    with urllib.request.urlopen(SITE+path,timeout=15) as response:
        if response.status!=200:
            raise RuntimeError(f"HTTP {response.status}: {path}")
        body=response.read(2*1024*1024+1)
        if len(body)>2*1024*1024:
            raise RuntimeError("Public response too large: "+path)
        return body

def feed():
    publication=json.loads(request("/api/first-release"))
    catalog=json.loads(request("/api/catalog"))
    if not isinstance(publication.get("rows"),list) or not publication["rows"]:
        raise RuntimeError("First-release feed unavailable")
    if not isinstance(catalog.get("countries"),list) or not catalog["countries"]:
        raise RuntimeError("Torn price catalog unavailable")
    return {"model_sha":publication.get("model_sha"),
            "forecast_rows":len(publication["rows"])}

def routes():
    root=request("/")
    page=request("/experimental")
    travel=request("/travel-decisions")
    graph=request("/?country=mex&item=Dahlia")
    if b"hotlist.js" not in page or b"beta.js" not in root or b"beta.js" not in travel or b"beta.js" not in graph:
        raise RuntimeError("Expected V2 routes not installed. Migrate /experimental first.")
    return True

def package(path):
    with zipfile.ZipFile(path) as z:
        entries=[i for i in z.infolist() if not i.is_dir()]
        if ({i.filename for i in entries}!=PACKAGE_NAMES or len(entries)!=len(PACKAGE_NAMES)
            or sum(i.file_size for i in entries)>1024*1024):
            raise RuntimeError("Unexpected or oversized UI-only update package")
        result={ASSETS/name:z.read("web/first_release_assets/"+name) for name in NAMES}
    js=result[ASSETS/"hotlist.js"]
    core=result[ASSETS/"hotlist-core.js"]
    html=result[ASSETS/"hotlist.html"]
    if (b"NIKEH_PAYOUTS" not in core or b"MIN_HOT_MARKET_VALUE=15000" not in core
        or b"priceError?null:core.saleQuote" not in js or b'value="15"' not in html
        or b'href="/experimental"' not in html):
        raise RuntimeError("Package does not contain reviewed Nikeh and Hot List policy")
    return result

def normal(path):
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("Expected regular, non-symlink file: "+str(path))

def write_atomic(path,data):
    st=path.stat()
    fd,tmp=tempfile.mkstemp(prefix=".hotlist-nikeh-",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as out:
            out.write(data);out.flush();os.fsync(out.fileno())
        os.chmod(tmp,stat.S_IMODE(st.st_mode))
        os.chown(tmp,st.st_uid,st.st_gid)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def verify(before,desired):
    routes()
    for name in NAMES:
        url="/experimental" if name=="hotlist.html" else "/first-release-assets/"+name
        if sha(request(url))!=sha(desired[ASSETS/name]):
            raise RuntimeError("Web asset not serving reviewed bytes: "+name)
    after=feed()
    if before!=after:
        raise RuntimeError("Forecast model or catalog shape changed unexpectedly")
    return {"status":"VERIFIED","experimental":"HOT_LIST_NIKEH",
            "all_items":"UNRESTRICTED","models_untouched":True,
            "forecast_sha":after["model_sha"],"forecast_rows":after["forecast_rows"]}

def rollback_script():
    return '''import hashlib,json,os,pathlib,stat,tempfile
base=pathlib.Path(__file__).resolve().parent
items=json.loads((base/"rollback.json").read_text())
for item in items:
 p=pathlib.Path(item["path"])
 if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=item["installed_sha256"]:
  raise SystemExit("STOP: changed live UI file "+str(p))
for item in reversed(items):
 p=pathlib.Path(item["path"]);raw=(base/item["saved"]).read_bytes();st=p.stat()
 fd,tmp=tempfile.mkstemp(dir=p.parent,prefix=".hotlist-nikeh-rollback-")
 with os.fdopen(fd,"wb") as out:out.write(raw);out.flush();os.fsync(out.fileno())
 os.chmod(tmp,stat.S_IMODE(st.st_mode));os.chown(tmp,st.st_uid,st.st_gid);os.replace(tmp,p)
print("HOTLIST_NIKEH_UI_ROLLED_BACK")
'''

def install(archive,apply):
    if os.geteuid()!=0:
        raise RuntimeError("Must run as root for protected website updates")
    if not ASSETS.is_dir() or ASSETS.is_symlink():
        raise RuntimeError("Unexpected web asset directory")
    desired=package(archive)
    for path in desired:
        normal(path)
    routes()
    before=feed()
    prior={path:path.read_bytes() for path in desired}
    for path,raw in prior.items():
        if raw==desired[path]:
            continue
        if not signed_prior(raw,path.name):
            raise RuntimeError("UI asset differs from approved V2 release: "+path.name+
                               " observed_blob="+blob(raw)+" expected_blobs="+",".join(APPROVED_PRIOR_BLOBS[path.name]))
    changed=[path for path in desired if desired[path]!=prior[path]]
    if not changed:
        return {"status":"HOTLIST_NIKEH_ALREADY_INSTALLED",
                "live":verify(before,desired)}
    report={"status":"HOTLIST_NIKEH_PREFLIGHT_PASSED",
            "changed_files":[str(p) for p in changed],
            "forecast_sha":before["model_sha"],"forecast_rows":before["forecast_rows"],
            "routes_changed":False,"database_changed":False,"collectors_changed":False}
    if not apply:
        return report
    BACKUPS.mkdir(parents=True,exist_ok=True)
    dirname=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-hotlist-nikeh-"
    backup=Path(tempfile.mkdtemp(prefix=dirname,dir=BACKUPS))
    os.chmod(backup,0o700)
    (backup/"original").mkdir(mode=0o700)
    manifest=[]
    for i,path in enumerate(changed):
        saved=f"original/{i}.bin"
        (backup/saved).write_bytes(prior[path])
        manifest.append({"path":str(path),"saved":saved,"installed_sha256":sha(desired[path])})
    (backup/"rollback.json").write_text(json.dumps(manifest,indent=2))
    (backup/"rollback.py").write_text(rollback_script())
    report["backup_dir"]=str(backup)
    report["rollback_command"]="sudo python3 "+str(backup/"rollback.py")
    written=[]
    try:
        for path in changed:
            write_atomic(path,desired[path])
            written.append(path)
        report["live"]=verify(before,desired)
        report["status"]="HOTLIST_NIKEH_DEPLOYED"
    except Exception as error:
        report["error"]=str(error)
        failed=[]
        for path in reversed(written):
            try:
                normal(path)
                if sha(path.read_bytes())!=sha(desired[path]):
                    raise RuntimeError("Later modification detected")
                write_atomic(path,prior[path])
            except Exception as revert:
                failed.append(str(path)+": "+str(revert))
        report["status"]="HOTLIST_NIKEH_ROLLED_BACK" if not failed else "HOTLIST_NIKEH_MANUAL_RECOVERY_REQUIRED"
        report["rollback_errors"]=failed
    (backup/"report.json").write_text(json.dumps(report,indent=2))
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package",required=True)
    parser.add_argument("--apply",action="store_true")
    opts=parser.parse_args()
    try:
        result=install(opts.package,opts.apply)
    except Exception as error:
        result={"status":"HOTLIST_NIKEH_PREFLIGHT_STOPPED","error":str(error),
                "routes_changed":False,"database_changed":False}
    print(json.dumps(result,indent=2))
    return 0 if result["status"] in ("HOTLIST_NIKEH_PREFLIGHT_PASSED",
                                   "HOTLIST_NIKEH_DEPLOYED",
                                   "HOTLIST_NIKEH_ALREADY_INSTALLED") else 1

if __name__=="__main__":
    raise SystemExit(main())
