"""Guarded v1 Hot List routing correction: / -> /experimental.

Only the web middleware bridge and the Hot List HTML/JS/reference JSON are
replaced. It neither changes prediction sources nor the stock collector.
Requires the exact prior approved public Hot List v1 files installed.
No mutation without --apply. Reports JSON and preserves rollback files.
"""
import argparse
import ast
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time
import urllib.request
import zipfile

ROOT=Path("/opt/torn-fren")
BRIDGE=ROOT/"web/first_release_bridge.py"
ASSETS=ROOT/"web/first_release_assets"
BACKUPS=Path("/var/backups/torn-fren-ops")
SERVICE="torn-fren-web.service"
BASE="http://127.0.0.1:8000"
NAMES=("hotlist.html","hotlist.js","abroad-roster.json")
PACKAGE_FILES={*(f"web/first_release_assets/{name}" for name in NAMES),"deploy/scripts/relocate_hotlist.py"}
V1_BLOBS={
 str(BRIDGE):"a4f0d6e4d89b31328a9aa61d4903ffe5f006923d",
 str(ASSETS/"hotlist.html"):"24aad1af4e50bbfe3c436220e5b033501fa2a188",
 str(ASSETS/"hotlist.js"):"20bd140f63e06609f02776b6e92b73dab701a9af",
 str(ASSETS/"hotlist-core.js"):"629658ffa1a66eccf1e9f2ac3dd6f316dc3edbfa",
 str(ASSETS/"hotlist.css"):"d06b9cd60ea5881f380a5127676c73f2f46a1264",
}
ASSET_V1='if name in ("beta.js","beta.css","hotlist.js","hotlist-core.js","hotlist.css"):'
ASSET_V2='if name in ("beta.js","beta.css","hotlist.js","hotlist-core.js","hotlist.css","abroad-roster.json"):'
ROUTE_V1='''            if path=="/" and not (request.query_params.get("country") or request.query_params.get("item")):
                return FileResponse(ASSETS/"hotlist.html",media_type="text/html",headers={"Cache-Control":"no-store"})
            if path in ("/experimental","/travel-decisions"):
                return FileResponse(ASSETS/"board.html",media_type="text/html",headers={"Cache-Control":"no-store"})'''
ROUTE_V2='''            if path=="/experimental":
                return FileResponse(ASSETS/"hotlist.html",media_type="text/html",headers={"Cache-Control":"no-store"})
            if path=="/travel-decisions":
                return FileResponse(ASSETS/"board.html",media_type="text/html",headers={"Cache-Control":"no-store"})'''


def sha(raw): return hashlib.sha256(raw).hexdigest()
def blob(raw): return hashlib.sha1(f"blob {len(raw)}".encode()+bytes([0])+raw).hexdigest()

def approved_v1(raw, path):
    """Allow exact V1 Git bytes or their CRLF-only conversion; reject all other drift."""
    pinned = V1_BLOBS.get(str(path))
    if not pinned or raw is None:
        return False
    if blob(raw) == pinned:
        return True
    if b"\r\n" not in raw:
        return False
    normalized = raw.replace(b"\r\n", b"\n")
    return b"\r" not in normalized and blob(normalized) == pinned

def regular(path,required=True):
    if path.is_symlink() or (required and not path.is_file()) or (path.exists() and not path.is_file()):
        raise RuntimeError("Unexpected or missing regular file: "+str(path))

def get(path):
    with urllib.request.urlopen(BASE+path,timeout=12) as response:
        if response.status!=200: raise RuntimeError(f"HTTP {response.status}: {path}")
        return response.read(8*1024*1024)

def feed():
    info=json.loads(get("/api/first-release"))
    if not isinstance(info.get("rows"),list) or not info["rows"] or not info.get("model_sha"):
        raise RuntimeError("No usable first-release publisher feed")
    c=json.loads(get("/api/catalog"))
    if not isinstance(c.get("countries"),list) or not c["countries"]:
        raise RuntimeError("Catalog endpoint unavailable")
    return {"model_sha":info["model_sha"],"forecast_count":len(info["rows"])}

