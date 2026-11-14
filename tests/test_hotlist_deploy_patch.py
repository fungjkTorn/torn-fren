"""Read-only contract tests for the V1 -> /experimental Hot List migration."""
from pathlib import Path
import hashlib
import importlib.util
import tempfile
import zipfile
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"deploy/scripts/relocate_hotlist.py"
spec=importlib.util.spec_from_file_location("relocate_hotlist", SCRIPT)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

reviewed=(ROOT/"web/first_release_bridge.py").read_text(encoding="utf-8")
assert reviewed.count(mod.ROUTE_V2)==1
assert reviewed.count(mod.ASSET_V2)==1
assert reviewed.count(mod.ROUTE_V1)==0
assert reviewed.count(mod.ASSET_V1)==0
v1=reviewed.replace(mod.ASSET_V2,mod.ASSET_V1).replace(mod.ROUTE_V2,mod.ROUTE_V1)
assert mod.patch_bridge(v1)==reviewed
assert mod.patch_bridge(reviewed)==reviewed

# The installed bridge has an independent VM-specific Git blob. Never replace
# that entire source with GitHub's copy: preserve arbitrary unrelated source
# byte-for-byte, and only mutate the two exact reviewed middleware snippets.
vm_extra = "# Production-only diagnostics retained by the web service.\\n"
vm_source = v1.replace('UI_REVISION="forward-beta-24-v1"',
                       'UI_REVISION="vm-custom-revision"') + "\\n" + vm_extra
assert not mod.approved_v1(vm_source.encode("utf-8"),mod.BRIDGE)
patched = mod.patch_bridge(vm_source)
assert patched == (vm_source.replace(mod.ASSET_V1,mod.ASSET_V2,1)
                    .replace(mod.ROUTE_V1,mod.ROUTE_V2,1))
assert patched.replace(mod.ASSET_V2,mod.ASSET_V1,1).replace(
    mod.ROUTE_V2,mod.ROUTE_V1,1)==vm_source
assert 'vm-custom-revision' in patched and vm_extra in patched
assert mod.patch_bridge(patched)==patched
for suspicious in (
    v1.replace('async def dispatch(', 'async def different_dispatch('),
    v1.replace('app.add_middleware(BetaMiddleware)','app.add_middleware(OtherMiddleware)'),
    v1.replace(mod.ASSET_V1,mod.ASSET_V1+"\\n                # "+mod.ASSET_V1)
):
    try: mod.patch_bridge(suspicious)
    except RuntimeError: pass
    else: raise AssertionError("Ambiguous or misplaced routing patch was not rejected")
for source in ("unexpected source", v1.replace(mod.ASSET_V1,mod.ASSET_V2)):
    try:mod.patch_bridge(source)
    except RuntimeError:pass
    else:raise AssertionError("Routing drift was not rejected")
assert mod.blob(b"abc")==hashlib.sha1(b"blob 3"+bytes([0])+b"abc").hexdigest()

# The V1 version was installed through a Windows Git archive, which can convert
# LF to CRLF. Accept ONLY that byte-for-byte conversion of the pinned Git blob.
v1_commit = "e4ddb3e5851e0080dd65261012d469da85f83879"
for name in ("hotlist.css", "hotlist-core.js", "hotlist.html", "hotlist.js"):
    filename = "web/first_release_assets/" + name
    signed = subprocess.check_output(["git", "show", f"{v1_commit}:{filename}"], cwd=ROOT)
    path = mod.ASSETS / name
    crlf = signed.replace(b"\n", b"\r\n")
    assert mod.blob(signed) == mod.V1_BLOBS[str(path)], name
    assert mod.approved_v1(signed, path), name
    assert mod.approved_v1(crlf, path), name
    assert not mod.approved_v1(signed + b"X", path), name
    assert not mod.approved_v1(crlf + b"X", path), name
    assert not mod.approved_v1(crlf + b"\r", path), name
    assert not mod.approved_v1(signed, mod.ASSETS / "unknown-file.js"), name
assert set(mod.NAMES)=={"hotlist.html","hotlist.js","abroad-roster.json"}

with tempfile.TemporaryDirectory() as folder:
    archive=Path(folder)/"hotlist-route-test.zip"
    with zipfile.ZipFile(archive,"w") as z:
        for name in mod.NAMES:
            relative="web/first_release_assets/"+name
            z.write(ROOT/relative,relative)
        z.write(SCRIPT,"deploy/scripts/relocate_hotlist.py")
    files=mod.read_package(archive)
    assert len(files)==3
    assert (mod.ASSETS/"abroad-roster.json") in files
print("PASS: exact middleware-only patch preserves VM bridge customizations, validates routes, and enforces signed asset blobs")
