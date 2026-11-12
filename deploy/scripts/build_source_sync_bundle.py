"""Build a reproducible source capsule from pinned public/private Git sources."""
import argparse,hashlib,json,re,subprocess,zipfile
from pathlib import Path
PRIVATE_BLOBS={'services/final_pair_live.py':'d2b407701115bcfb4cb8429a5acb8432fa11e336','services/checkpoint4_state.py':'4a42cb7de55f034113369542ea805087cf00efdc','services/daily_forward_report.py':'141687ad2c02492bda1cf59a03139a34fcb6e729','research/remaining_three_policy.py':'662c38c23e7dcaf008dde673fa8af6cd3c30c015'}
def build(checkout,commit,overlay,baseline,output):
 if not re.fullmatch('[0-9a-f]{40}',commit):raise ValueError('PINNED_COMMIT_REQUIRED')
 names=subprocess.check_output(['git','-C',str(checkout),'ls-tree','-r','--name-only',commit],text=True).splitlines()
 files={n:subprocess.check_output(['git','-C',str(checkout),'show',commit+':'+n]) for n in names}
 for name,expected in PRIVATE_BLOBS.items():
  value=(overlay/name).read_bytes();blob=hashlib.sha1(b'blob '+str(len(value)).encode()+b'\0'+value).hexdigest()
  if blob!=expected:raise ValueError('PRIVATE_OVERLAY_BLOB_MISMATCH')
  files[name]=value
 reader=hashlib.sha256(files['research/v128_full24_earliest_shadow.py']).hexdigest()
 entry=files['deploy/scripts/source_sync_final_pair_entry.py'].replace(b'__READER_SHA__',reader.encode())
 files['candidate_final_pair.py']=entry
 stage=files['deploy/scripts/source_sync_candidate_stage.py'].replace(b'__SOURCE_COMMIT__',commit.encode())
 manifest={n:hashlib.sha256(v).hexdigest() for n,v in files.items()}
 with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
  for name,value in files.items():z.writestr('release/'+name,value)
  z.writestr('manifest.json',json.dumps(manifest,sort_keys=True));z.writestr('baseline.json',baseline.read_bytes());z.writestr('stage.py',stage)
 return {'source_commit':commit,'files':len(files),'bundle_sha256':hashlib.sha256(output.read_bytes()).hexdigest()}
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--checkout',type=Path,required=True);p.add_argument('--commit',required=True);p.add_argument('--overlay',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(build(a.checkout,a.commit,a.overlay,a.baseline,a.output)))
if __name__=='__main__':main()
