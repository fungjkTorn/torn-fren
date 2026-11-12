#!/usr/bin/env python3
"""Run candidate publishers on disposable inference copies; never change services."""
import argparse,hashlib,json,os,pwd,shlex,shutil,sqlite3,subprocess,tempfile,time,zipfile
from pathlib import Path
from contextlib import closing

BASE='/var/lib/torn-fren-live-beta'
COHORTS={'incumbents':('first-ten-beta','',10),'challengers':('challengers-beta','challengers',6),'next_six':('next-six-beta','next-six',6),'final_pair':('final-pair-beta','final-pair',2),'japan_private':('japan-private','japan-private',1)}
COLLECTOR=Path('/opt/torn-fren/data/stock_history.db')

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def props(unit):
 r=subprocess.run(['systemctl','show',unit,'-p','ExecStart','-p','WorkingDirectory','-p','User','-p','ActiveState'],capture_output=True,text=True,check=True,timeout=10)
 return dict(line.split('=',1) for line in r.stdout.splitlines() if '=' in line)
def launch_tokens(raw):
 import re
 m=re.search(r'argv\[\]=(.*?) ; ignore_errors=',raw)
 if not m:m=re.search(r'argv\[\]=(.*?) ; ignore_errors=',raw.replace('ignore_errors','ignore_errors'))
 if not m:raise ValueError('UNRECOGNIZED_SYSTEMD_EXEC_FORMAT')
 return shlex.split(m.group(1))
def option(args,key,default=None):
 return args[args.index(key)+1] if key in args and args.index(key)+1<len(args) else default

def snapshot(path):
 s=json.loads((path/'latest.json').read_text())
 return {'items':len(s.get('items',{})),'published_epoch':s.get('published_epoch'),'valid_until_epoch':s.get('valid_until_epoch'),'model_sha':s.get('model_sha')}
def sqlite_copy(source,dest):
 with closing(sqlite3.connect(Path(source).resolve(strict=True).as_uri()+'?mode=ro',uri=True,timeout=10)) as src,closing(sqlite3.connect(dest)) as dst:
  src.execute('PRAGMA query_only=ON');src.backup(dst,pages=1024,sleep=.01)
 os.chmod(dest,0o600)
