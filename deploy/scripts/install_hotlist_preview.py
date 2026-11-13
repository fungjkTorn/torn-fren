"""Guarded web-only Hot List rollout. No model, collector or database writes.

Invoke from deploy/Publish-HotList.ps1. By default, this script performs
read-only preflight; --apply is required for any web-file changes.
"""
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

BASE = Path("/opt/torn-fren")
ASSETS = BASE / "web/first_release_assets"
BRIDGE = BASE / "web/first_release_bridge.py"
BACKUPS = Path("/var/backups/torn-fren-ops")
SERVICE = "torn-fren-web.service"
SITE = "http://127.0.0.1:8000"
ASSET_NAMES = ("hotlist.html", "hotlist.css", "hotlist.js", "hotlist-core.js")
PACKAGE_NAMES = {f"web/first_release_assets/{n}" for n in ASSET_NAMES}
PACKAGE_NAMES.add("deploy/scripts/install_hotlist_preview.py")
OLD_ASSET_RULE = 'if name in ("beta.js","beta.css"):'
NEW_ASSET_RULE = 'if name in ("beta.js","beta.css","hotlist.js","hotlist-core.js","hotlist.css"):'
OLD_ROUTE = '            if path in ("/experimental","/travel-decisions"):'
NEW_ROUTE = '''            if path=="/" and not (request.query_params.get("country") or request.query_params.get("item")):
                return FileResponse(ASSETS/"hotlist.html",media_type="text/html",headers={"Cache-Control":"no-store"})
            if path in ("/experimental","/travel-decisions"):'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fetch(path, timeout=20):
    with urllib.request.urlopen(SITE + path, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}: {path}")
        return response.read(8 * 1024 * 1024)


def is_running():
    return subprocess.run(("systemctl", "is-active", "--quiet", SERVICE), check=False).returncode == 0


def preflight():
    if not is_running():
        raise RuntimeError("Web service is not running; stopping without changes")
    board = json.loads(fetch("/api/first-release"))
    catalog = json.loads(fetch("/api/catalog"))
    if not isinstance(board.get("rows"), list) or not board["rows"]:
        raise RuntimeError("Live first-release feed has no rows")
    if not isinstance(catalog.get("countries"), list) or not catalog["countries"]:
        raise RuntimeError("Live catalog is unavailable")
    if b"hotlist.js" in fetch("/?country=mex&item=Dahlia"):
        raise RuntimeError("Stock graph route was replaced unexpectedly")
    for path in ("/experimental", "/travel-decisions"):
        if b"beta.js" not in fetch(path):
            raise RuntimeError("Existing planner view not available: " + path)
    return {"model_sha": board.get("model_sha"), "forecast_rows": len(board["rows"]),
            "catalog_countries": len(catalog["countries"])}


def read_package(path):
    with zipfile.ZipFile(path) as z:
        entries = [i for i in z.infolist() if not i.is_dir()]
        names = {i.filename for i in entries}
        if names != PACKAGE_NAMES or len(entries) != len(PACKAGE_NAMES):
            raise ValueError("Hot List archive contains unexpected or missing files")
        if sum(i.file_size for i in entries) > 1024 * 1024:
            raise ValueError("Hot List archive exceeds 1 MB")
        files = {name: z.read("web/first_release_assets/" + name) for name in ASSET_NAMES}
    if b"hotlist-core.js" not in files["hotlist.html"] or b"Hot List" not in files["hotlist.html"]:
        raise ValueError("Invalid Hot List homepage")
    if b"0.95" not in files["hotlist-core.js"]:
        raise ValueError("Missing 5% Item Market fee")
    if b"localStorage" in files["hotlist.js"] or b"save-sale" in files["hotlist.js"]:
        raise ValueError("Unexpected manual price-override code")
    return files


def patch_bridge(source):
    if NEW_ASSET_RULE in source and NEW_ROUTE in source:
        return source
    if source.count(OLD_ASSET_RULE) != 1 or source.count(OLD_ROUTE) != 1:
        raise RuntimeError("Installed bridge does not match reviewed route anchors")
    if NEW_ASSET_RULE in source or NEW_ROUTE in source:
        raise RuntimeError("Partially patched bridge: refusing to overwrite")
    patched = source.replace(OLD_ASSET_RULE, NEW_ASSET_RULE, 1).replace(OLD_ROUTE, NEW_ROUTE, 1)
    ast.parse(patched, filename=str(BRIDGE))
    return patched


def check_paths():
    if not ASSETS.is_dir() or ASSETS.is_symlink() or not BRIDGE.is_file() or BRIDGE.is_symlink():
        raise RuntimeError("Unexpected website installation paths")
    for name in ASSET_NAMES:
        p = ASSETS / name
        if p.is_symlink() or (p.exists() and not p.is_file()):
            raise RuntimeError("Unexpected asset path: " + name)


def install_bytes(path, data):
    original = path.stat() if path.exists() else path.parent.stat()
    fd, temp = tempfile.mkstemp(prefix=".hotlist-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(temp, stat.S_IMODE(original.st_mode) if path.exists() else 0o644)
        os.chown(temp, original.st_uid, original.st_gid)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def restart_and_wait():
    subprocess.run(("systemctl", "restart", SERVICE), check=True, timeout=35)
    for _ in range(20):
        if is_running():
            try:
                fetch("/api/first-release", timeout=5)
                return
            except Exception:
                pass
        time.sleep(2)
    raise RuntimeError("Web service did not recover after restart")


def check_live(files, before):
    assert b"hotlist.js" in fetch("/")
    assert b"hotlist.js" not in fetch("/?country=mex&item=Dahlia")
    for name in ASSET_NAMES:
        if name == "hotlist.html":
            continue  # served at root, not under the asset allowlist
        actual = fetch("/first-release-assets/" + name)
        if digest(actual) != digest(files[name]):
            raise RuntimeError("Live Hot List asset mismatch: " + name)
    for path in ("/experimental", "/travel-decisions"):
        if b"beta.js" not in fetch(path):
            raise RuntimeError("Original planner view regressed: " + path)
    after = preflight()
    if before["model_sha"] != after["model_sha"]:
        raise RuntimeError("Model identity changed during website update")
    if before["forecast_rows"] != after["forecast_rows"]:
        raise RuntimeError("Live forecast roster changed during website update")
    return {"homepage": "HOT_LIST", "stock_graph": "PRESERVED",
            "other_planner_views": "PRESERVED", "market_feed": "AVAILABLE",
            "model_sha": after["model_sha"], "forecast_rows": after["forecast_rows"]}


def write_rollback(backup, original, installed):
    manifest = {"files": []}
    for path, old in original.items():
        manifest["files"].append({"path": str(path), "previous": None if old is None else
                                  "original/" + str(len(manifest["files"])) + ".bin",
                                  "installed_sha256": digest(installed[path])})
        if old is not None:
            filename = backup / manifest["files"][-1]["previous"]
            filename.parent.mkdir(parents=True, exist_ok=True)
            filename.write_bytes(old)
    (backup / "rollback.json").write_text(json.dumps(manifest, indent=2))
    script = '''import json,os,pathlib,subprocess,tempfile,stat
