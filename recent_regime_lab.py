import argparse
from datetime import datetime
from services.recent_regime_lab import analyze_recent_regime


def pct(v): return '—' if v is None else f'{100*v:.1f}%'
def dur(v):
    if v is None: return '—'
    v=int(round(v)); sign='-' if v<0 else ''; v=abs(v); h,r=divmod(v,3600); m,s=divmod(r,60)
    if h: return f'{sign}{h}h {m}m {s}s'
    if m: return f'{sign}{m}m {s}s'
    return f'{sign}{s}s'

def main():
    p=argparse.ArgumentParser(); p.add_argument('country'); p.add_argument('item_name'); p.add_argument('--model',default='baseline_all_median'); p.add_argument('--policy',choices=['lifetime','recent20','recent10'],default='lifetime'); a=p.parse_args()
    r=analyze_recent_regime(a.country,a.item_name,a.model,a.policy)
    print(f"=== Recent-regime diagnostic: {r['item_name']} / {r['country']} ===")
    print(f"Model: {r['model']} | policy: {r['policy']} | evidence: {r.get('model_evidence_tier','—')}")
    print(f"Median stock lifetime: {dur(r.get('median_stock_lifetime_seconds'))}")
    print()
    print(f"{'window':>8} {'n':>4} {'arrival':>9} {'med abs err':>12} {'p90 abs err':>12} {'bias':>10}")
    print('-'*66)
    for key in (5,10,15,20,'all'):
        w=r['windows'].get(key,{}); ps=w.get('point') or {}
        print(f"{str(key):>8} {w.get('n',0):4d} {pct(w.get('arrival_success_rate')):>9} {dur(ps.get('median_absolute_error_seconds')):>12} {dur(ps.get('p90_absolute_error_seconds')):>12} {dur(ps.get('median_signed_error_seconds')):>10}")
    print(); print(f"REGIME STATUS: {r['regime_status'].upper()}"); print(r['regime_reason'])
    print(); print('Recent resolved cycles (newest last):')
    for row in r['rows'][-20:]:
        ts=row.get('actual_restock_timestamp'); label=datetime.fromtimestamp(ts).strftime('%m/%d %I:%M:%S %p') if ts else '—'
        print(f"  {label} | error {dur(row.get('signed_error_seconds')):>9} | target offset {dur(row.get('recommended_arrival_offset_seconds')):>9} | {'HIT' if row.get('arrival_hit') else 'MISS'}")

if __name__=='__main__': main()
