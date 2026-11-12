#!/usr/bin/env python3
"""Guarded versioned-source deployment. Keeps state, databases and old releases."""
import argparse,fcntl,hashlib,json,os,pwd,re,shlex,signal,sqlite3,subprocess,tempfile,time,urllib.request,zipfile
from pathlib import Path
from contextlib import closing

COMMIT='__SOURCE_COMMIT__'
BUNDLE_SHA='__BUNDLE_SHA__'
PUBLIC_MAIN='__MAIN_SHA__'
ROOT=Path('/var/lib/torn-fren-live-beta/releases')
OPS=Path('/var/backups/torn-fren-ops')
DROP='zz-github-source-sync.conf'
SYSTEMD=Path('/etc/systemd/system')
WEBROOT=Path('/opt/torn-fren')
COHORTS={'incumbents':('first-ten-beta','',10),'challengers':('challengers-beta','challengers',6),'next_six':('next-six-beta','next-six',6),'final_pair':('final-pair-beta','final-pair',2),'japan_private':('japan-private','japan-private',1)}
PRIVATE=('services/final_pair_live.py','services/checkpoint4_state.py','services/daily_forward_report.py','research/remaining_three_policy.py','candidate_final_pair.py')
LONG=('web','poller','bot');WORKERS=('routine-audit','gap-recovery')


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def command(argv,timeout=180):return subprocess.run(argv,capture_output=True,text=True,check=True,timeout=timeout)
def system(*args):return command(['systemctl',*args])
def properties(unit):
 p=command(['systemctl','show',unit,'-p','ExecStart','-p','WorkingDirectory','-p','User','-p','ActiveState','-p','SubState','-p','MainPID','-p','LoadState'])
 return dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
def tokens(raw):
 m=re.search(r'argv\[\]=(.*?) ; ignore_errors=',raw)
 if not m:raise ValueError('UNRECOGNIZED_EXEC_FORMAT')
 return shlex.split(m.group(1))
def option(args,key,default=None):return args[args.index(key)+1] if key in args and args.index(key)+1<len(args) else default
def replace(args,key,value):
 a=list(args)
 if key in a:a[a.index(key)+1]=str(value)
 else:a.extend([key,str(value)])
 return a
def atomic(path,data,mode=0o644):
 path=Path(path)
 if path.is_symlink():raise ValueError('SYMLINKED_OUTPUT')
 fd,tmp=tempfile.mkstemp(prefix='.'+path.name+'-',dir=path.parent)
 try:
  with os.fdopen(fd,'wb') as f:os.fchmod(f.fileno(),mode);f.write(data);f.flush();os.fsync(f.fileno())
  os.replace(tmp,path)
 finally:Path(tmp).unlink(missing_ok=True)
def fetch(route,port=8000):
 with urllib.request.urlopen('http://127.0.0.1:'+str(port)+route,timeout=30) as r:
  if r.status!=200:raise ValueError('HTTP_VERIFICATION_FAILED')
  return r.read(8*1024*1024)
def snap(label):
 s=json.loads((Path('/var/lib/torn-fren-live-beta')/COHORTS[label][1]/'latest.json').read_text())
 now=int(time.time());return {'published':s.get('published_epoch'),'valid_until':s.get('valid_until_epoch'),'items':len(s.get('items',{})),'model_sha':s.get('model_sha'),'valid':type(s.get('valid_until_epoch')) is int and s['valid_until_epoch']>now}
def healthy(label,model):
 s=snap(label)
 return s['valid'] and s['items']==COHORTS[label][2] and s['model_sha']==model

def wait_idle(units,timeout=190):
 deadline=time.monotonic()+timeout
 while any(properties(u).get('ActiveState') in ('activating','active','deactivating','reloading') for u in units):
  if time.monotonic()>deadline:raise TimeoutError('CURRENT_WORKER_DID_NOT_FINISH')
  time.sleep(2)
def drop_path(unit):return SYSTEMD/(unit+'.d')/DROP
def write_drop(unit,work,args):
 path=drop_path(unit);path.parent.mkdir(parents=True,exist_ok=True)
 if any('\n' in a or '\r' in a for a in args):raise ValueError('INVALID_LAUNCH_ARGUMENT')
 line=shlex.join(args).replace('%','%%')
 text=f'[Service]\nWorkingDirectory={work}\nEnvironment=PYTHONPATH={work}\nEnvironment=PYTHONDONTWRITEBYTECODE=1\nExecStart=\nExecStart={line}\n'
 atomic(path,text.encode())

