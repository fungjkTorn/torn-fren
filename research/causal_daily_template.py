"""Past-only daily phase analog, adapted from Nessie's archived template.

Uses raw indexed deltas, not hindsight bounce-cleaning or whole-dataset
feature normalization. This is a challenger, not a parity claim for the
archived champion. Returned support is uncalibrated template agreement.
"""
from __future__ import annotations
import bisect

DAY=86400
STEP=300
HORIZON=28800


class DailyTemplate:
    def __init__(self, observations, crosses):
        self.rows=observations
        self.times=[r.epoch for r in observations]
        self.crosses=crosses
        self.match=None
        self.windows=[]
        start=None;previous=None
        for row in observations:
            if previous is not None:
                # Match V145: a benign provider change inside the SAME
                # stock phase does not erase an already bounded episode.
                # A provider change AT a threshold crossing is ambiguous.
                invalid=(row.epoch<=previous.epoch or crosses(previous.epoch,row.epoch)
                         or (row.source!=previous.source and
                             (row.quantity>=30)!=(previous.quantity>=30)))
                if invalid:
                    start=None
                elif previous.quantity<30<=row.quantity:
                    start=row.epoch
                elif previous.quantity>=30>row.quantity and start is not None:
                    if not crosses(start,row.epoch):
                        self.windows.append((start,row.epoch))
                    start=None
            previous=row

    def state(self, clock, issued):
        if clock>issued:
            raise ValueError("template queried future stock")
        j=bisect.bisect_right(self.times,clock)-1
        if j<0 or clock-self.times[j]>86400 or self.crosses(self.times[j],clock):
            return None
        return self.rows[j].quantity>=30

    def plan(self, issued, flight):
        # Exact archived Nessie feature geometry: 2h lookback, one-day
        # lag, +/-1h shift, balanced phase fit >=0.5. Timing selection
        # variants are new; no winner is promoted into production.
        points=list(range(issued-7200,issued+1,STEP))
        current=[self.state(t,issued) for t in points]
        best=None
        alignments=[]
        for shift in range(-3600,3601,STEP):
            reference=[self.state(t-DAY-shift,issued) for t in points]
            pairs=[(a,b) for a,b in zip(current,reference) if a is not None and b is not None]
            if len(pairs)<6:
                continue
            balances=[]
            for phase in (False,True):
                values=[a==b for a,b in pairs if a==phase]
                if values:
                    balances.append(sum(values)/len(values))
            fit=sum(balances)/len(balances)
            raw=sum(a==b for a,b in pairs)/len(pairs)
            score=(fit,raw,-abs(shift),-shift)
            alignments.append((fit,shift))
            if best is None or score>best[0]:
                best=(score,shift)
        if best is None or best[0][0]<.5:
            self.match=None
            return {"earliest":None,"center":None,"first_center":None,"status":"NO_MATCHING_DAILY_TEMPLATE"}
        shift=best[1]
        supported=[s for fit,s in alignments if fit>=best[0][0]-.02]
        self.match=(issued,shift,min(supported),max(supported),best[0][0])
        eligible=[]
        for delay in range(0,HORIZON+1,STEP):
            historical_arrival=issued+delay+flight-DAY-shift
            # All historical arrival evidence MUST resolve before issue.
            if historical_arrival+10>issued:
                continue
            a=bisect.bisect_right(self.times,historical_arrival)-1
            b=bisect.bisect_right(self.times,historical_arrival+10)-1
            if a<0 or b<0 or self.crosses(historical_arrival,historical_arrival+10):
                continue
            segment=self.rows[a:b+1]
            if len({r.source for r in segment})!=1:
                continue
            if all(r.quantity>=30 for r in segment) and self.state(historical_arrival+10,issued) is True:
                eligible.append(delay)
        groups=[]
        for delay in eligible:
            if not groups or delay-groups[-1][-1]>STEP:
                groups.append([delay])
            else:
                groups[-1].append(delay)
        # Immediate is eligible independently; future windows require
        # adjacent 5m support. Count narrow single bins as abstentions.
        credible=[g for g in groups if len(g)>=2 or g[0]==0]
        if not credible:
            return {"earliest":None,"center":None,"first_center":None,"status":"NO_SUSTAINED_TEMPLATE_WINDOW"}
        first=credible[0]
        widest=max(credible,key=lambda g:(len(g),-g[0]))
        return {"earliest":issued+first[0],"center":issued+widest[len(widest)//2],
                "first_center":issued if first[0]==0 else issued+first[len(first)//2],
                "fit":round(best[0][0],4),"shift_seconds":shift,
                "status":"UNCALIBRATED_DAILY_TEMPLATE_CANDIDATE"}

    def event_forecast(self, issued, item_key, flight):
        """Project every fully resolved historical stock window, not one trip.

        Event bands describe near-optimal template ALIGNMENTS; they are
        not calibrated confidence intervals. Future stock is never read.
        """
        result={"item_key":item_key,"asof_epoch":issued,"flight_seconds":flight,
                "status":"NO_MATCHING_DAILY_TEMPLATE","restock_events":[],
                "current_stock_window":None,"arrival_stock_threshold":30,
                "model_name":"daily_phase_template_events",
                "uncertainty_kind":"UNCALIBRATED_ALIGNMENT_RANGE"}
        j=bisect.bisect_right(self.times,issued)-1
        current=self.rows[j] if j>=0 else None
        result.update(observed_current_quantity=current.quantity if current else None,
                      last_quantity_change_epoch=current.epoch if current else None)
        if self.match is None or self.match[0]!=issued:
            return result
        _,shift,early_shift,late_shift,fit=self.match
        offset=DAY+shift
        for start,end in self.windows:
            if end>issued:
                break  # Only fully observed historical stocked episodes.
            projected=start+offset;stock_end=end+offset
            if current and current.quantity>=30 and projected<=issued<stock_end:
                result["current_stock_window"]={"predicted_stock_below_30_epoch":stock_end}
            if issued<projected<=issued+HORIZON:
                result["restock_events"].append({
                    "predicted_restock_epoch":projected,
                    "restock_early_epoch":start+DAY+early_shift,
                    "restock_late_epoch":start+DAY+late_shift,
                    "predicted_stock_below_30_epoch":stock_end,
                    "historical_template_restock_epoch":start,
                    "historical_template_depletion_epoch":end})
        result["restock_events"]=result["restock_events"][:64]
        result["status"]="EVENT_TIMELINE_FORECAST_AVAILABLE"
        result["template_fit_not_success_probability"]=fit
        return result
