"""Read-only diagnostic bundle of planner forecasts and stock observations.

Standalone over SSH; the reviewed stock exporter is supplied as source text.
No service changes, inference, cleanup or edits to original databases.
"""
import argparse
import base64
from contextlib import closing
import json
import os
from pathlib import Path
import pwd
import sqlite3
import tempfile
import zipfile

ITEMS=('arg:Ceibo Flower','can:Crocus','cay:Banana Orchid','haw:Orchid',
       'jap:Cherry Blossom','mex:Dahlia','mex:Jaguar Plushie','swi:Edelweiss',
       'uae:Tribulus Omanense','uni:Heather')


def bundle(ledger,collector,output,stock_export_source,owner=None):
    ledger=Path(ledger).resolve(strict=True);collector=Path(collector).resolve(strict=True)
    output=Path(output)
    if output.exists() or output.is_symlink():raise ValueError('choose a new output filename')
    with tempfile.TemporaryDirectory(prefix='.planner-diagnostics-',dir=output.parent) as td:
        work=Path(td);copy=work/'forecasts.sqlite'
        with closing(sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True)) as src, closing(sqlite3.connect(copy)) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('ledger integrity check failed')
            observed_items={r[0] for r in dst.execute('SELECT DISTINCT item FROM issues')}
            if not set(ITEMS)<=observed_items:raise ValueError('active planner items missing from ledger')
            issues=dst.execute('SELECT COUNT(*),MIN(issued),MAX(issued) FROM issues').fetchone()
        space={'__name__':'stock_export_for_planner'}
        exec(compile(stock_export_source,'reviewed_stock_export.py','exec'),space)
        space['ITEMS']=ITEMS
        stock=space['export'](collector,work/'stock_history.sqlite',days=120)
        manifest={'schema':'planner-evidence-diagnostics-v1','service_changes':False,
                  'collector_modified':False,'ledger_modified':False,'model_inference_run':False,
                  'items':list(ITEMS),'forecast_rows':issues[0],'first_issued':issues[1],
                  'last_issued':issues[2],'stock_export':stock}
        # Do not expose temporary server paths as downloadable artifact paths.
        manifest['stock_export'].pop('output',None)
        (work/'manifest.json').write_text(json.dumps(manifest,indent=2))
        archive=work/'evidence.zip'
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
            for name in ('forecasts.sqlite','stock_history.sqlite','manifest.json'):z.write(work/name,name)
        os.chmod(archive,0o600)
        if owner:
            user=pwd.getpwnam(owner);os.chown(archive,user.pw_uid,user.pw_gid)
        os.link(archive,output)
        return dict(manifest,status='PLANNER_DIAGNOSTICS_READY',output=str(output),bytes=output.stat().st_size)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ledger',required=True);p.add_argument('--collector',required=True)
    p.add_argument('--output',required=True);p.add_argument('--owner')
    a=p.parse_args()
    stock_source=base64.b64decode(STOCK_EXPORT_SOURCE_B64,validate=True).decode('utf-8')
    print(json.dumps(bundle(a.ledger,a.collector,a.output,stock_source,a.owner),indent=2))