root=pathlib.Path(__file__).resolve().parent
items=json.loads((root/"rollback.json").read_text())["files"]
import hashlib
for item in items:
 p=pathlib.Path(item["path"])
 if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=item["installed_sha256"]:
  raise SystemExit("STOP: newer website file encountered: "+str(p))
for item in reversed(items):
 p=pathlib.Path(item["path"])
 if item["previous"] is None: p.unlink()
 else:
  src=(root/item["previous"]).read_bytes()
  old=p.stat()
  fd,tmp=tempfile.mkstemp(dir=p.parent,prefix=".hotlist-rollback-")
  with os.fdopen(fd,"wb") as f:f.write(src);f.flush();os.fsync(f.fileno())
  os.chmod(tmp,stat.S_IMODE(old.st_mode));os.chown(tmp,old.st_uid,old.st_gid);os.replace(tmp,p)
subprocess.run(["systemctl","restart","torn-fren-web.service"],check=True)
print("HOTLIST_ROLLBACK_COMPLETE")
'''
    (backup / "rollback.py").write_text(script)
    return "sudo python3 " + str(backup / "rollback.py")


def rollout(package, apply):
    if os.geteuid() != 0:
        raise PermissionError("Must run with sudo")
    check_paths()
    files = read_package(package)
    current_bridge = BRIDGE.read_text(encoding="utf-8")
    updated_bridge = patch_bridge(current_bridge)
    current = {BRIDGE: BRIDGE.read_bytes()}
    desired = {BRIDGE: updated_bridge.encode("utf-8")}
    for name in ASSET_NAMES:
        p = ASSETS / name
        current[p] = p.read_bytes() if p.exists() else None
        desired[p] = files[name]
    changed = [p for p in desired if desired[p] != current[p]]
    # An older, unknown copy of a Hot List asset is not safe to replace blindly.
    for name in ASSET_NAMES:
        p = ASSETS / name
        if current[p] is not None and current[p] != desired[p]:
            raise RuntimeError("Hot List asset has unexpected installed content: " + name)
    before = preflight()
    if not changed:
        return {"status": "HOTLIST_ALREADY_INSTALLED", "live": check_live(files, before)}
    summary = {"status": "HOTLIST_PREFLIGHT_PASSED", "changed_files": [str(p) for p in changed],
               "model_sha": before["model_sha"], "forecasts": before["forecast_rows"],
               "services_to_restart": [SERVICE], "models_changed": False,
               "databases_changed": False, "collectors_changed": False}
    if not apply:
        return summary

    BACKUPS.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(
        prefix=dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-hotlist-",
        dir=BACKUPS))
    os.chmod(backup, 0o700)
    rollback_cmd = write_rollback(backup, {p: current[p] for p in changed},
                                  {p: desired[p] for p in changed})
    written = []
    try:
        # Stage assets first, then bridge; none of the new assets are routed
        # until the existing web process restarts.
        for p in changed:
            if p == BRIDGE:
                continue
            install_bytes(p, desired[p])
            written.append(p)
        if BRIDGE in changed:
            install_bytes(BRIDGE, desired[BRIDGE])
            written.append(BRIDGE)
        restart_and_wait()
        summary["live"] = check_live(files, before)
        summary.update(status="HOTLIST_DEPLOYED", backup_directory=str(backup),
                       rollback_command=rollback_cmd)
    except Exception as exc:
        summary["error"] = str(exc)
        rollback_problems = []
        for p in reversed(written):
            try:
                if p.is_symlink() or not p.is_file() or digest(p.read_bytes()) != digest(desired[p]):
                    raise RuntimeError("Newer file found; cannot restore " + str(p))
                if current[p] is None:
                    p.unlink()
                else:
                    install_bytes(p, current[p])
            except Exception as rollback_error:
                rollback_problems.append(str(rollback_error))
        try:
            restart_and_wait()
        except Exception as rollback_error:
            rollback_problems.append(str(rollback_error))
        summary.update(status="HOTLIST_DEPLOYMENT_ROLLED_BACK" if not rollback_problems
                       else "HOTLIST_MANUAL_RECOVERY_REQUIRED",
                       rollback_problems=rollback_problems,
                       backup_directory=str(backup),
                       rollback_command=rollback_cmd)
    (backup / "deploy-report.json").write_text(json.dumps(summary, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = rollout(args.package, args.apply)
    except Exception as exc:
        result = {"status": "HOTLIST_PREFLIGHT_STOPPED", "error": str(exc),
                  "models_changed": False, "databases_changed": False}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in (
        "HOTLIST_PREFLIGHT_PASSED", "HOTLIST_DEPLOYED", "HOTLIST_ALREADY_INSTALLED"
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
