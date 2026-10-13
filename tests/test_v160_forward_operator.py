"""V160 isolated operator safety tests."""
import ast
import hashlib
import re
import shutil
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SH=ROOT/"deploy/scripts/v160_forward24_operator.sh"
LAUNCH=ROOT/"deploy/scripts/v160_forward_shadow_launcher.py"
SERVICE=ROOT/"deploy/systemd/torn-fren-v160-forward24.service"
TIMER=ROOT/"deploy/systemd/torn-fren-v160-forward24.timer"


class PrivateV160OperatorTests(unittest.TestCase):
    def test_explicit_enable_only_and_status_default(self):
        script=SH.read_text(encoding="utf-8")
        self.assertIn("${1:-status}",script)
        self.assertIn('if [[ "$ACTION" == status ]]',script)
        self.assertIn("smoke|record|report|enable|disable",script)
        self.assertIn('if [[ "$ACTION" == smoke ]]',script)
        self.assertIn("sudo systemctl enable --now",script)
        self.assertIn("sudo systemctl disable --now",script)
        self.assertIn('git show "${PIN}:research/${name}.py"',script)
        self.assertIn("v160_prospective_v151_shadow",script)
        self.assertIn("v161_prospective_v151_forward_report",script)
        self.assertIn("v38_roster.json",script)
        self.assertIn('test -r "$COLLECTOR"',script)
        self.assertNotIn('test -d "$WORK/.git"',script)
        self.assertIn('git -C "$WORK" rev-parse --is-inside-work-tree',script)
        self.assertIn('git -C "$WORK" rev-parse --show-toplevel',script)
        subprocess.run(["bash","-n",str(SH)],check=True)


    def test_status_reports_real_complete_and_incomplete_batches_read_only(self):
        script=SH.read_text(encoding="utf-8")
        self.assertIn("source.as_uri()+\"?mode=ro\"",script)
        self.assertIn("PRAGMA query_only=ON",script)
        self.assertIn("LIMIT 3",script)
        source=script.split("<<'PY_STATUS'\\n".replace("\\n","\n"),1)[1].split(
            "\nPY_STATUS",1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"v160_v151_prospective24.db"
            with sqlite3.connect(db) as con:
                con.execute("CREATE TABLE v160_ticks(issued_epoch INTEGER,"
                            "captured_epoch INTEGER,source_heartbeat_epoch INTEGER,"
                            "policy_id TEXT,roster_count INTEGER)")
                con.execute("CREATE TABLE v160_issued(item_key TEXT,"
                            "issued_epoch INTEGER,policy_id TEXT,payload_json TEXT)")
                for issue,rows in ((100,23),(200,24)):
                    con.execute("INSERT INTO v160_ticks VALUES(?,?,?,?,?)",
                                (issue,issue+1,issue-10,"p",24))
                    con.executemany(
                        "INSERT INTO v160_issued VALUES(?,?,?,?)",
                        [(str(i),issue,"p","{}") for i in range(rows)])
            digest=lambda:hashlib.sha256(db.read_bytes()).hexdigest()
            before=digest()
            result=subprocess.run([sys.executable,"-c",source,str(db)],
                                  check=True,capture_output=True,text=True)
            self.assertEqual(digest(),before)
            report=json.loads(result.stdout)
            self.assertEqual(
                [(r["issued_epoch"],r["recorded_items"],r["batch_complete"])
                 for r in report["last_three_batches"]],
                [(200,24,True),(100,23,False)])
            self.assertTrue(report["has_prospectively_recorded_batches"])

    def test_git_worktree_git_file_is_valid_checkout(self):
        # The VM can use a linked research worktree with .git as a FILE.
        # The old operator's test -d would reject this valid checkout.
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            source=base/"source"
            worktree=base/"research-worktree"
            subprocess.run(["git","init","-q",str(source)],check=True,
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            subprocess.run([
                "git","-C",str(source),
                "-c","user.name=CI","-c","user.email=ci@example.invalid",
                "commit","-q","--allow-empty","-m","init"
            ],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            subprocess.run(["git","-C",str(source),"worktree",
                            "add","--detach",str(worktree),"HEAD"],
                           check=True,stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
            self.assertTrue((worktree/".git").is_file())
            self.assertFalse((worktree/".git").is_dir())
            inside=subprocess.check_output([
                "git","-C",str(worktree),"rev-parse","--is-inside-work-tree"
            ],text=True).strip()
            root=subprocess.check_output([
                "git","-C",str(worktree),"rev-parse","--show-toplevel"
            ],text=True).strip()
            self.assertEqual(inside,"true")
            self.assertEqual(root,str(worktree))

    @staticmethod
    def _staged_names(script):
        match=re.search(r"for name in \\\n(.*?)\ndo\n",script,re.S)
        if not match:
            raise AssertionError("operator must explicitly enumerate pinned stage modules")
        return re.findall(r"(?m)^\s*(v[0-9][A-Za-z0-9_]*)\b",match.group(1))

    def test_stage_contains_full_recursive_research_import_closure(self):
        # A CI pass on the checkout is insufficient: on the VM the pinned
        # staging directory intentionally contains far fewer modules.
        names=self._staged_names(SH.read_text(encoding="utf-8"))
        self.assertEqual(len(names),len(set(names)))
        self.assertIn("v110_multicycle_restock_horizon_audit",names)
        self.assertIn("v38_snapshot_schema",names)
        roots={f"research/{name}.py" for name in names}
        roots|={"research/plushie_champions/common.py",
                "research/plushie_champions/__init__.py"}
        for path in sorted(roots):
            source=ROOT/path
            self.assertTrue(source.is_file(),str(source))
            tree=ast.parse(source.read_text(encoding="utf-8"),filename=str(source))
            for node in ast.walk(tree):
                modules=[]
                if isinstance(node,ast.ImportFrom) and node.module:
                    modules.append(node.module)
                    if node.module=="research":
                        modules.extend("research."+alias.name for alias in node.names)
                elif isinstance(node,ast.Import):
                    modules.extend(alias.name for alias in node.names)
                for module in modules:
                    if not module.startswith("research."):
                        continue
                    parts=module.split(".")
                    if parts[1]=="plushie_champions":
                        required=("research/plushie_champions/"+
                                  (parts[2] if len(parts)>2 else "__init__")+".py")
                    else:
                        required="research/"+parts[1]+".py"
                    if (ROOT/required).is_file():
                        self.assertIn(required,roots,
                            f"{path} requires unbundled {required}")

    def test_isolated_stage_imports_succeed_and_missing_dependency_fails_closed(self):
        names=self._staged_names(SH.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            stage=Path(tmp)/"pinned"/"research"
            champion=stage/"plushie_champions"
            champion.mkdir(parents=True)
            for name in names:
                shutil.copy2(ROOT/"research"/(name+".py"),stage/(name+".py"))
            for name in ("__init__.py","common.py"):
                shutil.copy2(ROOT/"research/plushie_champions"/name,champion/name)
            shutil.copy2(ROOT/"research/v38_roster.json",stage/"v38_roster.json")
            script=r"""
import importlib.util
import sys
from pathlib import Path
launcher=Path(sys.argv[1])
spec=importlib.util.spec_from_file_location("isolated_v160",launcher)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.WORK=Path(sys.argv[2])
module.STAGE=Path(sys.argv[3]).parent
module.load()
print("ISOLATED_STAGED_IMPORT_OK")
"""
            def load():
                return subprocess.run(
                    [sys.executable,"-c",script,str(LAUNCH),str(ROOT),
                     str(champion)],
                    text=True,capture_output=True,check=False)
            first=load()
            self.assertEqual(first.returncode,0,first.stderr)
            self.assertIn("ISOLATED_STAGED_IMPORT_OK",first.stdout)
            # Remove a transitive module while keeping it in the checkout:
            # the isolated importer must NOT recover it from the checkout.
            (stage/"v110_multicycle_restock_horizon_audit.py").unlink()
            failure=load()
            self.assertNotEqual(failure.returncode,0)
            self.assertIn("v110_multicycle_restock_horizon_audit",failure.stderr)

    def test_new_timer_and_service_isolate_budget(self):
        service=SERVICE.read_text(encoding="utf-8")
        timer=TIMER.read_text(encoding="utf-8")
        for needed in (
            "Type=oneshot","User=ubuntu","PrivateNetwork=yes",
            "ProtectSystem=strict","ReadOnlyPaths=/opt/torn-fren/data",
            "ReadWritePaths=/var/lib/torn-fren-v38","CPUQuota=30%",
            "MemoryMax=512M","flock -n",
            "v160_forward_shadow_launcher.py --record"):
            self.assertIn(needed,service)
        self.assertIn("Persistent=false",timer)
        self.assertIn("torn-fren-v160-forward24.service",timer)
        self.assertNotIn("web/app.py",service)

    def test_launcher_supports_only_three_modes_and_pinned_imports(self):
        script=LAUNCH.read_text(encoding="utf-8")
        for name in ('"--preview"','"--record"','"--report"',
                     "unpinned shadow module",
                     "capture.capture_once(record=a.record)",
                     "report.score(days=2)"):
            self.assertIn(name,script)
        self.assertNotIn("web.app",script)


if __name__=="__main__":
    unittest.main()
