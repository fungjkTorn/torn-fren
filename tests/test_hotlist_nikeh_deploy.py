"""Non-destructive contract checks for approved web-only Nikeh Hot List rollout."""
from pathlib import Path
import hashlib, importlib.util, json, subprocess, tempfile, zipfile

ROOT=Path(__file__).resolve().parents[1]
source=ROOT/"deploy/scripts/publish_hotlist_profitability.py"
spec=importlib.util.spec_from_file_location("hotlist_nikeh",source)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
prior_shas=("a544edcb334a1be2f522c87b2dac6a696048a3a8",  # PR #26 Nikeh live UI
            "542bca15a6af7880cf04e4f45dab21136a32e9e4",  # PR #25
            "1db892dcd81059adfd809f0c4c062ccd4513a330")  # PR #24
assets={}
for j,prior_sha in enumerate(prior_shas):
 for name in mod.NAMES:
  path="web/first_release_assets/"+name
  approved=subprocess.check_output(["git","show",f"{prior_sha}:{path}"],cwd=ROOT)
  if j==0:assets[name]=approved
  assert mod.blob(approved) in mod.APPROVED_PRIOR_BLOBS[name]
  assert mod.signed_prior(approved,name)
  assert mod.signed_prior(approved.replace(b"\n",b"\r\n"),name)
  assert not mod.signed_prior(approved+b"unsafe",name)
  assert not mod.signed_prior(approved.replace(b"\n",b"\r\n")+b"x",name)
  assert not mod.signed_prior(approved.replace(b"\n",b"\r\n")+b"\r",name)

with tempfile.TemporaryDirectory() as temp:
 base=Path(temp)
 deployed=base/"web"
 deployed.mkdir()
 archive=base/"nikeh.zip"
 with zipfile.ZipFile(archive,"w") as z:
  for name in mod.NAMES:
   path="web/first_release_assets/"+name
   z.write(ROOT/path,path)
  z.write(source,"deploy/scripts/publish_hotlist_profitability.py")
 desired=mod.package(archive)
 assert len(desired)==4
 for name,raw in assets.items():
  (deployed/name).write_bytes(raw.replace(b"\n",b"\r\n"))
 mod.ASSETS=deployed
 mod.BACKUPS=base/"backups"
 mod.os.geteuid=lambda:0
 mod.routes=lambda:True
 mod.feed=lambda:{"model_sha":"same-forecast-model","forecast_rows":24}
 requested=lambda path:(ROOT/"web/first_release_assets"/(path.split("/")[-1] if path!="/experimental" else "hotlist.html")).read_bytes()
 mod.request=requested
 original={name:(deployed/name).read_bytes() for name in mod.NAMES}
 preflight=mod.install(archive,False)
 assert preflight["status"]=="HOTLIST_NIKEH_PREFLIGHT_PASSED"
 assert all((deployed/name).read_bytes()==original[name] for name in mod.NAMES)
 done=mod.install(archive,True)
 assert done["status"]=="HOTLIST_NIKEH_DEPLOYED",done
 assert done["live"]["models_untouched"]
 assert all((deployed/name).read_bytes()==(ROOT/"web/first_release_assets"/name).read_bytes() for name in mod.NAMES)
 assert mod.install(archive,True)["status"]=="HOTLIST_NIKEH_ALREADY_INSTALLED"
 # A newer byte change must fail before writing anything.
 (deployed/"hotlist.js").write_bytes(b"unknown live drift")
 try:mod.install(archive,True)
 except RuntimeError:pass
 else:raise AssertionError("Drifted UI asset was overwritten")
 assert (deployed/"hotlist.js").read_bytes()==b"unknown live drift"
 # Failed post-deploy verification must roll back to the original bytes.
 for name,raw in original.items():
  (deployed/name).write_bytes(raw)
 verify=mod.verify
 def rejected(before,desired):
  raise RuntimeError("Simulated HTTP verification failure")
 mod.verify=rejected
 rejected_result=mod.install(archive,True)
 assert rejected_result["status"]=="HOTLIST_NIKEH_ROLLED_BACK",rejected_result
 assert all((deployed/name).read_bytes()==original[name] for name in mod.NAMES)
 mod.verify=verify
 # Simulate the first-stage route migration which leaves PR #24 core and JS.
 legacy="1db892dcd81059adfd809f0c4c062ccd4513a330"
 for name in mod.NAMES:
  signed=subprocess.check_output(["git","show",f"{legacy}:web/first_release_assets/{name}"],cwd=ROOT)
  (deployed/name).write_bytes(signed.replace(b"\n",b"\r\n"))
 assert mod.install(archive,False)["status"]=="HOTLIST_NIKEH_PREFLIGHT_PASSED"
 migrated=mod.install(archive,True)
 assert migrated["status"]=="HOTLIST_NIKEH_DEPLOYED",migrated
print("PASS: exact signed previous assets, UI-only updates, idempotence, preflight, rollback, drift rejection")
