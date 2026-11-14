"""Read-only contract: surgical Beanstalk API installation and rollback."""
import ast
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT/"deploy/scripts/publish_beanstalk_hot_list.py"
spec = importlib.util.spec_from_file_location("deploy_beanstalk_api", INSTALLER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# Before this PR, /api/beanstalk-hot-list did not exist in the web bridge.
previous = subprocess.check_output(
    ["git", "show", "ebbf1bc15e30fd1d2e9214216ba15437634134d3:web/first_release_bridge.py"],
    cwd=ROOT,
).decode("utf-8")
approved = (ROOT/"web/first_release_bridge.py").read_text()
patched = mod.patch_bridge(previous)
assert patched == approved, "Surgical bridge patch must match committed source"
assert mod.patch_bridge(approved) == approved, "Route installation must be idempotent"
assert patched.replace(mod.INSERT+mod.ANCHOR, mod.ANCHOR) == previous

# Preserve custom VM code that is unrelated to the two exact routing anchors.
custom = previous.replace('UI_REVISION="forward-beta-24-v1"',
                          'UI_REVISION="vm-independent-change"')
custom += "\n# Another VM-local diagnostic extension\n"
updated = mod.patch_bridge(custom)
assert 'vm-independent-change' in updated
assert updated.replace(mod.INSERT+mod.ANCHOR,mod.ANCHOR)==custom

# Must reject altered, moved or duplicated middleware anchors.
for bad in (
    previous.replace(mod.ANCHOR, mod.ANCHOR+"\n"+mod.ANCHOR),
    previous.replace('async def dispatch(', 'async def altered_dispatch('),
    previous.replace('app.add_middleware(BetaMiddleware)',
                     'app.add_middleware(OtherMiddleware)'),
    previous.replace(mod.ANCHOR,'            if path=="/other":'),
):
    try:
        mod.patch_bridge(bad)
    except (RuntimeError, SyntaxError):
        pass
    else:
        raise AssertionError("Unsafe routing modification accepted")


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    web = root/"web"
    web.mkdir()
    bridge = web/"first_release_bridge.py"
    new_module = web/"beanstalk_hot_list.py"
    bridge.write_text(previous)
    archive = root/"reviewed.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for name in sorted(mod.PACKAGE):
            z.write(ROOT/name, name)

    expected = mod.load_package(archive)
    assert expected == (ROOT/"web/beanstalk_hot_list.py").read_bytes()
    mod.ROOT = root
    mod.BRIDGE = bridge
    mod.MODULE = new_module
    mod.BACKUPS = root/"backups"
    mod.os.geteuid = lambda: 0
    mod.public_preflight = lambda: {"catalog_countries": 11,
                                    "forecast_rows": 24, "model_sha": "unchanged"}
    restarts = []
    mod.restart = lambda: restarts.append("restart")
    mod.verify = lambda: {"public_path":mod.PUBLIC_PATH,
                          "picks":7,"generated_at":"2026-11-14T00:00:00Z"}

    before = bridge.read_bytes()
    dry = mod.install(archive, apply=False)
    assert dry["status"] == "BEANSTALK_HOT_LIST_PREFLIGHT_PASSED",dry
    assert bridge.read_bytes() == before and not new_module.exists()
    applied = mod.install(archive, apply=True)
    assert applied["status"] == "BEANSTALK_HOT_LIST_DEPLOYED", applied
    assert new_module.read_bytes() == expected
    assert bridge.read_bytes().decode() == approved
    assert len(restarts)==1
    assert mod.install(archive, apply=True)["status"]=="BEANSTALK_HOT_LIST_ALREADY_INSTALLED"

    # Simulate unknown future version; refuse before modifying anything.
    new_module.write_text("independent VM work")
    try:
        mod.install(archive, apply=True)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Unknown VM-side edits were not rejected")
    assert new_module.read_text()=="independent VM work"

    # Simulate failed HTTP verification: rollback BOTH files and restart.
    new_module.write_bytes(expected)
    bridge.write_bytes(before)
    new_module.unlink()
    def failed_verify():
        raise RuntimeError("Synthetic public URL did not return seven picks")
    mod.verify = failed_verify
    rolled = mod.install(archive, apply=True)
    assert rolled["status"] == "BEANSTALK_HOT_LIST_ROLLED_BACK",rolled
    assert bridge.read_bytes() == before
    assert not new_module.exists()
    assert len(restarts)==3

print("PASS: Beanstalk API bridge patch preserves VM source, dry run, CORS, install and rollback")
