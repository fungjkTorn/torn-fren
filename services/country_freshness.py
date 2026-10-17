"""Provider-reported country clocks; never infer game-event timestamps."""
import re

COUNTRIES=frozenset(('mex','cay','can','haw','uni','arg','swi','jap','chi','uae','sou'))
DDL="""
CREATE TABLE IF NOT EXISTS country_stock_observations (
    id INTEGER PRIMARY KEY,
    received_epoch INTEGER NOT NULL,
    country TEXT NOT NULL,
    source TEXT NOT NULL,
    country_update_epoch INTEGER,
    export_epoch INTEGER,
    clock_status TEXT NOT NULL,
    export_clock_status TEXT NOT NULL,
    item_count INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_country_observation_time
    ON country_stock_observations(country,received_epoch,id);
CREATE INDEX IF NOT EXISTS idx_country_observation_receipt
    ON country_stock_observations(received_epoch,id);
"""


def parse_clock(value,received):
    # No unit guessing, float truncation, bool conversion or local-time
    # substitution. Preserve valid future seconds but flag them explicitly.
    if value is None:return None,'MISSING'
    if type(value) is str and re.fullmatch(r'[0-9]{1,10}',value):value=int(value)
    if type(value) is not int or not 0<value<=9999999999:return None,'INVALID'
    return value,('FUTURE' if value>received else 'REPORTED')


def observation(country,country_data,source,received,export_epoch=None):
    if country not in COUNTRIES or source not in ('yata','prometheus','unknown'):
        raise ValueError('unrecognized country/provider')
    if type(received) is not int or received<=0 or not isinstance(country_data,dict):
        raise ValueError('invalid receipt or country data')
    stocks=country_data.get('stocks',[])
    if not isinstance(stocks,list):raise ValueError('invalid country stocks')
    update,status=parse_clock(country_data.get('update'),received)
    export,export_status=parse_clock(export_epoch,received)
    if not stocks:status='EMPTY_PAYLOAD_'+status
    return (received,country,source,update,export,status,export_status,len(stocks))


def record(conn,country,country_data,source,received,export_epoch=None):
    row=observation(country,country_data,source,received,export_epoch)
    conn.execute('''INSERT INTO country_stock_observations
        (received_epoch,country,source,country_update_epoch,export_epoch,
         clock_status,export_clock_status,item_count) VALUES(?,?,?,?,?,?,?,?)''',row)


def status_at(row,asof,*,max_age=180):
    """As-of report age only; not verified per-item/game freshness."""
    received,_,_,update,_,status,_,_=row
    if received>asof:raise ValueError('future country observation')
    if asof-received>max_age:return 'RECEIPT_EXPIRED'
    if status!='REPORTED':return status
    return 'REPORT_RECENT' if 0<=asof-update<=max_age else 'REPORT_OLD'