def sanitized_failure(log):
 names=('IndexError','ValueError','AssertionError','CacheNotReady','TimeoutError','ModuleNotFoundError','ImportError','TypeError','KeyError','OperationalError','RuntimeError')
 import re
 frames=[{'file':Path(p).name,'line':int(line),'function':func} for p,line,func in re.findall(r'File "([^"]+\.py)", line (\d+), in ([A-Za-z_][A-Za-z_0-9]*)',log)][-8:]
 return {'traceback_locations':frames,'unexpected_min_qty_keyword':"unexpected keyword argument 'min_qty'" in log,'exception_types':[n for n in names if n in log], 'stale_export':'full export is too old' in log, 'missing_cache':'bootstrap required' in log or 'cache needs explicit bootstrap' in log, 'row_limit':'ROW_LIMIT' in log or 'history exceeds' in log}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
 if os.geteuid()!=0:raise SystemExit('Run staging with sudo.')
 user=pwd.getpwnam('ubuntu');baseline=json.loads(zipfile.ZipFile(args.bundle).read('baseline.json'))
 report={'schema':'TORNFREN_CANDIDATE_STAGE_V1','public_commit':'__SOURCE_COMMIT__','production_modified':False,'services_modified':False,'cohorts':{},'errors':[]}
 try:
  units=subprocess.run(['systemctl','list-unit-files','torn-fren*.service','--no-legend','--no-pager'],capture_output=True,text=True,check=True,timeout=10)
  report['bot_units']=[]
  for line in units.stdout.splitlines():
   fields=line.split()
   if not fields or not fields[0].startswith('torn-fren') or not fields[0].endswith('.service'):continue
   info=props(fields[0])
   if '/opt/torn-fren/run.py' in info.get('ExecStart',''):
    report['bot_units'].append({'unit':fields[0],'active_state':info.get('ActiveState'),'working_directory':info.get('WorkingDirectory')})
 except (subprocess.SubprocessError,OSError):report['bot_discovery']='UNAVAILABLE'
 with tempfile.TemporaryDirectory(prefix='torn-fren-candidate-',dir='/var/tmp') as td:
  root=Path(td);os.chmod(root,0o755);release=root/'release';release.mkdir()
  with zipfile.ZipFile(args.bundle) as z:
   for entry in z.infolist():
    if not entry.filename.startswith('release/'):continue
    rel=Path(entry.filename).relative_to('release')
    if '..' in rel.parts or rel.is_absolute():raise ValueError('UNSAFE_BUNDLE_PATH')
    path=release/rel
    if entry.is_dir():path.mkdir(parents=True,exist_ok=True);continue
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(entry))
   manifest=json.loads(z.read('manifest.json'))
  for name,sha in manifest.items():
   if digest(release/name)!=sha:raise ValueError('CANDIDATE_CHECKSUM_MISMATCH')
  # Validate current release source digests before executing any candidate code.
  for label,(family,suffix,count) in COHORTS.items():
   unit='torn-fren-'+family+'.service';p=props(unit);expected=baseline['units'][unit]
   if p.get('User')!='ubuntu' or p.get('WorkingDirectory')!=expected['WorkingDirectory']:raise ValueError('LIVE_UNIT_DRIFT')
   for name,sha in baseline['sources'][family]['sha256'].items():
    file=Path(p['WorkingDirectory'])/name
    if sha and (not file.is_file() or digest(file)!=sha):raise ValueError('LIVE_SOURCE_DRIFT')
  # Native predictor source must remain readable to ubuntu, not writable by it.
  for path in release.rglob('*'):
   if path.is_file():os.chmod(path,0o644)
   elif path.is_dir():os.chmod(path,0o755)
  for label,(family,suffix,count) in COHORTS.items():
   print(json.dumps({'status':'STAGING_PUBLISHER','cohort':label}),flush=True)
   live_state=Path(BASE)/suffix;state=root/label;state.mkdir();os.chown(state,user.pw_uid,user.pw_gid)
   start=time.monotonic()
   try:
    unit='torn-fren-'+family+'.service';p=props(unit);tokens=launch_tokens(p['ExecStart']);model=option(tokens,'--model-sha')
    if model!=baseline['snapshots'][label]['model_sha']:raise ValueError('MODEL_IDENTITY_DRIFT')
    if option(tokens,'--state')!=str(live_state):raise ValueError('LIVE_STATE_ARGUMENT_DRIFT')
    if label!='incumbents' and option(tokens,'--collector')!=str(COLLECTOR):raise ValueError('LIVE_COLLECTOR_ARGUMENT_DRIFT')
    if label=='incumbents' and option(tokens,'--live-source')!=str(COLLECTOR):raise ValueError('LIVE_COLLECTOR_ARGUMENT_DRIFT')
    if ('--private-japan' in tokens)!=(label=='japan_private'):raise ValueError('PRIVATE_JAPAN_FLAG_DRIFT')
    source=Path(option(tokens,'--source',str(live_state/'stock_history.sqlite')))
    if label=='incumbents':source=Path(option(tokens,'--source'))
    allowed=(Path(BASE),Path('/var/lib/torn-fren-research'))
    if not any(source.resolve().is_relative_to(parent) for parent in allowed):raise ValueError('UNEXPECTED_SOURCE_PATH')
    staged_source=state/'stock_history.sqlite';sqlite_copy(source,staged_source);os.chown(staged_source,user.pw_uid,user.pw_gid)
    selector=live_state/'selector.json'
    if selector.exists():
     if selector.is_symlink() or selector.stat().st_size>8*1024*1024:raise ValueError('UNEXPECTED_SELECTOR_CACHE')
     (state/'selector.json').write_bytes(selector.read_bytes());os.chown(state/'selector.json',user.pw_uid,user.pw_gid);os.chmod(state/'selector.json',0o600)
    python=Path('/home/ubuntu/torn-fren-v38-probe/.venv/bin/python')
    if not python.is_file():raise ValueError('PUBLISHER_PYTHON_MISSING')
    if label=='incumbents':
     wrapper=Path('/var/lib/torn-fren-live-beta/reporting/a1862fdf7958559ab7e0/entry.py')
     if digest(wrapper)!=baseline['units'][unit]['entrypoint_files'][str(wrapper)]:raise ValueError('REPORTING_WRAPPER_DRIFT')
     cmd=[str(python),'-B',str(wrapper),'publish','--source',str(staged_source),'--state',str(state),'--model-sha',model,'--live-source',str(COLLECTOR),'--publisher-sha',option(tokens,'--publisher-sha',model)]
    elif label in ('final_pair','japan_private'):
     cmd=[str(python),'-B',str(release/'candidate_final_pair.py'),'--collector',str(COLLECTOR),'--state',str(state),'--source',str(staged_source),'--model-sha',model]
     if label=='japan_private':cmd.append('--private-japan')
    else:cmd=[str(python),'-B','-m','services.challenger_live' if label=='challengers' else 'services.next_six_live','--collector',str(COLLECTOR),'--state',str(state),'--source',str(staged_source),'--model-sha',model]
    env={k:v for k,v in os.environ.items() if not k.startswith(('TORN','PYTHON'))}
    env.update(HOME=user.pw_dir,USER='ubuntu',PYTHONPATH=str(release),PYTHONDONTWRITEBYTECODE='1',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',TORNFREN_REPLAY_PINNED_RESEARCH=str(root/'no-legacy-stage'))
    def demote():os.setgroups([]);os.setgid(user.pw_gid);os.setuid(user.pw_uid);os.nice(19)
    process=subprocess.Popen(cmd,cwd=release,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,preexec_fn=demote,start_new_session=True)
    try:
     stdout,stderr=process.communicate(timeout=155)
    except subprocess.TimeoutExpired:
     import signal
     os.killpg(process.pid,signal.SIGKILL);stdout,stderr=process.communicate();raise TimeoutError('STAGED_PUBLISHER_TIMEOUT')
    if process.returncode:
     report['cohorts'][label]={'status':'FAILED','exit_code':process.returncode,**sanitized_failure(stdout+'\n'+stderr)}
     continue
    snap=snapshot(state);now=int(time.time())
    if snap['items']!=count or snap['model_sha']!=model or not isinstance(snap['valid_until_epoch'],int) or snap['valid_until_epoch']<=now:raise ValueError('INVALID_STAGED_SNAPSHOT')
    report['cohorts'][label]={'status':'PASS','items':count,'elapsed_seconds':round(time.monotonic()-start,1),'model_identity_preserved':True,'production_state_used_for_writes':False}
   except Exception as exc:report['cohorts'][label]={'status':'FAILED','error_type':type(exc).__name__,'error_code':str(exc) if str(exc).isupper() and len(str(exc))<80 else 'CANDIDATE_EXCEPTION'}
   finally:shutil.rmtree(state)
  report['status']='CANDIDATE_STAGE_PASSED' if len(report['cohorts'])==5 and all(v['status']=='PASS' for v in report['cohorts'].values()) else 'CANDIDATE_STAGE_FAILED'
  report['native_model_code_executed']=True
 args.report.write_text(json.dumps(report,indent=2));os.chmod(args.report,0o644)
 print(json.dumps(report),flush=True)
if __name__=='__main__':main()
