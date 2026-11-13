"""Read-only contract tests for the V1 -> /experimental Hot List migration."""
from pathlib import Path
import hashlib
import importlib.util
import tempfile
import zipfile

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
for source in ("unexpected source", v1.replace(mod.ASSET_V1,mod.ASSET_V2)):
    try:mod.patch_bridge(source)
    except RuntimeError:pass
    else:raise AssertionError("Routing drift was not rejected")
assert mod.blob(b"abc")==hashlib.sha1(b"blob 3"+bytes([0])+b"abc").hexdigest()
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
print("PASS: route relocator supports only exact v1/v2, full roster, signed source guard")
