"""Read-only localhost product audit; never reads collector files or secrets.

HTTP success proves route reachability, not prediction correctness. Responses
stay in memory; the report retains only hashes, counts and status diagnostics.
"""
import hashlib
import json
from collections import Counter
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, build_opener

from deploy.scripts.v163_readonly_event_first_preview import exact_roster

ROUTES = ('/', '/experimental', '/api/experimental/v41/predictions',
          '/travel-decisions', '/api/travel-decisions')
MAX_BYTES = 2_000_000


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def summarize(path, status, content, expected):
    out = {'http_status': status, 'bytes': len(content)}
    if status != 200:
        return out
    if not path.startswith('/api/'):
        out['html_sha256'] = hashlib.sha256(content).hexdigest()
        return out
    try:
        data = json.loads(content)
    except (ValueError, UnicodeError):
        return dict(out, error='INVALID_JSON')
    rows = (data.get('latest') if 'experimental' in path else data.get('rows')) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return dict(out, error='UNKNOWN_RESPONSE_SHAPE')
    keys = [r.get('item_key') for r in rows if isinstance(r, dict)]
    known = {k for k in keys if isinstance(k, str)}
    out.update(row_count=len(rows), unique_item_count=len(known),
               missing_configured_items=sorted(expected-known),
               unexpected_item_count=len(known-expected),
               duplicate_item_keys=sorted(k for k, n in Counter(k for k in keys if isinstance(k,str)).items() if n>1),
               status_counts=dict(Counter(str(r.get('status', r.get('decision',{}).get('status','UNKNOWN')))
                                          for r in rows if isinstance(r,dict))))
    return out


def audit(*, fetch=None, requested_count=28):
    expected = set(exact_roster())
    if type(requested_count) is not int or not len(expected) <= requested_count <= 250:
        raise ValueError('invalid requested item count')
    if fetch is None:
        opener = build_opener(NoRedirect)
        def fetch(path):
            with opener.open('http://127.0.0.1:8000'+path, timeout=4) as response:
                return response.status, response.read(MAX_BYTES+1)
    routes = {}
    for path in ROUTES:
        try:
            status, content = fetch(path)
            routes[path] = ({'error':'RESPONSE_TOO_LARGE'} if len(content)>MAX_BYTES else
                            summarize(path,status,content,expected))
        except HTTPError as error:
            routes[path] = {'http_status':error.code}
        except (URLError, TimeoutError, OSError):
            routes[path] = {'http_status':None,'error':'UNREACHABLE'}
    return {'status':'READ_ONLY_PRODUCT_RUNTIME_AUDIT', 'routes':routes,
            'requested_item_count':requested_count,'configured_item_count':len(expected),
            'additional_item_identities_required':max(0,requested_count-len(expected)),
            'accuracy_verified':False,'deployment_performed':False,
            'warning':'HTTP reachability and row counts do not establish fresh data or accurate recommendations.'}


if __name__ == '__main__':
    print(json.dumps(audit(),sort_keys=True))
