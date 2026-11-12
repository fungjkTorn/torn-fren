"""Conservative Torn-FREN Python reachability inventory; NEVER deletes files.

Static imports alone cannot prove an old model is unused: scheduled systemd
units, CLI entry points, importlib, website assets, private releases, rollback
scripts, and operator workflows all count as possible roots. This tool reports
review candidates only, never an archival authorization.
"""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict, deque
import json
from pathlib import Path
import re

SEEDS = ('run', 'poller', 'web.app', 'services.first_release_live',
         'services.next_six_live', 'services.durable_audit_queue_v39',
         'bot.main')
IGNORE_DIRS = {'.git', '.venv', 'venv', '__pycache__', 'data', 'node_modules',
               'backups', 'archive', 'historical_pc_data'}
SERVICE_EXTENSIONS = {'.service', '.timer'}
REFERENCING_EXTENSIONS = {'.py', '.sh', '.ps1', '.service', '.timer', '.html', '.js'}


def modules(root):
    out = {}
    for path in root.rglob('*.py'):
        rel = path.relative_to(root)
        if any(part in IGNORE_DIRS for part in rel.parts):
            continue
        parts = rel.with_suffix('').parts
        mod = '.'.join(parts[:-1]) if parts[-1] == '__init__' else '.'.join(parts)
        if mod:
            out[mod] = path
    return out


def imported_modules(path, current, known):
    """Resolve only static imports; intentionally under-approximate dynamics."""
    try:
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeError, SyntaxError):
        return set(), True
    found = set()
    uncertain = False
    package = current.split('.')[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in known:
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[:max(0, len(package) - node.level + 1)]
                stem = '.'.join(base + (node.module.split('.') if node.module else []))
            else:
                stem = node.module or ''
            if stem in known:
                found.add(stem)
            for alias in node.names:
                combined = (stem + '.' + alias.name) if stem else alias.name
                if combined in known:
                    found.add(combined)
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else (
                func.attr if isinstance(func, ast.Attribute) else '')
            if name in ('__import__', 'import_module', 'exec', 'eval'):
                uncertain = True
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    if node.args[0].value in known:
                        found.add(node.args[0].value)
    return found, uncertain


def active_vm_roots(inventory):
    """Use sanitized *actual VM* timer targets, never infer from file ages.

    A static service is live when an enabled timer targets it. Disabled legacy
    timers do not make their service an active root, but are not delete-safe
    merely because this inventory omits them.
    """
    if inventory is None:
        return {'timer_targets': [], 'services': [],
                'modules': [], 'external_scripts': []}
    if inventory.get('schema') != 'TORNFREN_SANITIZED_SYSTEMD_DEPENDENCIES_V1':
        raise ValueError('invalid sanitized VM unit-inventory schema')
    units = inventory.get('units')
    if not isinstance(units, list):
        raise ValueError('sanitized VM inventory lacks units')
    targets = {
        u.get('timer_target') for u in units
        if u.get('unit', '').endswith('.timer')
        and u.get('enabled') == 'enabled'
        and isinstance(u.get('timer_target'), str)
    }
    services = [
        u for u in units if u.get('unit', '').endswith('.service')
        and (u.get('enabled') == 'enabled' or u.get('unit') in targets)
    ]
    modules, external_scripts = set(), set()
    for u in services:
        modules.update(m for m in u.get('entry_modules', [])
                       if isinstance(m, str) and m not in ('uvicorn',))
        for script in u.get('entry_py_scripts', []):
            if not isinstance(script, str):
                continue
            if script.startswith('/opt/torn-fren/') and script.endswith('.py'):
                modules.add(script[len('/opt/torn-fren/'): -3].replace('/', '.'))
            else:
                external_scripts.add(script)
        if u.get('unit') == 'torn-fren-web.service':
            modules.add('web.app')
    return {'timer_targets': sorted(targets),
            'services': sorted(u['unit'] for u in services),
            'modules': sorted(modules),
            'external_scripts': sorted(external_scripts)}


def scan(root, extra_seeds=(), vm_units=None):
    known = modules(root)
    edges = {}
    dynamic = set()
    for module, path in known.items():
        imports, uncertain = imported_modules(path, module, known)
        edges[module] = sorted(imports)
        if uncertain:
            dynamic.add(module)

    vm = active_vm_roots(vm_units)
    roots = set(SEEDS) | set(extra_seeds) | set(vm['modules'])
    unit_refs = {}
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in IGNORE_DIRS for part in rel.parts):
            continue
        if path.suffix not in SERVICE_EXTENSIONS:
            continue
        try:
            content = path.read_text(encoding='utf-8-sig', errors='replace')
        except OSError:
            continue
        # systemd -m examples are explicit roots. Shell wrappers may import
        # other modules dynamically; those require a manual service review.
        imports = re.findall(r'(?:^|\s)-m\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)', content)
        scripts = re.findall(r'(?<![\w/])([A-Za-z_]\w*(?:/[A-Za-z_]\w*)*\.py)(?!\w)', content)
        for script in scripts:
            imports.append(script[:-3].replace('/', '.'))
        identified = sorted(set(imports) & known.keys())
        unit_refs[rel.as_posix()] = identified
        roots.update(identified)

    visited = set()
    pending = deque(sorted(roots & known.keys()))
    while pending:
        module = pending.popleft()
        if module in visited:
            continue
        visited.add(module)
        pending.extend(x for x in edges.get(module, []) if x not in visited)

    return {
        'schema': 'torn-fren-readonly-source-reference-audit-v1',
        'scope_root': str(root),
        'source_files': len(known),
        'actual_vm_enabled_timer_targets': vm['timer_targets'],
        'actual_vm_active_service_units': vm['services'],
        'actual_vm_entry_modules': vm['modules'],
        'actual_vm_modules_absent_from_checkout': sorted(set(vm['modules']) - known.keys()),
        'actual_vm_external_entry_scripts': vm['external_scripts'],
        'reachable_static': sorted(visited),
        'dynamic_import_modules': sorted(dynamic),
        'systemd_source_references': unit_refs,
        'possible_unreferenced_review_only': sorted(known.keys() - visited),
        'unresolved_user_or_private_service_roots': True,
        'automatic_deletion_authorized': False,
        'warning': ('An unreferenced static-import result is NOT an unused-file '
                    'finding. Check runtime units, plugins, dynamic imports, '
                    'browser assets, cron, private releases and rollback before archival.'),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path('.'))
    p.add_argument('--entry', action='append', default=[], help='Extra production or research module root')
    p.add_argument('--vm-unit-report', type=Path, default=None,
                   help='Sanitized read-only systemd JSON; never raw unit contents')
    p.add_argument('--json-output', type=Path, default=None)
    args = p.parse_args(argv)
    vm_units = None
    if args.vm_unit_report:
        vm_units = json.loads(args.vm_unit_report.read_text(encoding='utf-8-sig'))
    result = scan(args.root.resolve(), extra_seeds=args.entry, vm_units=vm_units)
    print(f"Scanned {result['source_files']} modules; "
          f"{len(result['reachable_static'])} statically reachable; "
          f"{len(result['possible_unreferenced_review_only'])} require manual review; "
          f"{len(result['dynamic_import_modules'])} with dynamic imports.")
    print(result['warning'])
    if args.json_output:
        args.json_output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result


if __name__ == '__main__':
    main()
