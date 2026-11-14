"""Guarded deployment of a read-only seven-pick Beanstalk JSON API.

Only deploy web/beanstalk_hot_list.py and insert ONE exact handler into the
existing live web/first_release_bridge.py middleware. All other customized VM
bridge source is preserved verbatim. No research, collector, DB or Beanstalk
changes. Preflight by default; --apply creates a backup and can auto-rollback.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import time
import urllib.request
import zipfile

ROOT = Path("/opt/torn-fren")
BRIDGE = ROOT/"web/first_release_bridge.py"
MODULE = ROOT/"web/beanstalk_hot_list.py"
BACKUPS = Path("/var/backups/torn-fren-ops")
SERVICE = "torn-fren-web.service"
BASE_URL = "http://127.0.0.1:8000"
PUBLIC_PATH = "/api/beanstalk-hot-list"
PACKAGE = {"web/beanstalk_hot_list.py", "deploy/scripts/publish_beanstalk_hot_list.py"}
ANCHOR = '            if path=="/api/first-release/history-summary":'
INSERT = '''            if path=="/api/beanstalk-hot-list":
                # Read-only Beanstalk drawer feed. No background prediction or mutation.
                headers={"Cache-Control":"public, max-age=15",
                         "Access-Control-Allow-Origin":"*"}
                try:
                    from web.beanstalk_hot_list import public_hot_list
                    payload=await run_in_threadpool(public_hot_list)
                    return JSONResponse(payload,
                        status_code=200 if payload["status"]=="OK" else 503,
                        headers=headers)
                except (OSError,ValueError,KeyError,TypeError,RuntimeError):
                    return JSONResponse(
                        {"schema":"torn-fren-beanstalk-hot-list-v1",
                         "status":"UNAVAILABLE","picks":[]},
                        status_code=503,headers=headers)
'''


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load_package(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        members=[m for m in z.infolist() if not m.is_dir()]
        if (len(members)!=len(PACKAGE)
            or {m.filename for m in members}!=PACKAGE
            or sum(m.file_size for m in members)>500_000):
            raise RuntimeError("Unexpected or oversized reviewed Beanstalk API package")
        module=z.read("web/beanstalk_hot_list.py")
        installer=z.read("deploy/scripts/publish_beanstalk_hot_list.py")
    if b"torn-fren-beanstalk-hot-list-v1" not in module or b"def build_hot_list(" not in module:
        raise RuntimeError("Missing reviewed read-only seven-pick module")
    ast.parse(module.decode("utf-8"), filename=str(MODULE))
    if b"def patch_bridge(" not in installer:
        raise RuntimeError("Missing installer contract")
    return module


def _middleware_guard(source):
    tree=ast.parse(source,filename=str(BRIDGE))
    install=[fn for fn in tree.body
             if isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef))
             and fn.name=="install_first_release"]
    if len(install)!=1:
        raise RuntimeError("Live install_first_release not uniquely present")
    middleware=[node for node in ast.walk(install[0])
                if isinstance(node,ast.ClassDef) and node.name=="BetaMiddleware"]
    if len(middleware)!=1:
        raise RuntimeError("Live BetaMiddleware not uniquely present")
    dispatch=[node for node in middleware[0].body
              if isinstance(node,ast.AsyncFunctionDef) and node.name=="dispatch"]
    if len(dispatch)!=1:
        raise RuntimeError("Live asynchronous dispatch handler not uniquely present")
    segment=ast.get_source_segment(source,dispatch[0])
    if not segment or ANCHOR not in segment or source.count(ANCHOR)!=1:
        raise RuntimeError("Approved history-summary route anchor moved or duplicated")
    if 'app.add_middleware(BetaMiddleware)' not in ast.get_source_segment(source,install[0]):
        raise RuntimeError("Live middleware install hook changed")
    if 'run_in_threadpool' not in source or 'JSONResponse' not in source:
        raise RuntimeError("Required existing middleware imports unavailable")


def patch_bridge(source):
    _middleware_guard(source)
    installed=(INSERT,INSERT.replace("\n","\r\n"))
    if any(block in source for block in installed):
        if sum(source.count(block) for block in installed)!=1:
            raise RuntimeError("Duplicate seven-pick route installed")
        return source
    if PUBLIC_PATH in source:
        raise RuntimeError("Unrecognized existing Beanstalk Hot List route")
    sep="\r\n" if "\r\n" in source else "\n"
    injection=INSERT.replace("\n",sep)
    after=source.replace(ANCHOR,injection+ANCHOR,1)
    ast.parse(after,filename=str(BRIDGE))
    if after.replace(injection+ANCHOR,ANCHOR,1)!=source:
        raise RuntimeError("Unrelated VM bridge code would change")
    return after


def regular(path,exist=True):
    if path.is_symlink() or (exist and not path.is_file()) or (path.exists() and not path.is_file()):
        raise RuntimeError("Unexpected or missing regular file: "+str(path))


def atomically(path,data):
    prior=path.stat() if path.exists() else path.parent.stat()
    fd,temp=tempfile.mkstemp(dir=path.parent,prefix=".beanstalk-hot-list-")
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp,stat.S_IMODE(prior.st_mode) if path.exists() else 0o644)
        os.chown(temp,prior.st_uid,prior.st_gid)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def request(path):
    req=urllib.request.Request(BASE_URL+path,headers={"User-Agent":"Torn-FREN-BeAnstalk-ReadOnly-Preflight/1"})
    with urllib.request.urlopen(req,timeout=14) as res:
        if res.status!=200:
            raise RuntimeError("Unexpected site response: "+path)
        raw=res.read(2*1024*1024+1)
        if len(raw)>2*1024*1024:
            raise RuntimeError("Oversized response: "+path)
        return raw


def public_preflight():
    if b"hotlist.js" not in request("/experimental"):
        raise RuntimeError("Hot List must be served at /experimental")
    if b"beta.js" not in request("/travel-decisions"):
        raise RuntimeError("Travel Decisions must remain intact")
    if b"beta.js" not in request("/"):
        raise RuntimeError("Original stock graph must remain intact")
    catalog=json.loads(request("/api/catalog"))
    board=json.loads(request("/api/first-release"))
    if not isinstance(catalog.get("countries"),list) or not catalog["countries"]:
        raise RuntimeError("Public live price catalog is unavailable")
    if not isinstance(board.get("rows"),list) or not board["rows"]:
        raise RuntimeError("Published departure feed is unavailable")
    return {"catalog_countries":len(catalog["countries"]),
            "forecast_rows":len(board["rows"]),
            "model_sha":board.get("model_sha")}


def restart():
    subprocess.run(["systemctl","restart",SERVICE],check=True,timeout=40)
    for _ in range(18):
        try:
            if subprocess.run(["systemctl","is-active","--quiet",SERVICE]).returncode==0:
                request("/api/first-release")
                return
        except (OSError,ValueError):
            pass
        time.sleep(2)
    raise RuntimeError("Web service did not recover after restart")


def verify():
    before=public_preflight()
    raw=request(PUBLIC_PATH)
    body=json.loads(raw)
    if (body.get("schema")!="torn-fren-beanstalk-hot-list-v1"
        or body.get("status")!="OK"
        or body.get("inventory_slots")!=15
        or len(body.get("picks") or [])!=7):
        raise RuntimeError("Read-only API did not return the required seven picks")
    groups={"xanax":1,"plushie":2,"flower":2,"nikeh":2}
    for item in body["picks"]:
        if item.get("category") not in groups:
            raise RuntimeError("Unknown selected item category")
        groups[item["category"]]-=1
        if not isinstance(item.get("estimated_round_trip_profit_per_hour"),int):
            raise RuntimeError("Missing hourly profit field")
        if "recommended_departure_time" not in item:
            raise RuntimeError("Missing nullable departure field")
    if any(groups.values()):
        raise RuntimeError("Category quotas not fulfilled")
    if len({i["country_code"] for i in body["picks"]})<6:
        raise RuntimeError("Destination diversity quota unmet")
    return {"public_path":PUBLIC_PATH,"generated_at":body["generated_at"],
            "picks":len(body["picks"]),**before}


def install(zip_path,apply=False):
    if os.geteuid()!=0:
        raise PermissionError("Root privileges required")
    regular(BRIDGE)
    regular(MODULE,exist=False)
    module=load_package(zip_path)
    raw_bridge=BRIDGE.read_bytes()
    existing=raw_bridge.decode("utf-8")
    updated=patch_bridge(existing).encode("utf-8")
    old_module=MODULE.read_bytes() if MODULE.exists() else None
    if old_module is not None and old_module!=module:
        raise RuntimeError("Unknown or customized Beanstalk API module; refusing overwrite")
    changes={}
    if updated!=raw_bridge:
        changes[BRIDGE]=(raw_bridge,updated)
    if old_module!=module:
        changes[MODULE]=(old_module,module)
    before=public_preflight()
    if not changes:
        return {"status":"BEANSTALK_HOT_LIST_ALREADY_INSTALLED","live":verify()}
    report={"status":"BEANSTALK_HOT_LIST_PREFLIGHT_PASSED",
            "changed_files":[str(k) for k in changes],
            "route_change":"One middleware endpoint only; unrelated VM bridge bytes preserved",
            "models_changed":False,"collector_changed":False,
            "database_changed":False,"beanstalk_changed":False,
            "before":before}
    if not apply:
        return report
    BACKUPS.mkdir(parents=True,exist_ok=True)
    stamp=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    saved=Path(tempfile.mkdtemp(prefix=stamp+"-beanstalk-hotlist-",dir=BACKUPS))
    os.chmod(saved,0o700)
    (saved/"original").mkdir(mode=0o700)
    manifest=[]
    for n,(path,(old,new)) in enumerate(changes.items()):
        backup=f"original/{n}.bin" if old is not None else None
        if backup:
            (saved/backup).write_bytes(old)
        manifest.append({"path":str(path),"backup":backup,"installed_sha256":sha(new)})
    (saved/"rollback.json").write_text(json.dumps(manifest,indent=2))
    script=r'''import hashlib,json,os,pathlib,stat,subprocess,tempfile
base=pathlib.Path(__file__).resolve().parent
items=json.loads((base/"rollback.json").read_text())
for x in items:
 p=pathlib.Path(x["path"])
 if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=x["installed_sha256"]:
  raise SystemExit("STOP: newer web file detected: "+str(p))
for x in reversed(items):
 p=pathlib.Path(x["path"])
 if x["backup"] is None:
  p.unlink()
  continue
 raw=(base/x["backup"]).read_bytes()
 st=p.stat()
 fd,tmp=tempfile.mkstemp(dir=p.parent,prefix=".beanstalk-hotlist-rollback-")
 with os.fdopen(fd,"wb") as f:f.write(raw);f.flush();os.fsync(f.fileno())
 os.chmod(tmp,stat.S_IMODE(st.st_mode));os.chown(tmp,st.st_uid,st.st_gid);os.replace(tmp,p)
subprocess.run(["systemctl","restart","torn-fren-web.service"],check=True)
print("BEANSTALK_HOT_LIST_ROLLBACK_COMPLETE")
'''
    (saved/"rollback.py").write_text(script)
    report["backup_directory"]=str(saved)
    report["rollback_command"]="sudo python3 "+str(saved/"rollback.py")
    done=[]
    try:
        # Module first, bridge second. The route never points to a missing module.
        for path in (MODULE,BRIDGE):
            if path in changes:
                atomically(path,changes[path][1])
                done.append(path)
        restart()
        report["live"]=verify()
        report["status"]="BEANSTALK_HOT_LIST_DEPLOYED"
    except Exception as error:
        report["error"]=str(error)
        failures=[]
        for path in reversed(done):
            original,installed=changes[path]
            try:
                regular(path)
                if sha(path.read_bytes())!=sha(installed):
                    raise RuntimeError("A newer web file exists")
                if original is None:
                    path.unlink()
                else:
                    atomically(path,original)
            except Exception as recovery:
                failures.append(str(path)+": "+str(recovery))
        try:
            restart()
        except Exception as recovery:
            failures.append("Web restart: "+str(recovery))
        report["rollback_errors"]=failures
        report["status"]=("BEANSTALK_HOT_LIST_ROLLED_BACK" if not failures
                          else "BEANSTALK_HOT_LIST_MANUAL_RECOVERY_REQUIRED")
    (saved/"report.json").write_text(json.dumps(report,indent=2))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package",required=True)
    p.add_argument("--apply",action="store_true")
    opts=p.parse_args()
    try:
        result=install(opts.package,apply=opts.apply)
    except Exception as error:
        result={"status":"BEANSTALK_HOT_LIST_PREFLIGHT_STOPPED","error":str(error),
                "models_changed":False,"database_changed":False}
    print(json.dumps(result,indent=2))
    return 0 if result["status"] in (
        "BEANSTALK_HOT_LIST_PREFLIGHT_PASSED",
        "BEANSTALK_HOT_LIST_DEPLOYED",
        "BEANSTALK_HOT_LIST_ALREADY_INSTALLED",
    ) else 1


if __name__=="__main__":
    raise SystemExit(main())