def mode():
    home,experimental,travel,graph=(get("/") ,get("/experimental"),
        get("/travel-decisions"),get("/?country=mex&item=Dahlia"))
    if b"beta.js" not in travel or b"beta.js" not in graph:
        raise RuntimeError("Travel decisions or stock graph is not preserved")
    if b"hotlist.js" in home and b"beta.js" in experimental:
        return "v1"
    if b"beta.js" in home and b"hotlist.js" in experimental:
        return "v2"
    raise RuntimeError("Unexpected website route layout; refusing change")

def _route_ast_guard(source, asset_rule, route_rule):
    """Verify both expected routing snippets occur once inside the live middleware."""
    tree=ast.parse(source,filename=str(BRIDGE))
    functions=[node for node in tree.body
               if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))
               and node.name=="install_first_release"]
    if len(functions)!=1:
        raise RuntimeError("Cannot find unique existing install_first_release function")
    classes=[node for node in ast.walk(functions[0])
             if isinstance(node,ast.ClassDef) and node.name=="BetaMiddleware"]
    if len(classes)!=1:
        raise RuntimeError("Cannot find unique existing web middleware class")
    dispatch=[node for node in classes[0].body
              if isinstance(node,ast.AsyncFunctionDef) and node.name=="dispatch"]
    if len(dispatch)!=1:
        raise RuntimeError("Cannot find unique existing web dispatch method")
    section=ast.get_source_segment(source,dispatch[0])
    if not section or asset_rule not in section or route_rule not in section:
        raise RuntimeError("Expected Hot List routes are outside the live middleware")
    if source.count(asset_rule)!=1 or source.count(route_rule)!=1:
        raise RuntimeError("Ambiguous Hot List route blocks")
    if "app.add_middleware(BetaMiddleware)" not in ast.get_source_segment(source,functions[0]):
        raise RuntimeError("Live middleware installation hook differs")


def patch_bridge(source):
    """Only replace the two pinned route snippets, preserving ALL other VM source."""
    if ASSET_V1 in source and ROUTE_V1 in source and ASSET_V2 not in source and ROUTE_V2 not in source:
        _route_ast_guard(source,ASSET_V1,ROUTE_V1)
        updated=source.replace(ASSET_V1,ASSET_V2,1).replace(ROUTE_V1,ROUTE_V2,1)
        _route_ast_guard(updated,ASSET_V2,ROUTE_V2)
        # Reversing exactly these two replacements must recover the byte-for-byte
        # original, including unrelated VM customizations and line-ending style.
        if updated.replace(ASSET_V2,ASSET_V1,1).replace(ROUTE_V2,ROUTE_V1,1)!=source:
            raise RuntimeError("Route-only replacement failed content preservation")
        return updated
    if ASSET_V2 in source and ROUTE_V2 in source and ASSET_V1 not in source and ROUTE_V1 not in source:
        _route_ast_guard(source,ASSET_V2,ROUTE_V2)
        return source
    raise RuntimeError("Existing web routing does not match approved V1/V2 anchors")

def read_package(archive):
    with zipfile.ZipFile(archive) as z:
        members=[x for x in z.infolist() if not x.is_dir()]
        if {x.filename for x in members}!=PACKAGE_FILES or len(members)!=len(PACKAGE_FILES) or sum(x.file_size for x in members)>1024*1024:
            raise RuntimeError("Invalid or oversized reviewed web-only archive")
        data={ASSETS/name:z.read("web/first_release_assets/"+name) for name in NAMES}
    html=data[ASSETS/"hotlist.html"]
    js=data[ASSETS/"hotlist.js"]
    if b'href="/experimental"' not in html or b'Hot List' not in html or b'abroad-roster.json' not in js:
        raise RuntimeError("Updated Hot List UI is incomplete")
    refs=json.loads(data[ASSETS/"abroad-roster.json"])
    entries=refs.get("items")
    if refs.get("schema")!="torn-fren-foreign-catalog-reference-v1" or not isinstance(entries,list) or len(entries)!=236 or len(set(entries))!=236:
        raise RuntimeError("Reference roster failed 236-key validation")
    for key in ("haw:Orchid","jap:Xanax","sou:Xanax","uni:Xanax"):
        if key not in entries: raise RuntimeError("Missing reference: "+key)
    return data

