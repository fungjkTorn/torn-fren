import argparse
from services.prediction_v2_preflight import build_prediction_v2_preflight


def pct(v): return '—' if v is None else f'{100*v:.1f}%'
def dur(v):
    if v is None: return '—'
    v=int(round(v)); sign='-' if v<0 else ''; v=abs(v); h,r=divmod(v,3600); m,s=divmod(r,60)
    if h: return f'{sign}{h}h {m}m {s}s'
    if m: return f'{sign}{m}m {s}s'
    return f'{sign}{s}s'

def main():
    p=argparse.ArgumentParser(); p.add_argument('country'); p.add_argument('item_name'); a=p.parse_args()
    r=build_prediction_v2_preflight(a.country,a.item_name); c=r.get('chosen') or {}
    print(f"=== Prediction v2 PRE-FLIGHT: {r['item_name']} / {r['country']} ===")
    print(f"Cycle class: {r['behavior_class']}")
    print(f"Model evidence: {str(r['model_evidence_tier']).upper()}")
    print(f"Travel reliability: {str(r['travel_reliability']).upper()}")
    print(f"Median stock lifetime: {dur(r['median_stock_lifetime_seconds'])}")
    print()
    print(f"Chosen point model: {c.get('model','—')}")
    print(f"Chosen arrival policy: {c.get('policy','—')}")
    print(f"Resolved recommendations: {c.get('n','—')}")
    print(f"Lifetime arrival success: {pct(c.get('arrival_success_rate'))}")
    print(f"Recent-20 arrival success: {pct(c.get('recent20_success_rate'))}")
    print(f"Recent-10 arrival success: {pct(c.get('recent10_success_rate'))}")
    print(f"Current recommended arrival offset: {dur(c.get('current_arrival_offset_seconds'))}")
    print(f"90% restock-window width: {dur(c.get('window_width_seconds'))}")
    print()
    print(f"Ready for live guidance: {r['ready_for_live_guidance']}")
    print(f"Caution-only: {r['caution_only']}")
    print(r['selection_reason'])
    rr=r.get('recent_regime')
    if rr:
        print(); print(f"Japan recent-regime status: {rr['regime_status'].upper()}")
        print(rr['regime_reason'])

if __name__=='__main__': main()
