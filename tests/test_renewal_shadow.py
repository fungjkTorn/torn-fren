import json
import sqlite3
import tempfile
import unittest
import io
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from research.japan_xanax import renewal_shadow as m

T=1792200000


def rows():
    result=[]
    for i in range(40):
        t=T-40*3600+i*3600
        result.extend([(t,0,'a'),(t+1200,100,'a'),(t+1800,20,'a'),(t+2100,0,'a')])
    return result


class RenewalTests(unittest.TestCase):
    def test_readonly_scoring_distinguishes_scorer_from_original_producer_pin(self):
        with patch('sys.argv',['renewal_shadow','score','--source','source.db','--journal','old.sqlite','--model-sha','a'*40]), \
             patch.object(m.subprocess,'check_output',return_value='b'*40), \
             patch.object(m,'score_journal',return_value={'model_sha':'a'*40}) as score,redirect_stdout(io.StringIO()) as out:
            m.main()
        self.assertEqual(score.call_args.kwargs['expected_sha'],'a'*40)
        self.assertEqual(json.loads(out.getvalue()),{'model_sha':'a'*40,'scorer_sha':'b'*40})
        with patch('sys.argv',['renewal_shadow','record','--source','source.db','--journal','new.sqlite','--model-sha','a'*40]), \
             patch.object(m.subprocess,'check_output',return_value='b'*40):
            with self.assertRaises(ValueError):m.main()

    def history(self):
        h=m.History(lambda a,b:False)
        for row in rows():h.add(row)
        return h

    def test_completed_true_zero_pairs_and_separate_buying_window(self):
        h=self.history();self.assertGreaterEqual(len(h.cycles),16)
        c=h.cycles[-1];self.assertEqual(c.available,600);self.assertEqual(c.end-c.restock,900)
        h.add((T+100,200,'a'));anchor=h.low
        h.add((T+200,20,'a'));self.assertEqual(h.low,anchor)
        h.add((T+300,0,'a'));self.assertEqual(h.low,T+300)

    def test_all_variants_are_deterministic_past_only_and_bounded(self):
        h=self.history();a=h.plans(T,poll_age=0);b=h.plans(T,poll_age=0)
        self.assertEqual(a,b);self.assertEqual(set(a),set(m.MODES))
        self.assertTrue(any(p['departure'] is not None for k,p in a.items() if k!='leave_now_control'))
        for p in a.values():
            if p['departure'] is not None:self.assertTrue(T<=p['departure']<=T+m.WAIT)
            if 'latest_training_cycle_end' in p:self.assertLessEqual(p['latest_training_cycle_end'],T)
        with self.assertRaises(ValueError):h.plans(T-86400,poll_age=0)
        self.assertTrue(all(p['departure'] is None for p in h.plans(T,poll_age=181).values()))

    def test_provider_switch_and_positive_topups_reset_current_phase(self):
        h=self.history();h.add((T+100,100,'a'));h.add((T+200,200,'a'))
        self.assertIsNone(h.phase_start)
        self.assertTrue(all(p['departure'] is None for k,p in h.plans(T+200,poll_age=0).items() if k!='leave_now_control'))
        h.add((T+300,0,'b'));self.assertIsNone(h.low)

    def test_source_reads_are_bounded_readonly_and_cut_off_future_rows(self):
        from test_v160_prospective_v151_shadow import collector_fixture
        with tempfile.TemporaryDirectory() as td:
            source=collector_fixture(Path(td),issued=T)
            with sqlite3.connect(source) as db:
                db.execute("INSERT INTO stock_history(timestamp,quantity,source,country,item_name) VALUES(?,?,?,?,?)",(T+1000,99999,'future','jap','Xanax'))
            before=source.read_bytes();observed,polls,crosses,evidence,cutoff=m.source_data(source,now=T)
            self.assertTrue(all(t<=T for t,q,s in observed));self.assertLessEqual(cutoff,T)
            self.assertEqual(source.read_bytes(),before)
            with self.assertRaises(ValueError):m.source_data(source,now=T,item_key='unknown:Xanax')

    def test_benchmark_same_fixed_starts_and_15_second_publication_floor(self):
        class Evidence:
            def score(self,arrival):return ('SUCCESS','TEST',None)
        polls=list(range(T-3*86400,T+1,30))
        with patch.object(m,'source_data',return_value=([],polls,lambda a,b:False,Evidence(),T)):
            r=m.benchmark('unused',days=1,model_sha='a'*40)
        self.assertTrue(all(p['starts']==288 for p in r['policies'].values()))
        self.assertEqual(r['publication_floor_seconds'],15)
        self.assertEqual(r['policies']['leave_now_control']['scored'],288)
        self.assertFalse(r['automatic_promotion'])

    def test_shadow_recorder_includes_all24_and_scorer_keeps_each_model(self):
        class Evidence:
            def score(self,arrival):return ('SUCCESS','TEST',None)
        data=(rows(),[T],lambda a,b:False,Evidence(),T)
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'source.db';source.write_bytes(b'untouched-source')
            journal=Path(td)/'shadow.sqlite'
            # Four monotonic calls: deadline, loop condition, begin, elapsed;
            # fifth ends the bounded session without sleeping.
            with patch.object(m,'source_data',return_value=data),patch.object(m.time,'time',return_value=T), \
                 patch.object(m.time,'monotonic',side_effect=[0,0,0,1,61]),patch.object(m.time,'sleep'),patch('builtins.print'):
                m.record(source,journal,model_sha='a'*40,duration=60)
            with sqlite3.connect(journal) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM plans').fetchone()[0],24*len(m.MODES))
                self.assertEqual(db.execute('SELECT COUNT(DISTINCT item_key) FROM plans').fetchone()[0],24)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM plans WHERE item_key='jap:Xanax'").fetchone()[0],len(m.MODES))
                saved=json.loads(db.execute('SELECT record FROM plans LIMIT 1').fetchone()[0])
                self.assertEqual(saved['source_cutoff'],T)
                self.assertEqual(saved['poll_age_seconds'],0)
            before=journal.read_bytes()
            progress=[]
            with patch.object(m,'source_data',return_value=data) as reads:
                r=m.score_journal(source,journal,expected_sha='a'*40,progress=progress.append)
            self.assertEqual(len(progress),24)
            self.assertEqual(reads.call_args_list[0].kwargs['now'],None)
            self.assertTrue(all(c.kwargs['now']==T for c in reads.call_args_list[1:]))
            self.assertEqual(r['truth_cutoff'],T)
            self.assertEqual(r['records_missing_source_clock'],0)
            self.assertEqual(len(r['items']),24)
            self.assertEqual(set(r['items']['jap:Xanax']),set(m.MODES))
            self.assertEqual(before,journal.read_bytes());self.assertEqual(source.read_bytes(),b'untouched-source')
            with self.assertRaises(ValueError):m.record(source,journal,model_sha='a'*40,duration=60)
            with self.assertRaises(ValueError):m.score_journal(source,journal,expected_sha='b'*40)
            with sqlite3.connect(journal) as db:
                for issued,key,mode,encoded in db.execute('SELECT * FROM plans').fetchall():
                    record=json.loads(encoded);record.pop('source_cutoff');record.pop('poll_age_seconds')
                    db.execute('UPDATE plans SET record=? WHERE issued=? AND item_key=? AND mode=?',(json.dumps(record),issued,key,mode))
            with patch.object(m,'source_data',return_value=data):legacy=m.score_journal(source,journal)
            self.assertEqual(legacy['records_missing_source_clock'],24*len(m.MODES))
            with sqlite3.connect(journal) as db:
                record['model_sha']='tampered'
                db.execute('UPDATE plans SET record=? WHERE issued=? AND item_key=? AND mode=?',(json.dumps(record),issued,key,mode))
            with self.assertRaises(ValueError):m.score_journal(source,journal)

    def test_source_expiring_during_build_cannot_publish_a_partial_roster(self):
        class Evidence:
            def score(self,arrival):return ('SUCCESS','TEST',None)
        data=([],[T-175],lambda a,b:False,Evidence(),T-175)
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'source.db';source.write_bytes(b'untouched-source')
            journal=Path(td)/'shadow.sqlite'
            with patch.object(m,'source_data',return_value=data),patch.object(m.time,'time',side_effect=[T,T+15]), \
                 patch.object(m.time,'monotonic',side_effect=[0,0,0,1,61]),patch.object(m.time,'sleep'),patch('builtins.print'):
                m.record(source,journal,model_sha='a'*40,duration=60)
            with sqlite3.connect(journal) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM plans').fetchone()[0],0)