def atomic(path,raw):
    existed=path.exists()
    st=path.stat() if existed else path.parent.stat()
    fd,tmp=tempfile.mkstemp(prefix=".hotlist-route-",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(raw);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,stat.S_IMODE(st.st_mode) if existed else 0o644)
        os.chown(tmp,st.st_uid,st.st_gid)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def restart():
    subprocess.run(("systemctl","restart",SERVICE),check=True,timeout=35)
    for i in range(20):
        try:
            if subprocess.run(("systemctl","is-active","--quiet",SERVICE),check=False).returncode==0:
                get("/api/first-release")
                return
        except (OSError,RuntimeError):
            pass
        time.sleep(2)
    raise RuntimeError("Web server did not recover after restart")

def verify(expected,files):
    if mode()!="v2": raise RuntimeError("Updated route is not serving Hot List on /experimental")
    for name in NAMES:
        if name!="hotlist.html" and sha(get("/first-release-assets/"+name))!=sha(files[ASSETS/name]):
            raise RuntimeError("Served asset differs: "+name)
    if sha(get("/experimental"))!=sha(files[ASSETS/"hotlist.html"]):
        raise RuntimeError("Wrong experimental HTML")
    newer=feed()
    if newer!=expected:
        raise RuntimeError("Publisher identity/count changed during web-only rollout")
    return {"root":"LEGACY_GRAPH","experimental":"HOT_LIST","travel_decisions":"PRESERVED",
            "stock_graph":"PRESERVED","roster_reference":236,"model_sha":newer["model_sha"],
            "public_forecast_items":newer["forecast_count"]}

