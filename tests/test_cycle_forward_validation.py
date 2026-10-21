import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from research import cycle_forward_validation as m

T=1792112400


class CycleForwardTests(unittest.TestCase):
    def protocol(self):
        return dict(protocol_version=1,name='chamois_cycle_forward_v1',model_sha='a'*40,
            declared_epoch=T-3600,issue_start_epoch=T,issue_end_epoch=T+86400,
            truth_ready_epoch=T+86400+m.MATURITY,item_keys=[m.ITEM],frozen=True,
            primary_comparisons={m.CHALLENGER:m.BASELINE},primary_metric='replanned_all_five_minute_starts')

    def fixture(self,root,cutoff):
        p=root/'protocol.json';p.write_text(json.dumps(self.protocol()))
        db=root/'snapshot.db'
        with sqlite3.connect(db) as cx:
            cx.execute('CREATE TABLE research_metadata(key TEXT,value TEXT)')
            cx.executemany('INSERT INTO research_metadata VALUES(?,?)',
                [('source_cutoff_epoch',str(cutoff)),('sanitized_stock_only','true'),('roster_size','24')])
        return p,db

    def test_protocol_rejects_retroactive_windows_swapped_models_and_short_maturity(self):
        self.assertEqual(m.validate(self.protocol()),self.protocol())
        for key,value in [('declared_epoch',T),('issue_start_epoch',T+1),('issue_end_epoch',T+100),
                          ('truth_ready_epoch',T+86400),('frozen',False),('model_sha','main'),
                          ('item_keys',['jap:Xanax']),('primary_comparisons',{m.BASELINE:m.CHALLENGER})]:
            with self.subTest(key=key),self.assertRaises(ValueError):m.validate(dict(self.protocol(),**{key:value}))

    def test_gate_waits_for_snapshot_not_wall_clock_and_uploaded_marker_is_scoped(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);ready=self.protocol()['truth_ready_epoch'];p,db=self.fixture(root,ready-1)
            before=db.read_bytes();self.assertFalse(m.gate(p,db,root)['should_run']);self.assertEqual(before,db.read_bytes())
            with sqlite3.connect(db) as cx:cx.execute("UPDATE research_metadata SET value=? WHERE key='source_cutoff_epoch'",(str(ready),))
            g=m.gate(p,db,root);self.assertTrue(g['should_run']);Path(g['state_path']).write_text('uploaded-run-id')
            self.assertFalse(m.gate(p,db,root)['should_run'])
            p.write_text(json.dumps(self.protocol(),indent=2));self.assertTrue(m.gate(p,db,root)['should_run'])

    def test_evaluation_uses_frozen_source_window_subset_and_rejects_partial_report(self):
        with tempfile.TemporaryDirectory() as td:
            p,db=self.fixture(Path(td),self.protocol()['truth_ready_epoch']);seen=[]
            def replay(**kw):
                seen.append(kw)
                return dict(issue_window_end_epoch=self.protocol()['issue_end_epoch'],asof_epoch=self.protocol()['truth_ready_epoch'],
                    items={m.ITEM:{'policies':{k:{'replanned_all_five_minute_starts':{'starts':288,'PENDING':0}} for k in (m.BASELINE,m.CHALLENGER)}}})
            r=m.evaluate(p,db,source_sha='a'*40,replayer=replay)
            self.assertFalse(r['automatic_promotion']);self.assertEqual(seen[0]['days'],1)
            self.assertEqual(seen[0]['item_keys'],[m.ITEM]);self.assertTrue(seen[0]['focused_zero'])
            self.assertEqual(seen[0]['issue_end'],self.protocol()['issue_end_epoch'])
            with self.assertRaises(ValueError):m.evaluate(p,db,source_sha='b'*40,replayer=replay)
            def pending(**kw):
                r=replay(**kw);r['items'][m.ITEM]['policies'][m.CHALLENGER]['replanned_all_five_minute_starts']['PENDING']=1;return r
            with self.assertRaises(ValueError):m.evaluate(p,db,source_sha='a'*40,replayer=pending)

    def test_real_replay_has_complete_mature_cohorts_and_readonly_source(self):
        import test_continuous_departure_replay as fixtures
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);db=fixtures.ContinuousTests().fixture(root)
            p=self.protocol();p.update(issue_start_epoch=fixtures.T-2*86400,
                issue_end_epoch=fixtures.T-86400,declared_epoch=fixtures.T-3*86400,
                truth_ready_epoch=fixtures.T-86400+m.MATURITY)
            protocol=root/'protocol.json';protocol.write_text(json.dumps(p));before=db.read_bytes()
            # The fixture omits exporter identity; add the same isolation metadata
            # required by the guarded private snapshot exporter.
            with sqlite3.connect(db) as cx:
                cx.executemany('INSERT INTO research_metadata VALUES(?,?)',
                    [('sanitized_stock_only','true'),('roster_size','24')])
            before=db.read_bytes();r=m.evaluate(protocol,db,source_sha='a'*40)
            self.assertEqual(before,db.read_bytes());self.assertEqual(r['items_evaluated'],1)
            self.assertEqual(r['verified_roster_size'],24)
            self.assertEqual(r['issue_window_end_epoch'],p['issue_end_epoch'])
            for policy in (m.BASELINE,m.CHALLENGER):
                self.assertEqual(r['items'][m.ITEM]['policies'][policy]['replanned_all_five_minute_starts']['starts'],288)

    def camel_protocol(self):
        p=self.protocol();p.update(name='camel_tree_forward_v1',item_keys=['uae:Camel Plushie'],
            primary_comparisons={'zero_path_tree_stable_peak':'zero_path_inventory_flow_peak'},
            secondary_comparisons={'zero_path_tree_stable_peak':'zero_path_aligned_analog50'},
            truth_ready_epoch=T+86400+m.SPECS['camel_tree']['maturity'])
        return p

    def test_camel_patient_comparison_cannot_switch_kind_or_hide_fast_reference(self):
        p=self.camel_protocol();self.assertEqual(m.validate(p,kind='camel_tree'),p)
        with self.assertRaises(ValueError):m.validate(p)
        with self.assertRaises(ValueError):m.validate(self.protocol(),kind='camel_tree')
        for k,v in [('secondary_comparisons',{}),('primary_comparisons',{'zero_path_tree_stable_peak':'zero_path_aligned_analog50'}),
                    ('truth_ready_epoch',T+86400+m.MATURITY)]:
            with self.assertRaises(ValueError):m.validate(dict(p,**{k:v}),kind='camel_tree')

    def test_real_camel_replay_keeps_patient_and_fast_comparisons(self):
        import test_continuous_departure_replay as fixtures
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);db=fixtures.ContinuousTests().fixture(root)
            with sqlite3.connect(db) as cx:
                oldest=fixtures.T-3*86400
                rows=cx.execute('SELECT timestamp,quantity,source,country,item_name FROM stock_history WHERE timestamp<?',(oldest+86400,)).fetchall()
                for shift in (86400,172800):
                    cx.executemany('INSERT INTO stock_history(timestamp,quantity,source,country,item_name) VALUES(?,?,?,?,?)',
                        [(t-shift,q,src,c,n) for t,q,src,c,n in rows])
                cx.executemany("INSERT INTO poll_heartbeats(timestamp,mode,success) VALUES(?,'poll-cycle',1)",
                    [(t,) for t in range(oldest-172800,oldest,30)])
                cx.executemany('INSERT INTO research_metadata VALUES(?,?)',
                    [('sanitized_stock_only','true'),('roster_size','24')])
            p=self.camel_protocol();p.update(issue_start_epoch=fixtures.T-2*86400,
                issue_end_epoch=fixtures.T-86400,declared_epoch=fixtures.T-3*86400,
                truth_ready_epoch=fixtures.T-86400+m.SPECS['camel_tree']['maturity'])
            proto=root/'camel.json';proto.write_text(json.dumps(p));before=db.read_bytes()
            r=m.evaluate(proto,db,source_sha='a'*40,kind='camel_tree');self.assertEqual(before,db.read_bytes())
            self.assertEqual(r['items_evaluated'],1);self.assertFalse(r['automatic_promotion'])
            item=r['items']['uae:Camel Plushie']
            for k in ('zero_path_tree_stable_peak','zero_path_inventory_flow_peak','zero_path_aligned_analog50'):
                self.assertEqual(item['policies'][k]['replanned_all_five_minute_starts']['starts'],288)
            self.assertIn('zero_path_inventory_flow_peak',item['tree_all_start_reference_comparisons']['zero_path_tree_stable_peak'])

    def test_direct_evaluation_cannot_skip_maturity_or_snapshot_isolation(self):
        with tempfile.TemporaryDirectory() as td:
            p,db=self.fixture(Path(td),self.protocol()['truth_ready_epoch']-1)
            with self.assertRaises(ValueError):m.evaluate(p,db,source_sha='a'*40,replayer=lambda **kw:self.fail('premature replay'))
            with sqlite3.connect(db) as cx:cx.execute("UPDATE research_metadata SET value='false' WHERE key='sanitized_stock_only'")
            with self.assertRaises(ValueError):m.gate(p,db,Path(td))


if __name__=='__main__':unittest.main()
