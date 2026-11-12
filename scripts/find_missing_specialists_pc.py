"""Read-only recovery scan for archived TORN-FREN item-specific specialist code.

Scans the selected PC roots, including nested old checkouts, for pinned
specialist script names. Searches Git's reachable history for older/deleted
filenames. NEVER modifies or copies files, executes recovered code, or
examines API keys/secret file contents.

Usage:
  .\\.venv\\Scripts\\python.exe .\\scripts\\find_missing_specialists_pc.py \\
    --root "$env:USERPROFILE\\Desktop" \\
    --output .\\historical_pc_results\\specialist-source-search.json
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import json
import os
import re
import subprocess

TARGETS={
 "arg:Monkey Plushie":"checkpoint4_online_selector.py",
 "swi:Chamois Plushie":"checkpoint4_online_selector.py",
 "chi:Panda Plushie":"panda_pair_selector_ml.py",
 "sou:Lion Plushie":"lion_pair_selector_ml.py",
 "uae:Camel Plushie":"camel_fast_selector.py",
 "uni:Nessie Plushie":"recent_phase_select.py",
 "uni:Red Fox Plushie":"rf_localgrid.py",
 "jap:Xanax":"japan_xanax_specialist.py",
}
EXTRA_NAMES={
 "jap:Xanax":("renewal_shadow.py", "xanax_specialist.py"),
}
KEYWORDS=("camel","nessie","red_fox","redfox","panda","lion","checkpoint4",
          "chamois","monkey","japan_xanax","xanax","rf_localgrid",
          "recent_phase","pair_selector")
SKIP={"node_modules",".venv","venv","__pycache__",".mypy_cache",
      "site-packages","historical_pc_data","historical_pc_results",
      ".pytest_cache","dist","build",".next","__pypackages__"}
SUPPORTED={".py",".ipynb"}
MAX_SEEN=200000
MAX_MATCH=500
MAX_GIT=30


def _matches(name):
    stem=name.lower().replace("-","_").replace(" ","_")
    return any(k in stem for k in KEYWORDS)


def _index_hit(path):
    suffix=Path(path).suffix.lower()
    return suffix in SUPPORTED and _matches(Path(path).name)


def scan(roots, *, check_git=True):
    hits=[];git_roots=[];seen=0;truncated=False
    visited=set()
    for initial in roots:
        root=Path(initial).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Only existing read-only search directories are allowed: "+str(root))
        for current, dirs, files in os.walk(root,topdown=True,followlinks=False):
            this=Path(current)
            if this.is_symlink():
                dirs[:]=[]
                continue
            try:identity=str(this.resolve(strict=True)).casefold()
            except (OSError,RuntimeError):dirs[:]=[];continue
            if identity in visited:
                dirs[:]=[]
                continue
            visited.add(identity)
            if ".git" in dirs or ".git" in files:
                git_roots.append(str(this))
            dirs[:]=[d for d in dirs if d.lower() not in SKIP
                      and d!=".git" and not (this/d).is_symlink()]
            for file in files:
                seen+=1
                if _index_hit(file):
                    path=str(this/file)
                    if len(hits)<MAX_MATCH:
                        hits.append(path)
                    else:
                        truncated=True
                if seen>=MAX_SEEN:
                    truncated=True
                    dirs[:]=[]
                    break
            if seen>=MAX_SEEN:
                break
        if seen>=MAX_SEEN:
            break
    historical=[]
    if check_git:
        for folder in sorted(set(git_roots))[:MAX_GIT]:
            try:
                cmd=["git","-C",folder,"rev-list","--all","--objects"]
                proc=subprocess.run(cmd,capture_output=True,text=True,
                                    errors="replace",timeout=30,check=False)
                if proc.returncode:
                    historical.append(dict(repository=folder,status="ERROR",
                        files=[]))
                    continue
                found=[]
                for line in proc.stdout.splitlines():
                    if " " not in line:continue
                    sha,path=line.split(" ",1)
                    if _index_hit(path):
                        found.append(dict(path=path,git_object_sha=sha))
                historical.append(dict(repository=folder,status="CHECKED",
                    files=found[:MAX_MATCH],
                    truncated=len(found)>MAX_MATCH))
            except (OSError,subprocess.TimeoutExpired):
                historical.append(dict(repository=folder,status="GIT_SEARCH_UNAVAILABLE",
                    files=[]))
    by_key={}
    allpaths=list(hits)
    for history in historical:
        allpaths += [r["path"] for r in history.get("files",[])]
    for key,source in TARGETS.items():
        names={source.lower(),*(n.lower() for n in EXTRA_NAMES.get(key,()))}
        exact=[p for p in allpaths if Path(p).name.lower() in names]
        related=[p for p in allpaths if _matches(Path(p).name)
                 and any(w in Path(p).name.lower().replace("-","_")
                         for w in (key.split(":")[1].lower().split()[0],
                                   "xanax" if key=="jap:Xanax" else source.split("_")[0]))]
        by_key[key]=dict(recorded_filename=source,
            exact_name_hits=sorted(set(exact))[:50],
            related_filename_hits=sorted(set(related))[:30],
            original_incumbent_executable_verified=False)
    return dict(kind="TORN_FREN_SPECIALIST_SOURCE_RECOVERY_SEARCH",
                status="SCAN_TRUNCATED" if truncated else "SOURCE_NAMES_SEARCHED",
                roots=[str(Path(p).resolve()) for p in roots],
                total_examined_file_entries=seen,
                found_source_filenames=sorted(set(hits)),
                git_repositories_checked=historical,
                by_item=by_key,
                original_model_equivalence_certified=False,
                files_modified=False,
                content_or_secrets_read=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root",action="append",type=Path,
                   help="Directory to search; repeat as needed (Desktop is typical)")
    p.add_argument("--output",type=Path,
                   help="Write JSON only to a NEW file in existing results directory")
    p.add_argument("--skip-git-history",action="store_true")
    a=p.parse_args(argv)
    roots=a.root or [Path.home()/"Desktop"]
    result=scan(roots,check_git=not a.skip_git_history)
    for key,row in result["by_item"].items():
        count=len(row["exact_name_hits"])
        print(key+" | "+str(count)+" exact old filenames",
              " | ".join(row["exact_name_hits"][:2]))
    print("SEARCHED",result["total_examined_file_entries"],
          "files in",len(result["roots"]),"root(s); checked",
          len(result["git_repositories_checked"]),"Git histories.")
    print("STATUS",result["status"])
    if a.output is not None:
        out=a.output.expanduser().resolve()
        if out.exists() or out.suffix.lower()!=".json" or not out.parent.is_dir():
            p.error("Specify a NEW results .json in an existing directory")
        out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",
                       encoding="utf-8")
        print("REPORT",out)


if __name__=="__main__":
    main()
