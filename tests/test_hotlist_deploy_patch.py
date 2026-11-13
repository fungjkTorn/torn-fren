"""Verify the guarded VM patch preserves the reviewed Hot List bridge source."""
from pathlib import Path
import importlib.util

root = Path(__file__).resolve().parents[1]
path = root / "deploy/scripts/install_hotlist_preview.py"
spec = importlib.util.spec_from_file_location("hotlist_installer", path)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

reviewed = (root / "web/first_release_bridge.py").read_text(encoding="utf-8")
assert reviewed.count(installer.NEW_ASSET_RULE) == 1
assert reviewed.count(installer.NEW_ROUTE) == 1
baseline = reviewed.replace(installer.NEW_ASSET_RULE, installer.OLD_ASSET_RULE)
baseline = baseline.replace(installer.NEW_ROUTE, installer.OLD_ROUTE)
assert installer.patch_bridge(baseline) == reviewed
assert installer.patch_bridge(reviewed) == reviewed, "Already-installed rollout must be idempotent"
try:
    installer.patch_bridge(baseline.replace(installer.OLD_ASSET_RULE, installer.NEW_ASSET_RULE))
except RuntimeError:
    pass
else:
    raise AssertionError("Partial installation must stop safely")
try:
    installer.patch_bridge("different server source")
except RuntimeError:
    pass
else:
    raise AssertionError("Source drift must block deployment")
assert sorted(installer.ASSET_NAMES) == ["hotlist-core.js", "hotlist.css", "hotlist.html", "hotlist.js"]
print("PASS: guarded Hot List bridge patch is exact, idempotent, and refuses drift")