def rollout(package,apply=False):
    if os.geteuid()!=0: raise PermissionError("Root required")
    if ASSETS.is_symlink() or not ASSETS.is_dir(): raise RuntimeError("Invalid installed asset directory")
    for path in [BRIDGE,ASSETS/"hotlist-core.js",ASSETS/"hotlist.css",*map(lambda x:ASSETS/x,NAMES)]:
        regular(path,required=path.name!="abroad-roster.json")
    for path in (ASSETS/"hotlist.css",ASSETS/"hotlist-core.js"):
        if not approved_v1(path.read_bytes(),path):
            raise RuntimeError(
                "Installed shared asset differs beyond CRLF normalization; refusing overwrite: "
                + path.name + " observed_blob=" + blob(path.read_bytes())
                + " expected_v1_blob=" + V1_BLOBS[str(path)]
            )
    files=read_package(package)
    prior={BRIDGE:BRIDGE.read_bytes()}
    desired={BRIDGE:patch_bridge(prior[BRIDGE].decode("utf-8")).encode("utf-8"),**files}
    for path in files:
        prior[path]=path.read_bytes() if path.exists() else None
    for path,raw in prior.items():
        if raw is None:
            if path.name!="abroad-roster.json":raise RuntimeError("Expected preexisting V1 asset missing")
        elif path==BRIDGE and raw!=desired[path]:
            # This VM has its own evolving web bridge. The two exact V1 routing
            # anchors were validated in BetaMiddleware.dispatch above. Only those
            # anchors are replaced; all other installed source is preserved.
            if patch_bridge(raw.decode("utf-8")).encode("utf-8")!=desired[path]:
                raise RuntimeError("Unexpected mutation outside the two route snippets")
        elif raw!=desired[path] and not approved_v1(raw,path):
            raise RuntimeError(
                "Changed or unknown installed web file beyond CRLF normalization: "
                + str(path) + " observed_blob=" + blob(raw)
                + " expected_v1_blob=" + str(V1_BLOBS.get(str(path)))
            )
    before=feed()
    observed_mode=mode()
    changed=[path for path in desired if prior[path]!=desired[path]]
    if not changed:
        return {"status":"HOTLIST_ROUTE_ALREADY_INSTALLED","live":verify(before,files)}
    if observed_mode!="v1":
        raise RuntimeError("Expected V1 route before change; live routing diverged")
    report={"status":"HOTLIST_ROUTE_PREFLIGHT_PASSED","prior":observed_mode,
            "changed_files":[str(p) for p in changed],
            "model_sha":before["model_sha"],"forecast_count":before["forecast_count"],
            "bridge_source_sha256_before":sha(prior[BRIDGE]),
            "bridge_edit":"TWO_VERIFIED_MIDDLEWARE_ROUTING_SNIPPETS_ONLY",
            "models_changed":False,"collector_changed":False,"databases_changed":False}
    if not apply: return report
    BACKUPS.mkdir(mode=0o700,parents=True,exist_ok=True)
    backup=Path(tempfile.mkdtemp(prefix=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-hotlist-route-",dir=BACKUPS))
    os.chmod(backup,0o700)
    (backup/"original").mkdir(mode=0o700)
    details=[]
    for i,p in enumerate(changed):
        old=prior[p]
        saved=f"original/{i}.bin" if old is not None else None
        if saved: (backup/saved).write_bytes(old)
        details.append({"path":str(p),"saved":saved,"installed_sha256":sha(desired[p])})
    (backup/"rollback.json").write_text(json.dumps(details,indent=2))
    rollback='''import hashlib,json,os,pathlib,stat,subprocess,tempfile
base=pathlib.Path(__file__).resolve().parent
entries=json.loads((base/"rollback.json").read_text())
for item in entries:
 p=pathlib.Path(item["path"])
 if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=item["installed_sha256"]:
  raise SystemExit("STOP: changed deployed web file: "+str(p))
for item in reversed(entries):
 p=pathlib.Path(item["path"])
 if item["saved"] is None:p.unlink();continue
 st=p.stat();raw=(base/item["saved"]).read_bytes()
 fd,tmp=tempfile.mkstemp(dir=p.parent,prefix=".hotlist-route-rollback-")
 with os.fdopen(fd,"wb") as f:f.write(raw);f.flush();os.fsync(f.fileno())
 os.chmod(tmp,stat.S_IMODE(st.st_mode));os.chown(tmp,st.st_uid,st.st_gid);os.replace(tmp,p)
subprocess.run(["systemctl","restart","torn-fren-web.service"],check=True)
print("HOTLIST_ROUTE_ROLLBACK_COMPLETE")
'''
    (backup/"rollback.py").write_text(rollback)
    report["backup_directory"]=str(backup)
    report["rollback_command"]="sudo python3 "+str(backup/"rollback.py")
    installed=[]
    try:
        for p in changed:
            if p==BRIDGE:continue
            atomic(p,desired[p]);installed.append(p)
        if BRIDGE in changed:
            atomic(BRIDGE,desired[BRIDGE]);installed.append(BRIDGE)
        restart()
        report["live"]=verify(before,files)
        report["status"]="HOTLIST_ROUTE_DEPLOYED"
    except Exception as error:
        report["error"]=str(error)
        recovery=[]
        for p in reversed(installed):
            try:
                regular(p)
                if sha(p.read_bytes())!=sha(desired[p]):raise RuntimeError("A newer file now exists: "+str(p))
                if prior[p] is None:p.unlink()
                else:atomic(p,prior[p])
            except Exception as issue:recovery.append(str(issue))
        try:restart()
        except Exception as issue:recovery.append(str(issue))
        report["status"]="HOTLIST_ROUTE_ROLLED_BACK" if not recovery else "HOTLIST_MANUAL_RECOVERY_REQUIRED"
        report["rollback_errors"]=recovery
    (backup/"report.json").write_text(json.dumps(report,indent=2))
    return report

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--package",required=True)
    ap.add_argument("--apply",action="store_true")
    args=ap.parse_args()
    try:result=rollout(args.package,args.apply)
    except Exception as error:
        result={"status":"HOTLIST_ROUTE_PREFLIGHT_STOPPED","error":str(error),
                "models_changed":False,"databases_changed":False}
    print(json.dumps(result,indent=2))
    return 0 if result["status"] in ("HOTLIST_ROUTE_PREFLIGHT_PASSED",
                                    "HOTLIST_ROUTE_DEPLOYED",
                                    "HOTLIST_ROUTE_ALREADY_INSTALLED") else 1

if __name__=="__main__":
    raise SystemExit(main())