def verify_web(manifest,port=8000,require_fresh=True):
 for name in ('beta.js','beta.css'):
  if hashlib.sha256(fetch('/first-release-assets/'+name,port)).hexdigest()!=manifest['web/first_release_assets/'+name]:raise ValueError('SERVED_ASSET_MISMATCH')
 for route in ('/','/experimental','/travel-decisions'):
  if b'/first-release-assets/beta.js' not in fetch(route,port):raise ValueError('WEB_PAGE_ASSET_MISSING')
 board=json.loads(fetch('/api/first-release',port))
 if len(board.get('rows',[]))!=24 or len({r.get('item_key') for r in board['rows']})!=24:raise ValueError('PUBLIC_ITEM_COUNT_MISMATCH')
 if require_fresh and (len(board.get('cohorts',{}))!=4 or any(c.get('status')!='LIVE_BETA' for c in board['cohorts'].values())):raise ValueError('PUBLIC_COHORT_NOT_FRESH')
 return {'public_items':24,'cohorts':{k:v['status'] for k,v in board['cohorts'].items()},'pages_verified':3}

def verify_services(plan):
 for unit in plan['long_units']:
  p=properties(unit)
  if p.get('ActiveState')!='active':raise ValueError('MAIN_SERVICE_NOT_ACTIVE')
 for unit,info in plan['units'].items():
  actual=properties(unit)
  if actual.get('WorkingDirectory')!=info['new_work']:raise ValueError('EFFECTIVE_SOURCE_PATH_MISMATCH')
  if tokens(actual['ExecStart'])!=info['new_args']:raise ValueError('EFFECTIVE_LAUNCH_MISMATCH')
 # Follow the original shared DB, not a newly initialized empty database.
 db=(Path(plan['public_root'])/'data'/'stock_history.db').resolve(strict=True)
 if str(db)!=plan['collector_realpath']:raise ValueError('COLLECTOR_TARGET_CHANGED')
 with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=3)) as con:
  con.execute('PRAGMA query_only=ON');last=con.execute("SELECT MAX(timestamp) FROM poll_heartbeats WHERE mode='poll-cycle' AND success=1").fetchone()[0]
  if type(last) is not int or not 0<=time.time()-last<=90:raise ValueError('COLLECTOR_NOT_FRESH')

def restore(backup):
 plan=json.loads((backup/'plan.json').read_text())
 for timer,active in plan['timers'].items():
  if active:system('stop',timer)
 wait_idle(plan['worker_units'],timeout=190)
 for unit in plan['units']:
  path=drop_path(unit);saved=backup/(unit+'.conf')
  if saved.exists():atomic(path,saved.read_bytes())
  else:path.unlink(missing_ok=True)
 system('daemon-reload')
 for unit in plan['long_units']:system('restart',unit)
 for timer,active in plan['timers'].items():
  if active:system('start',timer)
 for unit,info in plan['units'].items():
  p=properties(unit)
  if p.get('WorkingDirectory')!=info['old_work'] or tokens(p['ExecStart'])!=info['old_args']:raise ValueError('ROLLBACK_LAUNCH_VERIFICATION_FAILED')
 return {'status':'ORIGINAL_LAUNCHES_RESTORED','databases_restored_or_deleted':False,'ledgers_restored_or_deleted':False}

def smoke_web(public,manifest):
 import socket
 # Reuse the existing web environment internally; do not export its values.
 pid=properties('torn-fren-web.service').get('MainPID')
 env={}
 for item in Path('/proc',pid,'environ').read_bytes().split(b'\0'):
  key,sep,value=item.partition(b'=')
  if sep:env[key.decode()]=value.decode()
 for key in ('NOTIFY_SOCKET','LISTEN_FDS','LISTEN_PID','JOURNAL_STREAM'):env.pop(key,None)
 env.update(PYTHONPATH=str(public),PYTHONDONTWRITEBYTECODE='1')
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 user=pwd.getpwnam('ubuntu')
 def demote():os.setgroups([]);os.setgid(user.pw_gid);os.setuid(user.pw_uid)
 proc=subprocess.Popen(['/opt/torn-fren/venv/bin/python','-B','-m','uvicorn','web.app:app','--host','127.0.0.1','--port',str(port)],cwd=public,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,preexec_fn=demote,start_new_session=True)
 try:
  deadline=time.monotonic()+30
  while True:
   if proc.poll() is not None:raise ValueError('CANDIDATE_WEB_STARTUP_FAILED')
   try:verify_web(manifest,port,require_fresh=False);break
   except (OSError,ValueError):
    if time.monotonic()>deadline:raise TimeoutError('CANDIDATE_WEB_SMOKE_FAILED')
    time.sleep(1)
 finally:
  if proc.poll() is None:
   os.killpg(proc.pid,signal.SIGTERM)
   try:proc.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()


