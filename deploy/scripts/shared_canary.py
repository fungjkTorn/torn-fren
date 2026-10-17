"""Foreground, localhost-only canary. No installed services or collector writes."""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlsplit,urlencode
from urllib.request import build_opener,ProxyHandler,HTTPRedirectHandler

from services.travel_read_model import SnapshotCache,build_board
from services.experimental_shared_departures import rows_for_experimental
from deploy.scripts.prepare_shared_experimental_page import prepare_html

ROOT=Path(__file__).resolve().parents[2]
PROFILE='deploy/research_runner/flowers_plushies_tolerance30_candidate_20261016.json'
MAX_BYTES=2_000_000
FORBIDDEN_PORTS={8000,8001,8765}
ASSETS={'/shared_departure_preview.js','/shared_canary_graph_boot.js','/shared_experimental_rows.js'}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args):return None


def upstream(path):
    # Fixed localhost destination; no caller-controlled hosts or redirects.
    with build_opener(ProxyHandler({}),NoRedirect()).open('http://127.0.0.1:8000'+path,timeout=4) as r:
        content=r.read(MAX_BYTES+1)
        if r.status!=200 or len(content)>MAX_BYTES:raise ValueError('upstream unavailable')
        return content


def revision():
    sha=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    dirty=subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain','--untracked-files=no'],text=True)
    if dirty:raise ValueError('tracked canary code differs from pinned checkout')
    return sha


def validate_port(port):
    if type(port) is not int or not 1024<=port<=65535 or port in FORBIDDEN_PORTS:
        raise ValueError('choose a separate unprivileged canary port')


