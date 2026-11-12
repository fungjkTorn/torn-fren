"""Per-item online research selector using only matured replanning cohorts.

Each expert simulates the same fixed hourly starts. All expert outcomes for
a cohort must mature before it enters the rolling training buffer. Selection
never receives the outcome of the trip it is about to recommend.
"""
from collections import deque
from math import sqrt


class CausalPolicySelector:
    def __init__(self,experts,baseline):
        if not experts or baseline not in experts or len(set(experts))!=len(experts):
            raise ValueError('invalid expert roster')
        self.experts=tuple(experts)
        self.baseline=baseline
        self.active=[]
        self.completed=deque(maxlen=72)
        self.ticks=0
        self.last_issue=None

    def update(self,issued,decisions,*,poll_age,flight_seconds,score):
        if self.last_issue is not None and issued!=self.last_issue+300:
            raise ValueError('selector requires consecutive five-minute issues')
        if set(decisions)!=set(self.experts):
            raise ValueError('all expert decisions are required')
        self.last_issue=issued
        if self.ticks%12==0:
            self.active.append(dict(start=issued,experts={p:{} for p in self.experts}))
        self.ticks+=1
        pending=[]
        for cohort in self.active:
            start=cohort['start'];deadline=start+28800
            for p,state in cohort['experts'].items():
                if 'outcome' in state:
                    continue
                if 'departure' in state:
                    # Evidence.score uses <=180s polling lag plus10s grace.
                    # Refuse even to ask for truth until that bracket is past.
                    if issued>=state['departure']+flight_seconds+190:
                        outcome,_,_=score(state['departure']+flight_seconds)
                        if outcome=='PENDING':
                            raise ValueError('matured expert returned pending evidence')
                        state['outcome']=outcome
                    continue
                if issued>deadline:
                    state['outcome']='ABSTAIN';continue
                departure=decisions[p]['estimated_departure_epoch']
                if (departure is not None and issued<=departure<issued+300
                    and departure<=deadline and poll_age is not None
                    and 0<=poll_age+departure-issued<=180):
                    state.update(departure=departure,wait=departure-start)
            if all('outcome' in s for s in cohort['experts'].values()):
                self.completed.append(cohort)
            else:
                pending.append(cohort)
        self.active=pending

    def select(self):
        winner=self.baseline;best=0.;comparisons={}
        base_resolved=sum(c['experts'][self.baseline]['outcome'] in ('SUCCESS','FAILURE')
                          for c in self.completed)
        for expert in self.experts:
            if expert==self.baseline:
                continue
            pairs=[]
            for cohort in self.completed:
                a=cohort['experts'][self.baseline];b=cohort['experts'][expert]
                if a['outcome'] in ('SUCCESS','FAILURE') and b['outcome'] in ('SUCCESS','FAILURE'):
                    pairs.append((a,b))
            wins=sum(a['outcome']=='FAILURE' and b['outcome']=='SUCCESS' for a,b in pairs)
            losses=sum(a['outcome']=='SUCCESS' and b['outcome']=='FAILURE' for a,b in pairs)
            extra_wait=sum(b['wait']-a['wait'] for a,b in pairs)
            # Predeclared conservative research rule. Correlated cohorts mean
            # this is NOT a statistical certification or probability estimate.
            supported=(len(pairs)>=max(24,.8*base_resolved)
                       and wins-losses>=max(4,1.64*sqrt(wins+losses)))
            utility=((wins-losses)/len(pairs)-.05*max(0,extra_wait/len(pairs))/3600) if pairs else 0.
            comparisons[expert]=dict(matched=len(pairs),wins=wins,losses=losses,
                                     eligible=supported,utility=round(utility,6))
            if supported and utility>best:
                winner=expert;best=utility
        return winner,dict(training_cohorts=len(self.completed),pending_cohorts=len(self.active),
                           selected_expert=winner,comparisons=comparisons,
                           calibrated_success_probability=None)