def extract(bundle,public,private):
 if public.exists() or private.exists():raise ValueError('CANDIDATE_DIRECTORY_ALREADY_EXISTS')
 with zipfile.ZipFile(bundle) as z:
  manifest=json.loads(z.read('manifest.json'));baseline=json.loads(z.read('baseline.json'))
  for root in (public,private):root.mkdir(mode=0o755)
  for name,digest in manifest.items():
   rel=Path(name)
   if rel.is_absolute() or '..' in rel.parts:raise ValueError('UNSAFE_CANDIDATE_PATH')
   data=z.read('release/'+name)
   if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('CANDIDATE_HASH_MISMATCH')
   for root in (public,private):
    if root==public and name in PRIVATE:continue
    target=root/rel;target.parent.mkdir(parents=True,exist_ok=True);atomic(target,data)
  for root in (public,private):
   # External configuration and shared runtime data remain at their existing paths.
   (root/'data').symlink_to(WEBROOT/'data',target_is_directory=True)
   (root/'.env').symlink_to(WEBROOT/'.env')
   atomic(root/'DEPLOYED_RELEASE.json',json.dumps({'source_commit':COMMIT,'github_main_merge_commit':PUBLIC_MAIN,'private_overlay':root==private,'training_or_stock_data_included':False},indent=2).encode())
 return manifest,baseline


