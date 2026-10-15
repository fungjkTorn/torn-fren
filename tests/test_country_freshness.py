import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import country_freshness as f,history_service as hs


class ClockTests(unittest.TestCase):
    def test_no_unit_guessing_missing_future_invalid_and_no_raw_payload(self):
        for raw,status in ((None,'MISSING'),(True,'INVALID'),(1.5,'INVALID'),
                           ('not-a-timestamp','INVALID'),(1700000000000,'INVALID'),
                           (101,'FUTURE'),('100','REPORTED')):
            row=f.observation('jap',{'update':raw,'stocks':[{}]},'yata',100)
            self.assertEqual(row[5],status)
            self.assertNotIn('not-a-timestamp',str(row))
        row=f.observation('jap',{'update':99,'stocks':[]},'prometheus',100)
        self.assertEqual(f.status_at(row,100),'EMPTY_PAYLOAD_REPORTED')

    def test_future_queries_stale_receipts_and_old_country_reports(self):
        row=f.observation('jap',{'update':800,'stocks':[{}]},'yata',1000)
        self.assertEqual(f.status_at(row,1000),'REPORT_OLD')
        row=f.observation('jap',{'update':990,'stocks':[{}]},'yata',1000)
        self.assertEqual(f.status_at(row,1000),'REPORT_RECENT')
        self.assertEqual(f.status_at(row,1200),'RECEIPT_EXPIRED')
        with self.assertRaises(ValueError):f.status_at(row,999)

    def test_unchanged_stock_and_clock_regressions_are_both_retained(self):
        with tempfile.TemporaryDirectory() as td,patch.object(hs,'DB_PATH',Path(td)/'stock.db'),patch.object(hs,'_DB_READY',False):
            stock=dict(id=206,name='Xanax',quantity=20,cost=750000)
            for receipt,update,source in ((1000,990,'yata'),(1030,990,'yata'),
                                          (1060,980,'yata'),(1090,None,'prometheus')):
                with patch.object(hs.time,'time',return_value=receipt):
                    changed=hs.save_all_snapshots(dict(source=source,timestamp=receipt-1,
                        stocks={'jap':dict(stocks=[stock],update=update)}))
                    self.assertEqual(changed,{'jap':['Xanax']} if receipt==1000 else {})
            with sqlite3.connect(hs.DB_PATH) as cx:
                rows=cx.execute('SELECT received_epoch,country_update_epoch,source FROM country_stock_observations ORDER BY id').fetchall()
                self.assertEqual(rows,[(1000,990,'yata'),(1030,990,'yata'),(1060,980,'yata'),(1090,None,'prometheus')])
                self.assertEqual(cx.execute('SELECT timestamp,quantity FROM stock_history').fetchall(),[(1000,20)])
                self.assertEqual(cx.execute('SELECT export_epoch FROM country_stock_observations ORDER BY id').fetchall(),[(999,),(1029,),(1059,),(1089,)])
                self.assertEqual(cx.execute('SELECT count(*) FROM poll_heartbeats').fetchone()[0],0)

    def test_item_save_failure_rolls_back_corresponding_country_clock(self):
        with tempfile.TemporaryDirectory() as td,patch.object(hs,'DB_PATH',Path(td)/'stock.db'),patch.object(hs,'_DB_READY',False):
            with self.assertRaises(KeyError):
                hs.save_snapshot_from_export('jap',dict(update=100,stocks=[{}]),'yata')
            with sqlite3.connect(hs.DB_PATH) as cx:
                self.assertEqual(cx.execute('SELECT count(*) FROM country_stock_observations').fetchone()[0],0)


if __name__=='__main__':unittest.main()
