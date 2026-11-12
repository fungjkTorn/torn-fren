"""Bounded public-provider clock observations; no Torn key or collector access."""
import argparse
import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from services.country_freshness import COUNTRIES,observation,status_at

URLS={'yata':'https://yata.yt/api/v1/travel/export/',
      'prometheus':'https://api.prombot.co.uk/api/travel'}


def japan_external_value(stocks):
    """Unverified provider nextRestock value; never an observed event label."""
    row=next((r for r in stocks if isinstance(r,dict) and str(r.get('name','')).casefold()=='xanax'),None)
    if row is None:return dict(status='ITEM_MISSING')
    value=row.get('nextRestock');stamp=None
    if type(value) is str:
        try:
            parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
            if parsed.tzinfo is not None:
                candidate=int(parsed.timestamp())
                if 0<candidate<=9999999999:stamp=candidate
        except (ValueError,OverflowError):pass
    quantity=row.get('quantity')
    return dict(quantity=quantity if type(quantity) is int and quantity>=0 else None,
        next_restock_field_present='nextRestock' in row,next_restock_epoch=stamp,
        status='UNVERIFIED_PROVIDER_VALUE' if stamp is not None else 'NO_PARSEABLE_PROVIDER_VALUE',
        observed_game_event=False)


def normalize(provider,payload,received):
    if not isinstance(payload,dict) or not isinstance(payload.get('stocks'),dict):
        raise ValueError('invalid export structure')
    result={}
    for country in sorted(COUNTRIES):
        data=payload['stocks'].get(country)
        if data is None:
            result[country]=dict(status='COUNTRY_MISSING',age_seconds=None,update_epoch=None)
            continue
        row=observation(country,data,provider,received,payload.get('timestamp'))
        result[country]=dict(status=status_at(row,received),age_seconds=received-row[3] if row[3] is not None else None,
            update_epoch=row[3],export_epoch=row[4],export_clock_status=row[6],item_count=row[7])
        if country=='jap':result[country]['xanax_external_value']=japan_external_value(data.get('stocks',[]))
    return result


def summarize(samples):
    out={}
    for provider in URLS:
        good=[s for s in samples if s['provider']==provider and s.get('countries') is not None]
        countries={}
        for country in sorted(COUNTRIES):
            rows=[s['countries'][country] for s in good]
            ages=[r['age_seconds'] for r in rows if r['age_seconds'] is not None and r['age_seconds']>=0]
            clocks=[r['update_epoch'] for r in rows if r['update_epoch'] is not None]
            countries[country]=dict(samples=len(rows),recent=sum(r['status']=='REPORT_RECENT' for r in rows),
                old=sum(r['status']=='REPORT_OLD' for r in rows),
                min_report_age_seconds=min(ages,default=None),max_report_age_seconds=max(ages,default=None),
                observed_clock_changes=sum(a!=b for a,b in zip(clocks,clocks[1:])),
                observed_clock_regressions=sum(b<a for a,b in zip(clocks,clocks[1:])),
                statuses=sorted({r['status'] for r in rows}))
        out[provider]=dict(successful_fetches=len(good),failed_fetches=sum(s['provider']==provider and s.get('countries') is None for s in samples),countries=countries)
    return out


def probe(*,rounds=6,interval=60,fetch=None,clock=time.time,sleep=time.sleep):
    if type(rounds) is not int or not 1<=rounds<=16 or type(interval) is not int or not 30<=interval<=120:
        raise ValueError('invalid bounded sampling plan')
    def default_fetch(provider):
        with urllib.request.urlopen(urllib.request.Request(URLS[provider],headers={'User-Agent':'TORN-FREN-research-freshness/1'}),timeout=15) as response:
            raw=response.read(8000001)
        if len(raw)>8000000:raise ValueError('export response cap exceeded')
        return json.loads(raw)
    fetch=fetch or default_fetch;samples=[]
    for n in range(rounds):
        start=clock()
        for provider in URLS:
            try:
                data=fetch(provider);received=int(clock())
                samples.append(dict(round=n,provider=provider,received_epoch=received,
                    countries=normalize(provider,data,received)))
            except Exception as exc:
                # Never persist raw error/response strings, tokens or headers.
                samples.append(dict(round=n,provider=provider,received_epoch=int(clock()),
                    error_type=type(exc).__name__,
                    http_status=exc.code if type(getattr(exc,'code',None)) is int else None,countries=None))
        if n+1<rounds:sleep(max(0,interval-(clock()-start)))
    return dict(kind='PUBLIC_PROVIDER_CLOCK_OBSERVATIONS',samples=samples,summary=summarize(samples),
        actual_game_freshness_verified=False,collector_source_accessed=False,
        warning='Provider-reported country clock only; not item-level verification or historical backfill. Short probe cannot establish long-term freshness.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True)
    p.add_argument('--rounds',type=int,default=6);p.add_argument('--interval',type=int,default=60)
    a=p.parse_args();r=probe(rounds=a.rounds,interval=a.interval)
    Path(a.output).write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
    print('FRESHNESS_SUMMARY',json.dumps(r['summary'],sort_keys=True))