def apply(bundle,report_path):
 if sha(bundle)!=BUNDLE_SHA:raise ValueError('CANDIDATE_BUNDLE_CHECKSUM_MISMATCH')
 ROOT.mkdir(parents=True,exist_ok=True);OPS.mkdir(parents=True,exist_ok=True)
 if ROOT.is_symlink() or OPS.is_symlink():raise ValueError('UNEXPECTED_DEPLOYMENT_ROOT')
 marker=OPS/('source-sync-'+COMMIT+'.json')
 if marker.exists():
  saved=json.loads(marker.read_text());raise ValueError('RELEASE_ALREADY_ATTEMPTED_USE_ITS_REPORT_OR_ROLLBACK')
 stamp=str(time.time_ns());public=ROOT/('github-'+COMMIT[:12]+'-'+stamp+'-public');private=ROOT/('github-'+COMMIT[:12]+'-'+stamp+'-private')
 manifest,baseline=extract(bundle,public,private)
 smoke_web(public,manifest)
 plan={'public_root':str(public),'private_root':str(private),'collector_realpath':str((WEBROOT/'data/stock_history.db').resolve(strict=True)),'units':{},'timers':{},'long_units':[],'worker_units':[]}
 # Effective source/config checks occur before any timer or running process is changed.
 all_names=(*LONG,*WORKERS,*(v[0] for v in COHORTS.values()))
 for name in all_names:
  unit='torn-fren-'+name+'.service';p=properties(unit)
  if p.get('LoadState')!='loaded' or p.get('User')!='ubuntu':raise ValueError('UNEXPECTED_SERVICE_IDENTITY')
  old_args=tokens(p['ExecStart']);old_work=p.get('WorkingDirectory')
  if name in LONG and p.get('ActiveState')!='active':raise ValueError('MAIN_SERVICE_NOT_RUNNING')
  if name in (*LONG,*WORKERS):
   if old_work!='/opt/torn-fren':raise ValueError('WEB_ROOT_DRIFT')
  elif old_work!=baseline['units'][unit]['WorkingDirectory']:raise ValueError('PUBLISHER_ROOT_DRIFT')
  work=private if name in ('final-pair-beta','japan-private') else public
  args=list(old_args)
  if name=='final-pair-beta':
   old_wrapper=Path('/usr/local/lib/torn-fren-publisher-recovery/final_pair_entry.py')
   if sha(old_wrapper)!=baseline['recovery_wrappers']['final_pair_entry.py']:raise ValueError('FINAL_PAIR_WRAPPER_DRIFT')
   if str(old_wrapper) not in args:raise ValueError('FINAL_PAIR_WRAPPER_NOT_ACTIVE')
   args[args.index(str(old_wrapper))]=str(private/'candidate_final_pair.py')
  elif name in LONG:
   args=[str(public/a[len('/opt/torn-fren/'):]) if a.startswith('/opt/torn-fren/') and a.endswith('.py') else a for a in args]
  for label,(family,suffix,count) in COHORTS.items():
   if family!=name:continue
   if option(old_args,'--state')!=str(Path('/var/lib/torn-fren-live-beta')/suffix):raise ValueError('LIVE_STATE_PATH_DRIFT')
   if option(old_args,'--model-sha')!=baseline['snapshots'][label]['model_sha']:raise ValueError('MODEL_IDENTITY_DRIFT')
   if ('--private-japan' in args)!=(name=='japan-private'):raise ValueError('PRIVATE_MODE_FLAG_DRIFT')
  if name not in (*LONG,*WORKERS) and properties('torn-fren-'+name+'.timer').get('ActiveState')!='active':raise ValueError('PUBLISHER_TIMER_INACTIVE')
  plan['units'][unit]={'old_work':old_work,'old_args':old_args,'new_work':str(work),'new_args':args}
  if name in LONG:plan['long_units'].append(unit)
  else:
   plan['worker_units'].append(unit);timer='torn-fren-'+name+'.timer';t=properties(timer);plan['timers'][timer]=t.get('ActiveState')=='active'
 # Match captured live critical source hashes, preserving external reporting code.
 for label,info in baseline['sources'].items():
  if label not in ('web','first-ten-beta','challengers-beta','next-six-beta','final-pair-beta'):continue
  for name,digest in info['sha256'].items():
   if digest and sha(Path(info['root'])/name)!=digest:raise ValueError('LIVE_SOURCE_DRIFT')
 first=Path('/var/lib/torn-fren-live-beta/reporting/a1862fdf7958559ab7e0/entry.py')
 if sha(first)!=baseline['units']['torn-fren-first-ten-beta.service']['entrypoint_files'][str(first)]:raise ValueError('FIRST_TEN_REPORTING_WRAPPER_DRIFT')
 backup=Path(tempfile.mkdtemp(prefix='source-sync-',dir=OPS));os.chmod(backup,0o700)
 atomic(backup/'plan.json',json.dumps(plan,indent=2).encode(),0o600)
 for unit in plan['units']:
  p=drop_path(unit)
  if p.is_symlink():raise ValueError('SYMLINKED_SERVICE_DROPIN')
  if p.exists():atomic(backup/(unit+'.conf'),p.read_bytes(),0o600)
 atomic(backup/'installer.py',Path(__file__).read_bytes(),0o700)
 result={'schema':'TORNFREN_SOURCE_SYNC_DEPLOY_V1','source_commit':COMMIT,'github_main_merge_commit':PUBLIC_MAIN,'backup':str(backup),'rollback_command':f'sudo python3 {backup}/installer.py --rollback {backup}','databases_deleted':False,'forecast_records_deleted':False,'model_identities_preserved':True,'old_releases_deleted':False}
 changed=False
 result['status']='CUTOVER_PREPARED'
 atomic(marker,json.dumps(result,indent=2).encode(),0o600)
 atomic(report_path,json.dumps(result,indent=2).encode(),0o644)
 print(json.dumps({'status':'ROLLBACK_PREPARED','backup':str(backup),'rollback_command':result['rollback_command']}),flush=True)
 try:
  print(json.dumps({'status':'PAUSING_SCHEDULES_AND_WAITING_FOR_CURRENT_WORKERS'}),flush=True)
  changed=True
  for timer,active in plan['timers'].items():
   if active:system('stop',timer)
  wait_idle(plan['worker_units'])
  for unit,info in plan['units'].items():write_drop(unit,info['new_work'],info['new_args'])
  system('daemon-reload')
  # Fail on unexpected override precedence before restarting the collector/web/bot.
  for unit,info in plan['units'].items():
   p=properties(unit)
   if p.get('WorkingDirectory')!=info['new_work'] or tokens(p['ExecStart'])!=info['new_args']:raise ValueError('DROPIN_NOT_EFFECTIVE')
  for name in ('poller','web','bot'):system('restart','torn-fren-'+name+'.service')
  time.sleep(3)
  manual={}
  for label,(family,suffix,count) in COHORTS.items():
   print(json.dumps({'status':'PUBLISHING_LIVE_COHORT','cohort':label}),flush=True)
   system('start','torn-fren-'+family+'.service')
   if not healthy(label,baseline['snapshots'][label]['model_sha']):raise ValueError('LIVE_SNAPSHOT_INVALID')
   manual[label]=snap(label)['published']
  verify_services(plan);verify_web(manifest,require_fresh=False)
  for timer,active in plan['timers'].items():
   if active:system('start',timer)
  print(json.dumps({'status':'VERIFYING_NEXT_SCHEDULED_PUBLICATIONS'}),flush=True)
  deadline=time.monotonic()+190;verified=set();last_notice=0
  while len(verified)<5:
   for label in COHORTS:
    model=baseline['snapshots'][label]['model_sha']
    if healthy(label,model) and snap(label)['published']>manual[label]:verified.add(label)
   if len(verified)==5:break
   if time.monotonic()>deadline:raise TimeoutError('NEXT_SCHEDULED_PUBLICATION_NOT_VERIFIED')
   if time.monotonic()-last_notice>20:
    print(json.dumps({'status':'SCHEDULED_PUBLICATIONS_VERIFIED','verified':sorted(verified)}),flush=True);last_notice=time.monotonic()
   time.sleep(5)
  verify_services(plan);result.update(verify_web(manifest));result.update(status='SOURCE_SYNC_DEPLOYMENT_VERIFIED',scheduled_publishers_verified=sorted(verified),public_root=str(public),private_root=str(private))
  atomic(marker,json.dumps(result,indent=2).encode(),0o600)
 except Exception as error:
  result.update(status='DEPLOYMENT_FAILED',error_type=type(error).__name__,error_code=str(error) if str(error).isupper() and len(str(error))<100 else 'CUTOVER_EXCEPTION')
  if changed:
   try:result['rollback']=restore(backup)
   except Exception as rollback_error:result['rollback']={'status':'ROLLBACK_NEEDS_ATTENTION','error_type':type(rollback_error).__name__}
  atomic(marker,json.dumps(result,indent=2).encode(),0o600)
 atomic(report_path,json.dumps(result,indent=2).encode(),0o644)
 print(json.dumps(result),flush=True)


