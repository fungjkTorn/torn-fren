"""Compact display of full-roster frozen-shadow JSON, no model selection.

Reads an explicitly supplied report file. All eight fixed variants stay
visible; success denominators, unknowns, abstentions and pending counts are
preserved. No production/database access and no writes.
"""
import argparse
import json

MODES=(('NOW','leave_now_control'),('RATE','rate_current_quarter'),
       ('PAIR-P','paired_recent_peak'),('PAIR60','paired_recent_60'),
       ('SEQ-P','sequence_blocks_peak'),('SEQ60','sequence_blocks_60'),
       ('QTY-P','quantity_blocks_peak'),('QTY60','quantity_blocks_60'))
OUTCOMES=('SUCCESS','FAILURE','UNKNOWN','ABSTAIN','PENDING')


def cell(value):
    counts={k:value.get(k,0) for k in OUTCOMES}
    if any(type(v) is not int or v<0 for v in counts.values()):raise ValueError('Invalid outcome counts')
    known=counts['SUCCESS']+counts['FAILURE']
    if value.get('known',known)!=known or sum(counts.values())!=value['issues']:
        raise ValueError('Outcome totals do not match report')
    base=str(counts['SUCCESS'])+'/'+str(known) if known else '-'
    return base+'['+'/'.join(str(counts[k]) for k in ('UNKNOWN','ABSTAIN','PENDING'))+']'


def render(report):
    items=report['items']
    lines=['FROZEN ARRIVAL PLANS; future departure reconfirmation untested.',
        'Cells: success/known[unknown/abstain/pending]. A dash means no known arrivals.',
        'All variants shown; no best-model selection or automatic promotion.',
        f"Items={len(items)} Records={report.get('records','?')} Missing source clocks={report.get('records_missing_source_clock','?')}",
        f"{'Item':27} {'N':>2} "+' '.join(f'{name:>14}' for name,_ in MODES)]
    for key,models in sorted(items.items()):
        counts={models[mode]['issues'] for _,mode in MODES}
        if len(counts)!=1:raise ValueError('Model issue counts differ')
        lines.append(f'{key:27} {next(iter(counts)):>2} '+' '.join(f'{cell(models[mode]):>14}' for _,mode in MODES))
    return '\n'.join(lines)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report');a=p.parse_args()
    with open(a.report) as f:report=json.load(f)
    print(render(report))