def run_publisher(source,state,sha):
    env=dict(os.environ,TORNFREN_REPLAY_WORK=str(ROOT),TORNFREN_REPLAY_PINNED_RESEARCH=str(ROOT/'research'),
             OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
    started=time.monotonic()
    completed=subprocess.run([sys.executable,'-m','research.build_travel_event_snapshot',
        '--source',str(source),'--model-sha',sha,'--assignments',str(ROOT/PROFILE),
        '--output',str(state/'shared.json')],cwd=ROOT,env=env,capture_output=True,text=True,timeout=25)
    if completed.returncode:
        last=completed.stderr.strip().splitlines()
        raise RuntimeError('publisher failed: '+(last[-1][:200] if last else 'no diagnostic'))
    return time.monotonic()-started


class Canary:
    def __init__(self,state,sha,*,fetch=upstream):
        if not re.fullmatch('[0-9a-f]{40}',sha):raise ValueError('exact source SHA required')
        self.state=Path(state);self.sha=sha;self.fetch=fetch;self.cache=SnapshotCache()
        self.assignments=json.loads((ROOT/PROFILE).read_text())
        self.experimental=prepare_html(fetch('/experimental')).encode()
        # Validate upstream shape before any listener starts.
        self.root_html()
        self.last_publish='NOT_STARTED'

    def root_html(self):
        page=self.fetch('/').decode('utf8')
        if page.count('</head>')!=1 or page.count('<body>')!=1:raise ValueError('upstream graph HTML changed')
        if '/shared_departure_preview.js' not in page:
            page=page.replace('</head>','<script src="/shared_departure_preview.js"></script><script src="/shared_canary_graph_boot.js"></script></head>')
        banner='<aside style="padding:12px;background:#283a25;color:#e4f4dd">PRIVATE CANARY · Research estimates; reconfirm before travel. Existing website remains separate.</aside>'
        panel='' if 'id="sharedDeparturePreview"' in page else '<div id="sharedDeparturePreview" hidden role="status" style="padding:12px;color:#b8ef76"></div>'
        return page.replace('<body>','<body>'+banner+panel).encode()

    def board(self,now,overrides=None):
        snapshot=self.cache.read(self.state/'shared.json')
        if snapshot.get('model_sha')!=self.sha or snapshot.get('item_assignments')!=self.assignments:
            raise ValueError('snapshot source or assignments differ from canary pin')
        if set(snapshot.get('items',{}))!=set(self.assignments):raise ValueError('snapshot roster mismatch')
        return build_board(snapshot,now=now,flight_overrides=overrides)

    def health(self,now):
        try:
            board=self.board(now)
            age=board['source_poll_age_seconds']
            fresh=type(age) is int and 0<=age<=180 and 0<=now-board['asof_epoch']<300
            return (200 if fresh else 503),{'status':'PRIVATE_CANARY_READY' if fresh else 'STALE_SHARED_FEED',
                'source_sha':self.sha,'item_count':board['item_count'],'source_poll_age_seconds':age,
                'last_publish':self.last_publish,'accuracy_verified':False,'listener':'127.0.0.1'}
        except (OSError,ValueError,TypeError,KeyError):
            return 503,{'status':'SHARED_FEED_UNAVAILABLE','accuracy_verified':False}

    def route(self,target,now):
        url=urlsplit(target)
        if url.scheme or url.netloc:raise ValueError('absolute request targets are not supported')
        query=parse_qs(url.query,keep_blank_values=True)
        if len(target)>2048 or any(len(v)!=1 for v in query.values()):raise ValueError('invalid query')
        p={k:v[0] for k,v in query.items()};path=url.path
        if path=='/health':
            status,data=self.health(now);return status,'application/json',json.dumps(data).encode()
        if path=='/':return 200,'text/html',self.root_html()
        if path=='/experimental':return 200,'text/html',self.experimental
        if path=='/travel-decisions':return 200,'text/html',(ROOT/'web/travel_decisions.html').read_bytes()
        if path in ASSETS:return 200,'text/javascript',(ROOT/'web/static'/path[1:]).read_bytes()
        if path=='/champion_graph.js':return 200,'text/javascript',self.fetch(path)
        if path=='/api/catalog':return 200,'application/json',self.fetch(path)
        if path in ('/api/travel-decisions','/api/experimental/v41/predictions'):
            allowed={'country','flight_seconds'} if path=='/api/travel-decisions' else {'country','item'}
            if set(p)-allowed:raise ValueError('unsupported selector')
            country=p.get('country');partner=p.get('flight_seconds') if 'travel-decisions' in path else p.get('item')
            if bool(country)!=bool(partner):raise ValueError('paired selectors required')
            if country and (len(country)!=3 or len(partner)>120):raise ValueError('invalid selector')
            overrides=None
            if 'flight_seconds' in p:
                seconds=int(p['flight_seconds'])
                if not 60<=seconds<=86400:raise ValueError('invalid flight')
                overrides={country:seconds}
            board=self.board(now,overrides)
            if country and not any(r['country']==country for r in board['rows']):raise ValueError('unknown country')
            data=board
            if 'experimental' in path:
                rows=rows_for_experimental(board,now=now)
                if country:rows=[r for r in rows if r['item_key']==country+':'+partner]
                data={'latest':rows,'shared_departure_overlay':True,'prediction_accuracy_verified':False}
            return 200,'application/json',json.dumps(data).encode()
        if path=='/api/history':
            if set(p)-{'country','item','minutes','legacy_v2'}:raise ValueError('unsupported history parameter')
            if len(p.get('country',''))!=3 or not 1<=len(p.get('item',''))<=120:raise ValueError('invalid history selector')
            if not 1<=int(p.get('minutes','1440'))<=10080:raise ValueError('invalid history range')
            if p.get('legacy_v2','true') not in ('true','false'):raise ValueError('invalid history mode')
            data=json.loads(self.fetch(path+'?'+urlencode(p)))
            try:
                board=self.board(now);key=p['country']+':'+p['item']
                preview={**{k:board[k] for k in ('asof_epoch','evaluated_at_epoch','source_poll_age_seconds')},
                    'row':next((r for r in board['rows'] if r['item_key']==key),None)}
            except (OSError,ValueError,TypeError,KeyError):preview={'row':None,'status':'SHARED_FEED_UNAVAILABLE'}
            data.setdefault('analysis',{})['shared_departure_preview']=preview
            return 200,'application/json',json.dumps(data).encode()
        return 404,'application/json',b'{"detail":"Canary route unavailable"}'


def producer(app,source,stop,initial_delay=0):
    if stop.wait(initial_delay):return
    while not stop.is_set():
        started=time.monotonic()
        try:
            elapsed=run_publisher(source,app.state,app.sha)
            app.last_publish='PUBLISHED';print('CANARY_PUBLISHED',round(elapsed,2),'seconds',flush=True)
        except (OSError,RuntimeError,subprocess.TimeoutExpired):
            app.last_publish='PUBLISH_FAILED';print('CANARY_PUBLISH_FAILED',flush=True)
        stop.wait(max(5,20-(time.monotonic()-started)))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True);p.add_argument('--state',required=True)
    p.add_argument('--model-sha',required=True);p.add_argument('--port',type=int,default=8770)
    p.add_argument('--preflight-only',action='store_true');a=p.parse_args()
    validate_port(a.port)
    if revision()!=a.model_sha:raise ValueError('checkout does not match requested SHA')
    source=Path(a.source).resolve(strict=True);state=Path(a.state).resolve()
    if state==ROOT or source.is_relative_to(state):raise ValueError('separate canary state directory required')
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        probe.bind(('127.0.0.1',a.port))
    os.umask(0o077)
    marker={'model_sha':a.model_sha,'source':str(source),'purpose':'TORN_FREN_PRIVATE_CANARY'}
    if state.exists() and any(state.iterdir()):
        if not (state/'canary.json').is_file() or json.loads((state/'canary.json').read_text())!=marker:
            raise ValueError('state directory belongs to a different task')
    state.mkdir(mode=0o700,parents=True,exist_ok=True)
    (state/'canary.json').write_text(json.dumps(marker,sort_keys=True))
    app=Canary(state,a.model_sha)
    elapsed=run_publisher(source,state,a.model_sha)
    if elapsed>20:raise RuntimeError('initial build exceeds private canary latency budget')
    app.last_publish='PUBLISHED';status,health=app.health(int(time.time()))
    print(json.dumps(dict(health,build_seconds=elapsed,port=a.port),sort_keys=True),flush=True)
    if status!=200:raise RuntimeError('fresh canary preflight failed')
    if a.preflight_only:return
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:status,kind,body=app.route(self.path,int(time.time()))
            except ValueError:status,kind,body=400,'application/json',b'{"detail":"Invalid canary request"}'
            except (OSError,TypeError,KeyError):status,kind,body=503,'application/json',b'{"detail":"Canary source unavailable"}'
            self.send_response(status);self.send_header('Content-Type',kind+'; charset=utf-8')
            self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    stop=threading.Event()
    with ThreadingHTTPServer(('127.0.0.1',a.port),Handler) as server:
        threading.Thread(target=producer,args=(app,source,stop,max(0,20-elapsed)),daemon=True).start()
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:stop.set()


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
        print(json.dumps({'status':'CANARY_PREFLIGHT_FAILED','error':str(error)[:300]}),file=sys.stderr)
        raise SystemExit(1)