def main():
 p=argparse.ArgumentParser();a=p.add_mutually_exclusive_group(required=True);a.add_argument('--apply',action='store_true');a.add_argument('--rollback',type=Path);p.add_argument('--bundle',type=Path);p.add_argument('--report',type=Path,default=Path('/home/ubuntu/TornFREN-Source-Sync-Deploy.json'));args=p.parse_args()
 if os.geteuid()!=0:raise SystemExit('Run with sudo.')
 OPS.mkdir(parents=True,exist_ok=True)
 fd=os.open(OPS/'.source-sync.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,'w') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if args.rollback:
   path=args.rollback.absolute()
   if path.parent!=OPS or path.is_symlink():raise ValueError('UNEXPECTED_ROLLBACK_PATH')
   print(json.dumps(restore(path)))
  else:
   if not args.bundle:raise ValueError('BUNDLE_REQUIRED')
   if sha(args.bundle)!=BUNDLE_SHA:raise ValueError('CANDIDATE_BUNDLE_CHECKSUM_MISMATCH')
   # Run the final candidate on disposable copies before touching live settings.
   with tempfile.TemporaryDirectory(prefix='torn-fren-predeploy-',dir='/var/tmp') as td:
    script=Path(td)/'stage.py';stage_report=Path(td)/'stage.json'
    with zipfile.ZipFile(args.bundle) as z:script.write_bytes(z.read('stage.py'))
    subprocess.run(['/usr/bin/python3',str(script),'--bundle',str(args.bundle),'--report',str(stage_report)],check=True,timeout=1000)
    proof=json.loads(stage_report.read_text())
    if proof.get('status')!='CANDIDATE_STAGE_PASSED' or proof.get('public_commit')!=COMMIT:
     atomic(args.report,json.dumps({'schema':'TORNFREN_SOURCE_SYNC_DEPLOY_V1','status':'PREDEPLOY_STAGE_FAILED','production_modified':False,'stage':proof},indent=2).encode())
     print(json.dumps({'status':'PREDEPLOY_STAGE_FAILED','production_modified':False}),flush=True)
     return
   apply(args.bundle,args.report)
if __name__=='__main__':main()
