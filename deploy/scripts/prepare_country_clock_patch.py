"""Prepare, but never apply, a minimal clock patch against actual host code.

AST positions select imports and the two existing transaction blocks. No
collector imports or execution. No changed timestamp or stock-delta logic.
The minimal patch leaves export_epoch explicitly missing, since that value
is not passed to the existing save function. Country update/receipt clocks
are still recorded on unchanged polls.
"""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path


def digest(raw):return hashlib.sha256(raw).hexdigest()


def prepare(source_path,helper_path,exporter_path):
    raw=Path(source_path).read_bytes()
    if len(raw)>2000000:raise ValueError('Collector code cap exceeded')
    source=raw.decode('utf-8');tree=ast.parse(source);lines=source.splitlines(keepends=True)
    if '\r' in source:raise ValueError('Non-LF collector source requires separate review')
    imports=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))]
    if not imports:raise ValueError('No unambiguous import block')
    if any(isinstance(n,ast.ImportFrom) and any(a.name=='country_freshness' for a in n.names) for n in imports):
        raise ValueError('Country clock import already present; inspect existing instrumentation')
    edits={imports[-1].end_lineno:['from services import country_freshness\n']}
    def function(name):
        candidates=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name]
        if len(candidates)!=1:raise ValueError('Ambiguous expected function '+name)
        return candidates[0]
    def connection(fn):
        found=[]
        for n in ast.walk(fn):
            if isinstance(n,ast.With):
                for item in n.items:
                    if (isinstance(item.context_expr,ast.Call) and isinstance(item.context_expr.func,ast.Name)
                            and item.context_expr.func.id=='_connect' and isinstance(item.optional_vars,ast.Name)
                            and item.optional_vars.id=='conn'):found.append(n)
        if len(found)!=1:raise ValueError('Ambiguous existing DB transaction in '+fn.name)
        return found[0]
    init=connection(function('init_db'));save=function('save_snapshot_from_export');txn=connection(save)
    args={a.arg for a in save.args.args+save.args.kwonlyargs}
    if not {'country','country_data','source'}<=args:raise ValueError('Unsupported save function signature')
    assigned=[n for n in ast.walk(save) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='timestamp' for t in n.targets) and n.lineno<txn.lineno]
    if len(assigned)!=1:raise ValueError('Expected receipt timestamp before transaction')
    if any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name)
            and n.func.value.id=='country_freshness' for n in ast.walk(tree)):
        raise ValueError('Existing clock calls require separate review')
    def insert_before(node,statements):
        position=node.body[0].lineno-1
        line=lines[position];indent=line[:len(line)-len(line.lstrip())]
        edits.setdefault(position,[]).extend(indent+s+'\n' for s in statements)
    insert_before(init,["for country_clock_statement in country_freshness.DDL.split(';'):",
                        '    if country_clock_statement.strip():',
                        '        conn.execute(country_clock_statement)'])
    insert_before(txn,['country_freshness.record(conn,country,country_data,source,timestamp)'])
    out=[]
    for i in range(len(lines)+1):
        out.extend(edits.get(i,[]))
        if i<len(lines):out.append(lines[i])
    modified=''.join(out)
    ast.parse(modified);compile(modified,'<prepared-country-clock-collector>','exec')
    diff=''.join(difflib.unified_diff(lines,modified.splitlines(keepends=True),
        fromfile='a/services/history_service.py',tofile='b/services/history_service.py',n=0))
    helper=Path(helper_path).read_bytes();exporter=Path(exporter_path).read_bytes()
    ast.parse(helper);ast.parse(exporter)
    manifest=dict(kind='PREPARED_COUNTRY_CLOCK_PATCH_NOT_APPLIED',base_history_sha256=digest(raw),
        proposed_history_sha256=digest(modified.encode()),patch_sha256=digest(diff.encode()),
        helper_sha256=digest(helper),exporter_sha256=digest(exporter),
        country_update_and_receipt_logged=True,export_epoch_forwarded=False,zero_context_patch=True,
        stock_delta_logic_changed=False,prediction_model_changed=False,production_modified=False,
        limitation='Exact base hash must match before applying with --unidiff-zero; patch contains additions only and no original host code context. AST/syntax checks only; host apply-check and isolated behavioral tests are separate. Country clocks do not certify item/game freshness. Export clock remains explicitly MISSING.')
    return diff,manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True);p.add_argument('--helper',required=True);p.add_argument('--exporter',required=True)
    p.add_argument('--output-dir',required=True)
    a=p.parse_args();out=Path(a.output_dir);out.mkdir(parents=True,exist_ok=True)
    diff,manifest=prepare(a.source,a.helper,a.exporter)
    (out/'country-clock-host.patch').write_text(diff)
    (out/'country-clock-host-manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print(json.dumps(manifest,sort_keys=True))


if __name__=='__main__':main()
